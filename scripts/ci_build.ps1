param(
    [ValidateSet('Build', 'Installer', 'VerifySigned')][string]$Phase = 'Build',
    [Parameter(Mandatory)][string]$Python,
    [string]$Iscc,
    [switch]$UseExistingEnvironment,
    [string]$ExpectedThumbprint
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
New-Item -ItemType Directory -Path ci/qa -Force | Out-Null
$versionMatch = [regex]::Match([IO.File]::ReadAllText((Join-Path $root 'installer/PDFMaster.iss')), '#define AppVersion "([0-9]+\.[0-9]+\.[0-9]+)"')
if (-not $versionMatch.Success) { throw 'Installer version must be an explicit numeric major.minor.patch.' }
$version = $versionMatch.Groups[1].Value
$application = Join-Path $root 'dist/PDFMaster/PDFMaster.exe'
$installer = Join-Path $root "dist/installers/PDFMaster-Setup-$version.exe"
$venvPython = Join-Path $root '.venv/Scripts/python.exe'

function Assert-ExitCode {
    param([string]$Operation)
    if ($LASTEXITCODE -ne 0) { throw "$Operation failed with exit code $LASTEXITCODE" }
}
function Assert-CodeSignature {
    param([string]$Path)
    if ($ExpectedThumbprint -notmatch '^[A-Fa-f0-9]{40}$') { throw 'Set the approved public SIGNPATH_CERTIFICATE_THUMBPRINT (40 hex digits).' }
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Thumbprint -ne $ExpectedThumbprint -or $null -eq $signature.TimeStamperCertificate) {
        throw "Authenticode must be Valid, timestamped, and use the approved certificate: $([IO.Path]::GetFileName($Path))"
    }
    return [ordered]@{ status = [string]$signature.Status; signer_thumbprint = $signature.SignerCertificate.Thumbprint; timestamp_thumbprint = $signature.TimeStamperCertificate.Thumbprint }
}
function Get-PayloadHashes {
    $appRoot = Join-Path $root 'dist/PDFMaster'
    $hashes = [ordered]@{}
    foreach ($file in (Get-ChildItem -LiteralPath $appRoot -Recurse -File | Sort-Object FullName)) {
        $name = [IO.Path]::GetRelativePath($appRoot, $file.FullName).Replace('\', '/')
        $hashes[$name] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    return $hashes
}
function Assert-UpstreamUnchanged {
    $baseline = Get-Content -LiteralPath ci/payload-hashes.json -Raw | ConvertFrom-Json -AsHashtable
    $current = Get-PayloadHashes
    if ($baseline.Count -ne $current.Count) { throw 'Signing changed the set of packaged files.' }
    foreach ($name in $baseline.Keys) {
        if (-not $current.Contains($name)) { throw "Packaged file missing after signing: $name" }
        if ($name -ne 'PDFMaster.exe' -and $baseline[$name] -ne $current[$name]) { throw "Upstream/package file changed during signing: $name" }
    }
}
function Invoke-FrozenSelfTest {
    param([string]$Label)
    $report = Join-Path $root "ci/qa/frozen-$Label.json"
    $savedPath = $env:PATH
    $savedTess = $env:TESSDATA_PREFIX
    try {
        $env:PATH = Join-Path $env:WINDIR 'System32'
        $env:TESSDATA_PREFIX = Join-Path $root 'ci/nonexistent-tessdata'
        $process = Start-Process -FilePath $application -ArgumentList @('--self-test', ('"' + $report + '"')) -WindowStyle Hidden -PassThru -RedirectStandardOutput "ci/qa/frozen-$Label.stdout.txt" -RedirectStandardError "ci/qa/frozen-$Label.stderr.txt"
        if (-not $process.WaitForExit(120000)) { $process.Kill(); throw 'Frozen self-test timed out.' }
        $process.Refresh()
        if ($process.ExitCode -ne 0) { throw "Frozen self-test exit code $($process.ExitCode)." }
        $result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
        if (-not $result.ok -or -not $result.frozen) { throw 'Frozen self-test did not confirm success.' }
    } finally {
        $env:PATH = $savedPath
        $env:TESSDATA_PREFIX = $savedTess
    }
}

if ($Phase -ne 'VerifySigned') {
    if (-not $UseExistingEnvironment) {
        & $Python -m venv .venv
        Assert-ExitCode 'Create build venv'
        & $venvPython -m pip install --disable-pip-version-check -r requirements-dev.txt
        Assert-ExitCode 'Install pinned dependencies'
    }
    if (-not (Test-Path -LiteralPath $venvPython)) { throw 'Existing build environment not found.' }
    $actualVersion = & $venvPython -c 'import json,platform,sys; print(json.dumps({"version":platform.python_version(),"bits":64 if sys.maxsize>2**32 else 32}))'
    Assert-ExitCode 'Read build Python version'
    $actualFacts = $actualVersion | ConvertFrom-Json
    if ($actualFacts.version -ne '3.12.14' -or $actualFacts.bits -ne 64) { throw 'Build environment must use CPython 3.12.14 x64.' }
    & $venvPython -m pip check
    Assert-ExitCode 'Dependency check'
}

switch ($Phase) {
    'Build' {
        $env:QT_QPA_PLATFORM = 'offscreen'
        & $venvPython -m pytest tests -q --junitxml=ci/qa/tests.xml
        Assert-ExitCode 'Tests'
        & "$root/build.ps1" -Python $venvPython -Iscc $Iscc
        if ((Get-AuthenticodeSignature -LiteralPath $application).Status -ne 'NotSigned' -or (Get-AuthenticodeSignature -LiteralPath $installer).Status -ne 'NotSigned') {
            throw 'Unsigned CI unexpectedly produced a signed artifact; inspect the toolchain.'
        }
        Invoke-FrozenSelfTest 'unsigned'
        Get-PayloadHashes | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath ci/payload-hashes.json -Encoding utf8
        $provenance = [ordered]@{
            version = $version; signed = $false
            repository = $env:GITHUB_REPOSITORY; commit = $env:GITHUB_SHA; ref = $env:GITHUB_REF
            run_id = $env:GITHUB_RUN_ID; run_attempt = $env:GITHUB_RUN_ATTEMPT
            runner = $env:RUNNER_OS; runner_environment = $env:RUNNER_ENVIRONMENT
            origin_note = 'Claims for inspection; SignPath independently verifies GitHub artifact origin through its connector.'
        }
        $provenance | ConvertTo-Json | Set-Content -LiteralPath ci/provenance.json -Encoding utf8
    }
    'Installer' {
        Assert-CodeSignature $application | Out-Null
        Assert-UpstreamUnchanged
        & "$root/build.ps1" -Python $venvPython -Iscc $Iscc -SkipFreeze -SkipManifest
        Invoke-FrozenSelfTest 'signed-application'
    }
    'VerifySigned' {
        $signatures = [ordered]@{ application = (Assert-CodeSignature $application); installer = (Assert-CodeSignature $installer) }
        Assert-UpstreamUnchanged
        Invoke-FrozenSelfTest 'signed-final'
        & $venvPython scripts/build_manifest.py
        Assert-ExitCode 'Signed source/manifest verification'
        $signatures | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath ci/qa/signatures.json -Encoding utf8
    }
}
if ($env:GITHUB_OUTPUT) { "version=$version" | Add-Content -LiteralPath $env:GITHUB_OUTPUT -Encoding utf8 }
Write-Output "CI phase $Phase completed for $version; no release was published."
