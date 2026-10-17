[CmdletBinding(DefaultParameterSetName = 'Bootstrap')]
param(
    [Parameter(ParameterSetName = 'Bootstrap')][string]$ToolsDirectory = "$PSScriptRoot/../.ci-tools",
    [Parameter(ParameterSetName = 'Bootstrap')][string]$ExistingPython,
    [Parameter(ParameterSetName = 'Bootstrap')][string]$ExistingIscc,
    [Parameter(ParameterSetName = 'Bootstrap')][string]$OutputFile = "$PSScriptRoot/../ci/tools.json",
    [Parameter(Mandatory, ParameterSetName = 'Verify')][switch]$VerifyOnly,
    [Parameter(Mandatory, ParameterSetName = 'Verify')][string]$File,
    [Parameter(Mandatory, ParameterSetName = 'Verify')][ValidatePattern('^[A-Fa-f0-9]{64}$')][string]$ExpectedSha256
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-FileSha256 {
    param([string]$LiteralPath, [string]$Expected)
    if (-not (Test-Path -LiteralPath $LiteralPath -PathType Leaf)) { throw "Tool file missing: $LiteralPath" }
    $digest = (Get-FileHash -LiteralPath $LiteralPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($digest -ne $Expected.ToLowerInvariant()) { throw "SHA256 mismatch: $([IO.Path]::GetFileName($LiteralPath))" }
    return $digest
}
if ($VerifyOnly) {
    [pscustomobject]@{ sha256 = (Assert-FileSha256 $File $ExpectedSha256); verified = $true } | ConvertTo-Json
    return
}

# PSF/actions/setup-python do not publish a Windows 3.12.14 security-release
# binary. Use Astral's official immutable Windows build, not a floating uv install.
# Upstream sources/licenses: https://github.com/astral-sh/python-build-standalone
# Release: https://github.com/astral-sh/python-build-standalone/releases/tag/20260901
$pythonUrl = 'https://github.com/astral-sh/python-build-standalone/releases/download/20260901/cpython-3.12.14%2B20260901-x86_64-pc-windows-msvc-install_only.tar.gz'
$pythonHash = 'e90c1b6419da3bd812dd73bb3de40287a21abf153438147639ec5e20375ea93f'
$innoUrl = 'https://github.com/jrsoftware/issrc/releases/download/is-6_2_2/innosetup-6.2.2.exe'
$innoHash = '8117d10d00a2ad33a1390978ea3872861c330e087914410a6377b22c4c5b8563'
$innoSigner = 'D08557D0054C36122483EB0EFC58D1B47D72630C'
$toolRoot = [IO.Path]::GetFullPath($ToolsDirectory)
New-Item -ItemType Directory -Path $toolRoot -Force | Out-Null

function Get-PinnedDownload {
    param([string]$Url, [string]$Destination, [string]$Sha256)
    if (-not (Test-Path -LiteralPath $Destination)) {
        $partial = $Destination + '.partial'
        Invoke-WebRequest -Uri $Url -OutFile $partial
        Assert-FileSha256 $partial $Sha256 | Out-Null
        Move-Item -LiteralPath $partial -Destination $Destination
    }
    Assert-FileSha256 $Destination $Sha256 | Out-Null
}

if ($ExistingPython) {
    $python = (Resolve-Path -LiteralPath $ExistingPython).Path
    $pythonOrigin = 'existing-local-interpreter; not a CI download attestation'
} else {
    $pythonArchive = Join-Path $toolRoot 'cpython-3.12.14-20260901-windows-x64.tar.gz'
    Get-PinnedDownload $pythonUrl $pythonArchive $pythonHash
    $pythonHome = Join-Path $toolRoot 'cpython-3.12.14-20260901'
    $python = Join-Path $pythonHome 'python/python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        New-Item -ItemType Directory -Path $pythonHome -Force | Out-Null
        & tar.exe -xzf $pythonArchive -C $pythonHome
        if ($LASTEXITCODE -ne 0) { throw 'Pinned Python archive extraction failed.' }
    }
    $pythonOrigin = $pythonUrl
}
$pythonFacts = & $python -c 'import json,platform,sys; print(json.dumps({"version":platform.python_version(),"bits":64 if sys.maxsize>2**32 else 32}))'
if ($LASTEXITCODE -ne 0) { throw 'Python bootstrap failed to launch.' }
$facts = $pythonFacts | ConvertFrom-Json
if ($facts.version -ne '3.12.14' -or $facts.bits -ne 64) { throw 'CI requires CPython 3.12.14 x64 exactly.' }

if ($ExistingIscc) {
    $iscc = (Resolve-Path -LiteralPath $ExistingIscc).Path
    $innoOrigin = 'existing-local-compiler; not a CI download attestation'
} else {
    $innoInstaller = Join-Path $toolRoot 'innosetup-6.2.2.exe'
    Get-PinnedDownload $innoUrl $innoInstaller $innoHash
    $signature = Get-AuthenticodeSignature -LiteralPath $innoInstaller
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Thumbprint -ne $innoSigner) {
        throw 'Pinned Inno Setup installer Authenticode/signing certificate verification failed.'
    }
    $innoHome = Join-Path $toolRoot 'InnoSetup-6.2.2'
    $iscc = Join-Path $innoHome 'ISCC.exe'
    if (-not (Test-Path -LiteralPath $iscc)) {
        $install = Start-Process -FilePath $innoInstaller -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CURRENTUSER', '/portable=1', '/NOICONS', ('/DIR="' + $innoHome + '"')) -WindowStyle Hidden -Wait -PassThru
        if ($install.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $iscc)) { throw 'Portable Inno Setup bootstrap failed.' }
    }
    $innoOrigin = $innoUrl
}
$result = [ordered]@{
    python = [IO.Path]::GetFullPath($python); python_version = $facts.version; python_origin = $pythonOrigin
    python_archive_sha256 = $pythonHash; python_archive_verified = -not [bool]$ExistingPython
    iscc = [IO.Path]::GetFullPath($iscc); inno_origin = $innoOrigin
    inno_installer_sha256 = $innoHash; inno_installer_verified = -not [bool]$ExistingIscc
}
$output = [IO.Path]::GetFullPath($OutputFile)
New-Item -ItemType Directory -Path (Split-Path -Parent $output) -Force | Out-Null
$result | ConvertTo-Json | Set-Content -LiteralPath $output -Encoding utf8
if ($env:GITHUB_OUTPUT) {
    "python-path=$($result.python)" | Add-Content -LiteralPath $env:GITHUB_OUTPUT -Encoding utf8
    "iscc-path=$($result.iscc)" | Add-Content -LiteralPath $env:GITHUB_OUTPUT -Encoding utf8
}
$result | ConvertTo-Json
