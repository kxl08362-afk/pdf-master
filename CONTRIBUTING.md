# Contributing

PDF Мастер is an offline Windows PDF application. Application-specific code is licensed under GNU AGPL-3.0-only; third-party components keep their own licenses. By submitting a contribution, offer your contribution under the same applicable project license and identify any third-party material you introduce. No copyright assignment or commercial relicense is requested by this document.

Discuss larger changes in an issue or pull request before expanding the interface or dependency set. Clear bug reports should identify the application version, Windows version, operation, expected result and a minimal reproduction. Use synthetic files: do not post real customer documents, passwords, signature images or personal data.

## Development

Use Windows 11 x64 and CPython 3.12 x64 for the supported build. From the repository root, create an isolated environment and install pinned dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe app.py
.\.venv\Scripts\python.exe -m pytest tests -q
```

Build instructions are in [installer/BUILD.md](installer/BUILD.md). Keep generated executables, temporary files, local credentials and user documents out of commits. A successful local test is not evidence that a GitHub build or signed release succeeded.

Read `openspec/specs` and active `openspec/changes` before nontrivial development. Keep a focused change, implement its stated behavior, verify it and update the relevant specification. Small obvious fixes do not require a separate planning ceremony.

## Review expectations

Preserve local document processing, explicit user control over file writes, undo behavior and supported PDF permissions. Changes affecting OCR, redaction, forms, image insertion, page rotation or crop coordinates need meaningful fixtures and saved-result checks. Text extraction alone cannot prove that a signature image or a Cyrillic form value is visible; rendering alone cannot prove that redacted content was removed.

Identify dependency versions, upstream sources, applicable notices and corresponding-source obligations in [THIRD_PARTY.md](THIRD_PARTY.md). Do not copy source from another project without checking its license and preserving required attribution. Changes to installers, dependencies, CI or signing files require particular attention because they determine what users install.

The current proposed maintainer/reviewer is [kxl08362-afk](https://github.com/kxl08362-afk). There is no claimed independent review team or guaranteed response schedule. Maintainer review is required for external contributions. Contributors who later receive repository or signing privileges must enable MFA for the relevant services before access is granted; their access must be documented in the [Code signing policy](CODE_SIGNING.md).

Signing service enrollment is pending. A pull request, CI pass or merged change does not authorize production signing. See [CODE_SIGNING.md](CODE_SIGNING.md) and [SECURITY.md](SECURITY.md).
