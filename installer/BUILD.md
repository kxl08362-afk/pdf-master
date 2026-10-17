# Windows x64 build

Build on Windows 11 x64 using x64 CPython, PowerShell and Inno Setup 6.2.2 or newer. End users need none of these tools. The build machine requires internet only when obtaining dependencies/models/compiler.

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
./build.ps1 -Iscc 'C:/path/to/InnoSetup/ISCC.exe'
```

The release includes `resources/tessdata/rus.traineddata`, `eng.traineddata` (tessdata_best), `resources/fonts/DejaVuSans.ttf` and all files under `licenses/`. Keep them alongside source for a reproducible feature-complete build. PyMuPDF includes its own OCR engine; no Tesseract executable is installed or executed.

Version 0.3.0 also embeds img2pdf, pikepdf/QPDF, lxml and packaging, pinned in requirements.txt. `installer/hooks/hook-pikepdf.py` collects the pikepdf Windows wheel's native libraries into `pikepdf.libs` so its DLL-directory loader works in the frozen layout. No external qpdf executable is needed. Refresh their exact installed notices and source URLs with `python scripts/build_collect_extra_licenses.py` before freezing a new dependency version. These libraries provide actual conversion/optimization; no Stirling Java/server stack or PDFium runtime is included.

Compiler: Inno Setup 6.2.2, official immutable release:
https://github.com/jrsoftware/issrc/releases/download/is-6_2_2/innosetup-6.2.2.exe

For an isolated portable compiler installation, run the official installer with `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER /portable=1 /NOICONS /DIR="C:\absolute\project\installer\tools\InnoSetup"`. Check its Authenticode signature first. The build script looks for the project compiler, then ISCC on PATH, or accepts `-Iscc`. The compiler and its downloaded installer are build tools and are not part of the application distribution.

Output: `dist/installers/PDFMaster-Setup-0.3.0.exe`. The application uses a PyInstaller onedir layout with shared Qt DLLs and license notices. Its output and installer are unsigned; no Authenticode certificate is included. Windows SmartScreen may show a warning for an unknown publisher.

Qt uses the ICU component supplied by Windows 11. The spec deliberately excludes `icuuc.dll` and `icudt*.dll` from the bundle: a different ICU from build-machine PATH can have incompatible suffixed exports and prevent QtCore from loading. No separate ICU or Visual C++ installation is needed. `scripts/build_manifest.py` proves frozen application bytecode equals the corresponding current source and records SHA256 inputs plus installer checksum in `dist/build-manifest.json`.

Isolated silent verification (substitute an absolute temporary path):

```powershell
Start-Process dist/installers/PDFMaster-Setup-0.3.0.exe -Wait -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/DIR="C:\absolute\verification\PDFMaster"'
& 'C:/absolute/verification/PDFMaster/PDFMaster.exe'
Start-Process 'C:/absolute/verification/PDFMaster/unins000.exe' -Wait -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'
```

The installer uses current-user registry uninstall registration and Start menu shortcuts. It never registers as the default PDF application, installs fonts globally, changes PATH, or needs administrator elevation. Silent installation skips launching the application. Uninstallation removes installed files; user documents are stored outside the installation directory.

Release maintainers can run `./scripts/verify_windows_install.ps1 -CheckOnly` for a read-only check of existing installations, running PDFMaster processes, the default application path and the Start menu shortcut. Full verification, `./scripts/verify_windows_install.ps1`, refuses to proceed if any of these already exist. After an approved final build it installs into a fresh unique directory under `qa/`, verifies version/registry/shortcut, runs the installed self-test with `PATH=System32` and an invalid `TESSDATA_PREFIX`, captures the installed GUI through the application's `--screenshot` mode, and uninstalls in a `finally` block. A user-created PDF inside the install directory must survive uninstallation with the same SHA256. Evidence is saved under the unique QA directory. This helper never removes application data or an existing user installation; it is not run as part of building or packaging a release.

## GitHub-hosted CI and prepared SignPath integration

`.github/workflows/windows-ci.yml` runs on GitHub-hosted `windows-2025` for pull requests, main pushes, manual runs and trusted reusable calls. It uses a read-only repository token and no signing secrets. Every remote action is pinned to a full commit SHA. It runs pinned development dependencies, pytest, the normal build and a frozen self-test, then stores clearly named unsigned installer/application artifacts plus source/input hashes and commit/run information. `PYTHONUTF8=1` keeps Cyrillic diagnostics reproducible. A local/static check is not evidence of a successful GitHub run; record the actual run URL/result separately.

Bootstrap uses `scripts/prepare_ci_tools.ps1`. CPython **3.12.14 x64** comes from Astral's official immutable `python-build-standalone` release `20260901`, SHA256 `e90c1b6419da3bd812dd73bb3de40287a21abf153438147639ec5e20375ea93f`. This is explicitly an Astral distribution, not a PSF Windows installer: `actions/setup-python` has no Windows binary for this security-only release. Inno Setup **6.2.2** is downloaded from its official immutable release, SHA256 `8117d10d00a2ad33a1390978ea3872861c330e087914410a6377b22c4c5b8563`; Authenticode must be `Valid` with the pinned Martijn Laan certificate. Tools stay inside `.ci-tools`; no global Python or compiler setup is performed. The script returns JSON, writes `ci/tools.json`, and sets GitHub step outputs `python-path` and `iscc-path`. Existing-interpreter/compiler options are for local probes and are marked as not download-attested.

```powershell
./scripts/prepare_ci_tools.ps1
$tools = Get-Content ci/tools.json -Raw | ConvertFrom-Json
./scripts/ci_build.ps1 -Phase Build -Python $tools.python -Iscc $tools.iscc
# Local probe using an already prepared exact-version environment:
./scripts/ci_build.ps1 -Phase Build -Python .venv/Scripts/python.exe -Iscc installer/tools/InnoSetup/ISCC.exe -UseExistingEnvironment
```

`sign-release.yml` is manual-only and restricted to trusted main source. It deliberately fails before signing until repository variables are configured: `SIGNPATH_ENABLED=true`, `SIGNPATH_ORGANIZATION_ID`, `SIGNPATH_PROJECT_SLUG`, `SIGNPATH_SIGNING_POLICY_SLUG`, `SIGNPATH_APPLICATION_CONFIGURATION_SLUG`, `SIGNPATH_INSTALLER_CONFIGURATION_SLUG`, and public `SIGNPATH_CERTIFICATE_THUMBPRINT`. The GitHub environment `signpath-release` must already exist, require a manual reviewer, and allow exactly the `main` branch; readiness verifies these protections using read-only GitHub API calls. Put `SIGNPATH_API_TOKEN` only in that environment after external SignPath approval. Configure the SignPath project with the GitHub trusted-build connector, verified repository/main origin, the approved certificate and a manually approved signing policy. A repository variable is an operator opt-in, not proof that the Foundation has approved a project.

Import `signing/artifact-configuration.xml` and `signing/installer-artifact-configuration.xml` as the two corresponding SignPath configurations. Both have ZIP roots because `upload-artifact@v4` wraps the single EXE; pass `version` from the reviewed source. Stage one signs only `PDFMaster.exe` after it has been uploaded to GitHub. Windows must report `Valid`, the expected certificate thumbprint and a timestamp before this EXE replaces the unsigned one. The workflow then compiles Inno around that signed payload, uploads the unsigned outer installer, and makes a second SignPath request. Before any signed artifact upload, it verifies both signatures again, checks every other payload file is byte-identical, reruns the frozen self-test and refreshes the source/build manifest. The generated **Inno uninstaller is not signed by this pipeline**; upstream DLLs are never re-signed with the project's certificate. No GitHub Release is automatically published, including after successful verification.

`ci_build.ps1 -Phase Installer` uses `build.ps1 -SkipFreeze -SkipManifest`; it requires the already signed own EXE and unchanged upstream hashes. `-Phase VerifySigned` accepts no unsigned/test-certificate result as a successful release. Live SignPath requests, policy approvals and signed output validation remain untested until genuine service credentials and configuration are available.

Primary references: [SignPath GitHub origin verification](https://docs.signpath.io/trusted-build-systems/github), [artifact syntax](https://docs.signpath.io/artifact-configuration/syntax), [supported formats](https://docs.signpath.io/artifact-configuration/reference), [GitHub environment protections](https://docs.github.com/en/rest/deployments/environments).

Local preparation validation completed on 2026-10-18: official pinned archives downloaded, hashes checked, Inno Authenticode checked, and both toolchains launched. Both workflows passed actionlint 1.7.11; both artifact configurations passed the official SignPath v1 XSD using .NET XmlSchemaSet. Nine dedicated CI/security checks and four subtests passed, including same-length download corruption rejection. A full local `ci_build.ps1 -Phase Build -UseExistingEnvironment` run passed 99 tests and 76 subtests, froze all ten runtime modules with source equality, compiled the unsigned installer, and passed all nine frozen self-test groups with `PATH=System32` and an invalid `TESSDATA_PREFIX`. One unrelated Windows symlink fixture was skipped because the local account lacks symlink privilege. The signing verification phase correctly rejected the unsigned EXE. These are local results; GitHub-hosted execution and live SignPath requests require separate evidence.
