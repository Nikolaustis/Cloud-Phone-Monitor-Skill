param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("UgPhone", "VSPhone", "Redfinger", "LDCloud")]
    [string]$Platform,
    [string]$SkillRoot = (Split-Path -Parent $MyInvocation.MyCommand.Path)
)

$ErrorActionPreference = "Stop"

function Resolve-PythonExe {
    $candidates = @("C:\Python314\python.exe", "C:\Python313\python.exe", "C:\Python312\python.exe")
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Python executable not found. Run INSTALL.ps1 -InstallDependencies after installing Python 3.12+."
}

function Quote-ProcessArgument([string]$Value) {
    if ($null -eq $Value) { return '""' }
    return '"' + ($Value -replace '"', '\"') + '"'
}

function Read-StatusFile([string]$Path) {
    if (!(Test-Path $Path)) { return $null }
    try {
        return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-LastLogLines([string]$Path, [int]$Count = 30) {
    if (!(Test-Path $Path)) { return @() }
    try { return @(Get-Content -LiteralPath $Path -Tail $Count) } catch { return @() }
}

$SkillRoot = (Resolve-Path -LiteralPath $SkillRoot).Path
$PythonExe = Resolve-PythonExe
$AuthDir = Join-Path $SkillRoot "output\auth"
New-Item -ItemType Directory -Force -Path $AuthDir | Out-Null

$helperPath = Join-Path $SkillRoot "cloud_phone_monitor\login_wait_for_signal.py"
if (!(Test-Path $helperPath)) {
    throw "Login helper is missing: $helperPath. Re-run INSTALL.ps1 from the current source package."
}

& $PythonExe -c "import playwright" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Playwright is not available for $PythonExe. Run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1 -InstallDependencies"
}

$slug = switch ($Platform) {
    "UgPhone" { "ugphone" }
    "VSPhone" { "vsphone" }
    "Redfinger" { "redfinger" }
    "LDCloud" { "ldcloud" }
}

$StatePath = Join-Path $AuthDir ("{0}_state.json" -f $slug)
$SignalPath = Join-Path $AuthDir ("{0}_login_complete.signal" -f $slug)
$StatusPath = Join-Path $AuthDir ("{0}_login_status.json" -f $slug)
$StdoutPath = Join-Path $AuthDir ("{0}_login_stdout.log" -f $slug)
$StderrPath = Join-Path $AuthDir ("{0}_login_stderr.log" -f $slug)

foreach ($path in @($SignalPath, $StatusPath, $StdoutPath, $StderrPath)) {
    if (Test-Path $path) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
}

$arguments = @(
    "-m", "cloud_phone_monitor.login_wait_for_signal",
    "--platform", $Platform,
    "--save-storage-state", $StatePath,
    "--signal-file", $SignalPath,
    "--status-file", $StatusPath
)

if ($Platform -eq "UgPhone") {
    $arguments += @(
        "--persistent-profile", (Join-Path $AuthDir "ugphone_profile"),
        "--runtime-context", (Join-Path $AuthDir "ugphone_runtime_context.json")
    )
}

$argumentLine = ($arguments | ForEach-Object { Quote-ProcessArgument ([string]$_) }) -join " "

Write-Host "============================================================"
Write-Host "Cloud Phone Monitor - Local Login"
Write-Host "============================================================"
Write-Host "Platform:   $Platform"
Write-Host "Skill root: $SkillRoot"
Write-Host ""
Write-Host "Starting a LOCAL Playwright Chromium browser..."
Write-Host ""
Write-Host "IMPORTANT:"
Write-Host "- Complete the login only in the Chromium window opened by this command."
Write-Host "- Do NOT complete this login in ChatGPT Work / Cloud Browser."
Write-Host "- Cloud Browser cookies/localStorage/sessionStorage are isolated from this local collector."
Write-Host ""

$process = Start-Process `
    -FilePath $PythonExe `
    -ArgumentList $argumentLine `
    -WorkingDirectory $SkillRoot `
    -RedirectStandardOutput $StdoutPath `
    -RedirectStandardError $StderrPath `
    -PassThru

try {
    $startupDeadline = (Get-Date).AddSeconds(90)
    $ready = $false
    while ((Get-Date) -lt $startupDeadline) {
        if ($process.HasExited) { break }
        $status = Read-StatusFile $StatusPath
        if ($null -ne $status -and $status.status -eq "waiting_for_user_signal") {
            $ready = $true
            break
        }
        Start-Sleep -Milliseconds 500
    }

    if (-not $ready) {
        if (-not $process.HasExited) {
            try { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } catch {}
        }
        $stderrTail = Get-LastLogLines $StderrPath
        $details = if ($stderrTail.Count -gt 0) { "`n" + ($stderrTail -join "`n") } else { "" }
        throw "The local login browser did not become ready within 90 seconds.$details"
    }

    Write-Host "Local Chromium is ready."
    Write-Host "Complete the $Platform login in that window and KEEP the browser open."
    Write-Host ""
    [void](Read-Host "After login is complete, press Enter here to verify and save the login state")

    New-Item -ItemType File -Force -Path $SignalPath | Out-Null
    Write-Host ""
    Write-Host "Verifying and saving local login state..."

    $finishDeadline = (Get-Date).AddMinutes(6)
    while (-not $process.HasExited -and (Get-Date) -lt $finishDeadline) {
        Start-Sleep -Milliseconds 500
        $process.Refresh()
    }
    if (-not $process.HasExited) {
        try { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } catch {}
        throw "Login verification did not finish within 6 minutes. Inspect $StatusPath and retry .\LOGIN.ps1 $Platform."
    }

    $finalStatus = Read-StatusFile $StatusPath
    if ($null -eq $finalStatus) {
        $stderrTail = Get-LastLogLines $StderrPath
        $details = if ($stderrTail.Count -gt 0) { "`n" + ($stderrTail -join "`n") } else { "" }
        throw "Login helper exited without a readable status file.$details"
    }

    if ($process.ExitCode -ne 0 -or $finalStatus.status -ne "saved_and_verified") {
        $reason = $null
        if ($null -ne $finalStatus.verification_after_reopen_task_equivalent) {
            $reason = $finalStatus.verification_after_reopen_task_equivalent.reason
        }
        if ([string]::IsNullOrWhiteSpace([string]$reason) -and $null -ne $finalStatus.verification_before_save) {
            $reason = $finalStatus.verification_before_save.reason
        }
        if ([string]::IsNullOrWhiteSpace([string]$reason) -and $null -ne $finalStatus.error) {
            $reason = $finalStatus.error
        }
        if ([string]::IsNullOrWhiteSpace([string]$reason)) {
            $reason = [string]$finalStatus.status
        }
        throw "$Platform login state was not saved and verified: $reason. Retry .\LOGIN.ps1 $Platform and finish the login in the local Chromium window."
    }

    Write-Host ""
    Write-Host "[OK] $Platform login state saved."
    Write-Host "[OK] Storage state: $StatePath"
    if ($Platform -eq "UgPhone") {
        Write-Host "[OK] Persistent profile: $(Join-Path $AuthDir 'ugphone_profile')"
        Write-Host "[OK] Runtime context: $(Join-Path $AuthDir 'ugphone_runtime_context.json')"
        Write-Host "[OK] Persistent profile reopened and verified in scheduled-task/headless mode."
    } else {
        Write-Host "[OK] Local Playwright state was saved after the platform page verification step."
        Write-Host "     Note: platform-specific live-auth verification is currently stricter for UgPhone than for $Platform."
    }
    Write-Host ""
    Write-Host "Auth files are private local data. Do not upload output/auth/ to GitHub."
} finally {
    if (Test-Path $SignalPath) {
        Remove-Item -LiteralPath $SignalPath -Force -ErrorAction SilentlyContinue
    }
}
