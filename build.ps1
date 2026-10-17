param(
    [string]$Python = "$PSScriptRoot/.venv/Scripts/python.exe",
    [string]$Iscc = "$PSScriptRoot/installer/tools/InnoSetup/ISCC.exe",
    [switch]$SkipFreeze,
    [switch]$FreezeOnly,
    [switch]$SkipManifest
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if ($SkipFreeze -and $FreezeOnly) { throw 'SkipFreeze and FreezeOnly are mutually exclusive.' }
if (-not (Test-Path -LiteralPath $Python)) {
    throw 'Python build environment missing. Create .venv and run pip install -r requirements.txt; end users do not need Python.'
}
if (-not $FreezeOnly -and -not (Test-Path -LiteralPath $Iscc)) {
    $taskIscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($taskIscc) { $Iscc = $taskIscc.Source }
    else { throw 'Inno Setup 6 compiler not found. Install or extract it and supply -Iscc C:/path/ISCC.exe. See installer/BUILD.md.' }
}
foreach ($taskRequired in @('app.py', 'resources/tessdata/rus.traineddata', 'resources/tessdata/eng.traineddata', 'resources/fonts/DejaVuSans.ttf', 'LICENSE.txt')) {
    if (-not (Test-Path -LiteralPath $taskRequired)) { throw "Missing required input: $taskRequired" }
}
if (-not $SkipFreeze) {
    & $Python -m PyInstaller --noconfirm --clean PDFMaster.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: $LASTEXITCODE" }
}
if ($FreezeOnly) { return }
& $Iscc installer/PDFMaster.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed: $LASTEXITCODE" }
if (-not $SkipManifest) {
    & $Python scripts/build_manifest.py
    if ($LASTEXITCODE -ne 0) { throw "Build source verification failed: $LASTEXITCODE" }
}
Get-FileHash -Algorithm SHA256 dist/installers/PDFMaster-Setup-0.3.0.exe
