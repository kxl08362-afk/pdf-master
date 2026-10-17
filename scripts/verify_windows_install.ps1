param(
    [string]$Version = '0.3.0',
    [switch]$CheckOnly
)
# Release QA only: never run against an existing installation or shortcut.
$ErrorActionPreference = 'Stop'
$taskProject = Split-Path -Parent $PSScriptRoot
$taskGuid = '{519E1AB0-9E92-42A6-B9F1-2B412B693910}_is1'
$taskUserKey = 'HKCU:/Software/Microsoft/Windows/CurrentVersion/Uninstall/' + $taskGuid
$taskKeys = @(
    $taskUserKey,
    ('HKLM:/Software/Microsoft/Windows/CurrentVersion/Uninstall/' + $taskGuid),
    ('HKLM:/Software/WOW6432Node/Microsoft/Windows/CurrentVersion/Uninstall/' + $taskGuid)
)
$taskShortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'PDF Мастер.lnk'
$taskDefault = Join-Path $env:LOCALAPPDATA 'Programs/PDFMaster/PDFMaster.exe'
$taskExisting = @($taskKeys | Where-Object { Test-Path -LiteralPath $_ })
$taskRunning = @(Get-Process -Name PDFMaster -ErrorAction SilentlyContinue)
if ($taskExisting.Count -or $taskRunning.Count -or (Test-Path -LiteralPath $taskDefault) -or (Test-Path -LiteralPath $taskShortcut)) {
    throw 'Existing PDFMaster installation, process, or Start menu shortcut found; QA stopped without changing it.'
}
if ($CheckOnly) {
    [pscustomobject]@{ ExistingInstall = $false; RunningApp = $false; ExistingShortcut = $false; SafeForIsolatedTest = $true } | ConvertTo-Json
    return
}

