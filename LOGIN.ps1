param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("UgPhone", "VSPhone", "Redfinger", "LDCloud")]
    [string]$Platform,
    [switch]$Start,
    [switch]$Complete,
    [switch]$Status,
    [switch]$Cancel,
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

function Read-JsonFile([string]$Path) {
    if (!(Test-Path $Path)) { return $null }
    try {
        return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Write-JsonFile([string]$Path, [object]$Value) {
    $parent = Split-Path -Parent $Path
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    $Value | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 -LiteralPath $Path
}

function Get-LastLogLines([string]$Path, [int]$Count = 30) {
    if (!(Test-Path $Path)) { return @() }
    try { return @(Get-Content -LiteralPath $Path -Tail $Count) } catch { return @() }
}

function Get-RunningProcess([int]$ProcessId) {
    if ($ProcessId -le 0) { return $null }
    try {
        return Get-Process -Id $ProcessId -ErrorAction Stop
    } catch {
        return $null
    }
}

function Stop-LocalLoginProcess([int]$ProcessId) {
    if ($ProcessId -le 0) { return }
    $running = Get-RunningProcess $ProcessId
    if ($null -eq $running) { return }

    $taskkill = Get-Command taskkill.exe -ErrorAction SilentlyContinue
    if ($taskkill) {
        try {
            $taskkillPath = [string]$taskkill.Source
            & $taskkillPath /PID $ProcessId /T /F *> $null
            return
        } catch {}
    }
    try { Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue } catch {}
}

function Resolve-FailureReason([object]$FinalStatus) {
    if ($null -eq $FinalStatus) { return "missing_login_status" }
    $reason = $null
    if ($null -ne $FinalStatus.verification_after_reopen_task_equivalent) {
        $reason = $FinalStatus.verification_after_reopen_task_equivalent.reason
    }
    if ([string]::IsNullOrWhiteSpace([string]$reason) -and $null -ne $FinalStatus.verification_before_save) {
        $reason = $FinalStatus.verification_before_save.reason
    }
    if ([string]::IsNullOrWhiteSpace([string]$reason) -and $null -ne $FinalStatus.error) {
        $reason = $FinalStatus.error
    }
    if ([string]::IsNullOrWhiteSpace([string]$reason)) {
        $reason = [string]$FinalStatus.status
    }
    if ([string]::IsNullOrWhiteSpace([string]$reason)) {
        $reason = "unknown_login_failure"
    }
    return [string]$reason
}

$selectedModes = @()
if ($Start) { $selectedModes += "Start" }
if ($Complete) { $selectedModes += "Complete" }
if ($Status) { $selectedModes += "Status" }
if ($Cancel) { $selectedModes += "Cancel" }
if ($selectedModes.Count -gt 1) {
    throw "Choose only one mode: -Start, -Complete, -Status, or -Cancel. Omit all mode switches for interactive PowerShell login."
}
$Mode = if ($selectedModes.Count -eq 1) { $selectedModes[0] } else { "Interactive" }

$SkillRoot = (Resolve-Path -LiteralPath $SkillRoot).Path
$AuthDir = Join-Path $SkillRoot "output\auth"
New-Item -ItemType Directory -Force -Path $AuthDir | Out-Null

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
$ControlPath = Join-Path $AuthDir ("{0}_login_agent_session.json" -f $slug)

function Assert-LocalLoginRuntime {
    $helperPath = Join-Path $SkillRoot "cloud_phone_monitor\login_wait_for_signal.py"
    if (!(Test-Path $helperPath)) {
        throw "Login helper is missing: $helperPath. Re-run INSTALL.ps1 from the current source package."
    }

    $PythonExe = Resolve-PythonExe
    & $PythonExe -c "import playwright" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Playwright is not available for $PythonExe. Run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INSTALL.ps1 -InstallDependencies"
    }
    return $PythonExe
}

function Write-LocalLoginBanner {
    Write-Host "============================================================"
    Write-Host "Cloud Phone Monitor - Local Login"
    Write-Host "============================================================"
    Write-Host "Platform:   $Platform"
    Write-Host "Skill root: $SkillRoot"
    Write-Host "Mode:       $Mode"
    Write-Host ""
    Write-Host "IMPORTANT:"
    Write-Host "- Collector authentication is a LOCAL-EXECUTION workflow."
    Write-Host "- Complete the login only in the Playwright Chromium window opened by this script."
    Write-Host "- Do NOT use ChatGPT Work / Cloud Browser for collector authentication."
    Write-Host "- Cloud Browser cookies/localStorage/sessionStorage cannot become local output/auth/ state."
    Write-Host ""
}

function Start-LoginSession {
    $PythonExe = Assert-LocalLoginRuntime

    $existingControl = Read-JsonFile $ControlPath
    if ($null -ne $existingControl) {
        $existingProcessId = 0
        try { $existingProcessId = [int]$existingControl.process_id } catch {}
        $existingProcess = Get-RunningProcess $existingProcessId
        $existingStatus = Read-JsonFile $StatusPath
        if ($null -ne $existingProcess -and $null -ne $existingStatus -and $existingStatus.status -eq "waiting_for_user_signal") {
            throw "A $Platform login session is already waiting for the user. Finish the login in the existing local Chromium window, then run .\LOGIN.ps1 $Platform -Complete. Use -Cancel only if you want to discard that session."
        }
        if ($null -ne $existingProcess) {
            Stop-LocalLoginProcess $existingProcessId
        }
        Remove-Item -LiteralPath $ControlPath -Force -ErrorAction SilentlyContinue
    }

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

    Write-Host "Starting a LOCAL Playwright Chromium browser..."
    $process = Start-Process `
        -FilePath $PythonExe `
        -ArgumentList $argumentLine `
        -WorkingDirectory $SkillRoot `
        -RedirectStandardOutput $StdoutPath `
        -RedirectStandardError $StderrPath `
        -PassThru

    $startupDeadline = (Get-Date).AddSeconds(90)
    $ready = $false
    while ((Get-Date) -lt $startupDeadline) {
        $process.Refresh()
        if ($process.HasExited) { break }
        $statusValue = Read-JsonFile $StatusPath
        if ($null -ne $statusValue -and $statusValue.status -eq "waiting_for_user_signal") {
            $ready = $true
            break
        }
        Start-Sleep -Milliseconds 500
    }

    if (-not $ready) {
        $process.Refresh()
        if (-not $process.HasExited) {
            Stop-LocalLoginProcess ([int]$process.Id)
        }
        $stderrTail = Get-LastLogLines $StderrPath
        $details = if ($stderrTail.Count -gt 0) { "`n" + ($stderrTail -join "`n") } else { "" }
        throw "The local login browser did not become ready within 90 seconds.$details"
    }

    $control = [ordered]@{
        schema_version = 1
        platform = $Platform
        process_id = [int]$process.Id
        skill_root = $SkillRoot
        state_file = $StatePath
        signal_file = $SignalPath
        status_file = $StatusPath
        stdout_file = $StdoutPath
        stderr_file = $StderrPath
        started_at = (Get-Date).ToUniversalTime().ToString("o")
        state = "waiting_for_user"
    }
    Write-JsonFile $ControlPath $control

    Write-Host ""
    Write-Host "[OK] Local Chromium is ready."
    Write-Host "Complete the $Platform login in that window and KEEP the browser open."
    Write-Host ""
    Write-Host "LOGIN_AGENT_STATE=WAITING_FOR_USER"
    Write-Host "LOGIN_AGENT_PLATFORM=$Platform"
    Write-Host "LOGIN_AGENT_CONTROL=$ControlPath"
    Write-Host "LOGIN_AGENT_NEXT_COMMAND=.\LOGIN.ps1 $Platform -Complete"
    return [pscustomobject]$control
}

function Complete-LoginSession {
    $control = Read-JsonFile $ControlPath
    if ($null -eq $control) {
        $finalStatusWithoutControl = Read-JsonFile $StatusPath
        if ($null -ne $finalStatusWithoutControl -and $finalStatusWithoutControl.status -eq "saved_and_verified") {
            Write-SuccessSummary
            return
        }
        throw "No active two-stage $Platform login session was found. Start one with .\LOGIN.ps1 $Platform -Start."
    }

    if ([string]$control.platform -ne $Platform) {
        throw "Login control file platform mismatch: expected $Platform, found $($control.platform)."
    }

    $helperStatus = Read-JsonFile $StatusPath
    if ($null -ne $helperStatus -and $helperStatus.status -eq "saved_and_verified") {
        Remove-Item -LiteralPath $ControlPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $SignalPath -Force -ErrorAction SilentlyContinue
        Write-SuccessSummary
        return
    }

    $ProcessId = 0
    try { $ProcessId = [int]$control.process_id } catch {}
    $runningProcess = Get-RunningProcess $ProcessId
    if ($null -eq $runningProcess) {
        $stderrTail = Get-LastLogLines $StderrPath
        $details = if ($stderrTail.Count -gt 0) { "`n" + ($stderrTail -join "`n") } else { "" }
        Remove-Item -LiteralPath $ControlPath -Force -ErrorAction SilentlyContinue
        $reason = Resolve-FailureReason $helperStatus
        throw "The $Platform local login process is no longer running before completion. Status: $reason.$details"
    }

    if ($null -eq $helperStatus -or $helperStatus.status -ne "waiting_for_user_signal") {
        $reason = Resolve-FailureReason $helperStatus
        throw "The $Platform login session is not waiting for the user signal. Current status: $reason. Inspect $StatusPath or cancel/restart the session."
    }

    New-Item -ItemType File -Force -Path $SignalPath | Out-Null
    Write-Host "User completion signal sent. Verifying and saving local login state..."

    try {
        $finishDeadline = (Get-Date).AddMinutes(6)
        while ((Get-Date) -lt $finishDeadline) {
            $runningProcess = Get-RunningProcess $ProcessId
            if ($null -eq $runningProcess) { break }
            Start-Sleep -Milliseconds 500
        }

        $runningProcess = Get-RunningProcess $ProcessId
        if ($null -ne $runningProcess) {
            Stop-LocalLoginProcess $ProcessId
            throw "Login verification did not finish within 6 minutes. Inspect $StatusPath and retry .\LOGIN.ps1 $Platform -Start."
        }

        $finalStatus = Read-JsonFile $StatusPath
        if ($null -eq $finalStatus -or $finalStatus.status -ne "saved_and_verified") {
            $reason = Resolve-FailureReason $finalStatus
            $stderrTail = Get-LastLogLines $StderrPath
            $details = if ($stderrTail.Count -gt 0) { "`n" + ($stderrTail -join "`n") } else { "" }
            throw "$Platform login state was not saved and verified: $reason.$details"
        }

        Write-SuccessSummary
    } finally {
        Remove-Item -LiteralPath $SignalPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $ControlPath -Force -ErrorAction SilentlyContinue
    }
}

function Write-SuccessSummary {
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
    Write-Host "LOGIN_AGENT_STATE=SAVED_AND_VERIFIED"
    Write-Host "LOGIN_AGENT_PLATFORM=$Platform"
    Write-Host ""
    Write-Host "Auth files are private local data. Do not upload output/auth/ to GitHub."
}

function Show-LoginSessionStatus {
    $control = Read-JsonFile $ControlPath
    $helperStatus = Read-JsonFile $StatusPath

    Write-Host "Platform: $Platform"
    Write-Host "Control file: $ControlPath"
    if ($null -eq $control) {
        Write-Host "Agent session: none"
    } else {
        $ProcessId = 0
        try { $ProcessId = [int]$control.process_id } catch {}
        $running = $null -ne (Get-RunningProcess $ProcessId)
        Write-Host "Agent session: active=$running process_id=$ProcessId state=$($control.state)"
    }

    if ($null -eq $helperStatus) {
        Write-Host "Helper status: missing"
        Write-Host "LOGIN_AGENT_STATE=NO_SESSION"
    } else {
        Write-Host "Helper status: $($helperStatus.status)"
        if ($helperStatus.status -eq "waiting_for_user_signal") {
            Write-Host "LOGIN_AGENT_STATE=WAITING_FOR_USER"
        } elseif ($helperStatus.status -eq "saved_and_verified") {
            Write-Host "LOGIN_AGENT_STATE=SAVED_AND_VERIFIED"
        } else {
            Write-Host "LOGIN_AGENT_STATE=$($helperStatus.status)"
        }
    }
}

function Cancel-LoginSession {
    $control = Read-JsonFile $ControlPath
    if ($null -ne $control) {
        $ProcessId = 0
        try { $ProcessId = [int]$control.process_id } catch {}
        $runningProcess = Get-RunningProcess $ProcessId
        if ($null -ne $runningProcess) {
            Stop-LocalLoginProcess $ProcessId
        }
    }
    Remove-Item -LiteralPath $SignalPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ControlPath -Force -ErrorAction SilentlyContinue
    Write-Host "Cancelled local $Platform login session. Existing saved auth state was not deleted."
    Write-Host "LOGIN_AGENT_STATE=CANCELLED"
}

Write-LocalLoginBanner

switch ($Mode) {
    "Start" {
        [void](Start-LoginSession)
    }
    "Complete" {
        Complete-LoginSession
    }
    "Status" {
        Show-LoginSessionStatus
    }
    "Cancel" {
        Cancel-LoginSession
    }
    "Interactive" {
        [void](Start-LoginSession)
        [void](Read-Host "After login is complete, press Enter here to verify and save the login state")
        Complete-LoginSession
    }
    default {
        throw "Unsupported login mode: $Mode"
    }
}