$taskInstaller = Join-Path $taskProject "dist/installers/PDFMaster-Setup-$Version.exe"
if (-not (Test-Path -LiteralPath $taskInstaller)) { throw "Installer not found: $taskInstaller" }
$taskBuild = Get-Content -LiteralPath (Join-Path $taskProject 'dist/build-manifest.json') -Raw | ConvertFrom-Json
$taskInstallerHash = (Get-FileHash -LiteralPath $taskInstaller -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskInstallerHash -ne $taskBuild.installer.sha256) { throw 'Installer checksum differs from build manifest.' }
$taskQa = Join-Path $taskProject ('qa/install-' + $Version + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
$taskTarget = Join-Path $taskQa 'PDFMaster'
New-Item -ItemType Directory -Path $taskQa | Out-Null
$taskReportPath = Join-Path $taskQa 'installation.json'
$taskReport = [ordered]@{
    version = $Version; installer_sha256 = $taskInstallerHash; isolated_directory = $taskTarget
    preexisting_install = $false; installation_exit = $null; selftest_exit = $null
    screenshot_exit = $null; uninstall_exit = $null; ok = $false
}
$taskInstalled = $false
$taskFailure = $null

function Invoke-PdfMasterQaProcess {
    param([string]$Executable, [string[]]$Arguments, [string]$LogName, [int]$TimeoutSeconds = 90)
    $taskProcess = Start-Process -FilePath $Executable -ArgumentList $Arguments -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $taskQa "$LogName.stdout.txt") `
        -RedirectStandardError (Join-Path $taskQa "$LogName.stderr.txt")
    if (-not $taskProcess.WaitForExit($TimeoutSeconds * 1000)) {
        # Stop only this process object/handle, never an unrelated application.
        $taskProcess.Kill()
        throw "QA process timed out: $LogName"
    }
    $taskProcess.Refresh()
    return $taskProcess.ExitCode
}

try {
    $taskReport.installation_exit = Invoke-PdfMasterQaProcess $taskInstaller @(
        '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
        ('/DIR="' + $taskTarget + '"'), ('/LOG="' + (Join-Path $taskQa 'install.log') + '"')
    ) 'installer'
    $taskExe = Join-Path $taskTarget 'PDFMaster.exe'
    $taskInstalled = Test-Path -LiteralPath (Join-Path $taskTarget 'unins000.exe')
    if ($taskReport.installation_exit -ne 0 -or -not (Test-Path -LiteralPath $taskExe)) { throw 'Isolated installation failed.' }
    $taskRegistration = Get-ItemProperty -LiteralPath $taskUserKey
    if ($taskRegistration.DisplayVersion -ne $Version -or $taskRegistration.InstallLocation.TrimEnd('\') -ne $taskTarget.TrimEnd('\')) {
        throw 'Unexpected uninstall registration after installation.'
    }
    if (-not (Test-Path -LiteralPath $taskShortcut)) { throw 'Start menu shortcut missing.' }
    $taskShell = New-Object -ComObject WScript.Shell
    $taskLink = $taskShell.CreateShortcut($taskShortcut)
    $taskReport.shortcut_target = $taskLink.TargetPath
    if ($taskLink.TargetPath -ne $taskExe) { throw 'Start menu shortcut points to a different executable.' }
    $taskReport.installation_version = (Get-Item -LiteralPath $taskExe).VersionInfo.FileVersion
    $taskSelfTest = Join-Path $taskQa 'selftest.json'
    $taskSavedPath = $env:PATH
    $taskSavedTess = $env:TESSDATA_PREFIX
    try {
        $env:PATH = Join-Path $env:WINDIR 'System32'
        $env:TESSDATA_PREFIX = Join-Path $taskQa 'nonexistent-tessdata'
        $taskReport.selftest_exit = Invoke-PdfMasterQaProcess $taskExe @('--self-test', ('"' + $taskSelfTest + '"')) 'selftest'
        $taskResult = Get-Content -LiteralPath $taskSelfTest -Raw | ConvertFrom-Json
        if ($taskReport.selftest_exit -ne 0 -or -not $taskResult.ok -or -not $taskResult.frozen) { throw 'Installed standalone self-test failed.' }
        $taskReport.selftest_checks = @($taskResult.checks)
        $taskSample = Join-Path $taskResult.evidence 'filled-form.pdf'
        $taskScreenshot = Join-Path $taskQa 'installed-window.png'
        $taskReport.screenshot_exit = Invoke-PdfMasterQaProcess $taskExe @('--open', ('"' + $taskSample + '"'), '--screenshot', ('"' + $taskScreenshot + '"')) 'screenshot' 30
        if ($taskReport.screenshot_exit -ne 0 -or -not (Test-Path -LiteralPath $taskScreenshot)) { throw 'Installed application screenshot failed.' }
        $taskReport.screenshot = $taskScreenshot
        # Deliberately place a user-created document inside the install folder:
        # Inno uninstall should remove only its own tracked application files.
        $taskUserDocument = Join-Path $taskTarget 'user-created-document.pdf'
        Copy-Item -LiteralPath $taskSample -Destination $taskUserDocument
        $taskReport.user_document = $taskUserDocument
        $taskReport.user_document_sha256 = (Get-FileHash -LiteralPath $taskUserDocument -Algorithm SHA256).Hash
    } finally {
        $env:PATH = $taskSavedPath
        $env:TESSDATA_PREFIX = $taskSavedTess
    }
} catch {
    $taskFailure = $_
    $taskReport.error = $_.Exception.Message
} finally {
    if ($taskInstalled) {
        try {
            $taskReport.uninstall_exit = Invoke-PdfMasterQaProcess (Join-Path $taskTarget 'unins000.exe') @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') 'uninstall'
            for ($taskRetry = 0; $taskRetry -lt 20 -and (Test-Path -LiteralPath (Join-Path $taskTarget 'PDFMaster.exe')); $taskRetry++) { Start-Sleep -Milliseconds 150 }
            $taskReport.app_removed = -not (Test-Path -LiteralPath (Join-Path $taskTarget 'PDFMaster.exe'))
            $taskReport.registry_removed = -not (Test-Path -LiteralPath $taskUserKey)
            $taskReport.shortcut_removed = -not (Test-Path -LiteralPath $taskShortcut)
            if ($taskReport.user_document) {
                $taskReport.user_document_preserved = (Test-Path -LiteralPath $taskReport.user_document) -and `
                    ((Get-FileHash -LiteralPath $taskReport.user_document -Algorithm SHA256).Hash -eq $taskReport.user_document_sha256)
            }
            if ($taskReport.uninstall_exit -ne 0 -or -not $taskReport.app_removed -or -not $taskReport.registry_removed -or -not $taskReport.shortcut_removed) {
                throw 'Uninstall did not completely remove the tracked test application.'
            }
            if ($taskReport.user_document -and -not $taskReport.user_document_preserved) { throw 'Uninstall changed the user-created document.' }
        } catch {
            if (-not $taskFailure) { $taskFailure = $_ }
            $taskReport.uninstall_error = $_.Exception.Message
        }
    }
    $taskReport.ok = -not [bool]$taskFailure
    $taskReport | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $taskReportPath -Encoding utf8
}
$taskReport | ConvertTo-Json -Depth 6
if ($taskFailure) { throw $taskFailure }
