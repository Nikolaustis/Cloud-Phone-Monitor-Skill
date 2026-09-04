param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("UgPhone", "VSPhone", "Redfinger", "LDCloud")]
    [string]$Platform,
    [switch]$Start,
    [switch]$Complete,
    [switch]$Status,
    [switch]$Cancel,
    [string]$SkillRoot = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($SkillRoot)) {
    if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        $SkillRoot = $PSScriptRoot
    } else {
        $scriptPath = $MyInvocation.MyCommand.Path
        if ([string]::IsNullOrWhiteSpace($scriptPath)) {
            throw "Unable to determine SkillRoot. Pass -SkillRoot explicitly."
        }
        $SkillRoot = Split-Path -Parent $scriptPath
    }
}
$SkillRoot = (Resolve-Path -LiteralPath $SkillRoot).Path

function Quote-Arg([string]$Value) {
    if ($null -eq $Value) { return '""' }
    if ($Value -notmatch '[\s"]') { return $Value }
    return '"' + (($Value -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
}

function Invoke-CapturedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [int]$TimeoutSeconds = 30
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = (($Arguments | ForEach-Object { Quote-Arg ([string]$_) }) -join " ")
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    try {
        if (-not $proc.Start()) {
            return [pscustomobject]@{ Started = $false; ExitCode = -1; Stdout = ""; Stderr = "process_start_returned_false" }
        }
        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            try { $proc.Kill() } catch {}
            return [pscustomobject]@{ Started = $true; ExitCode = -2; Stdout = $proc.StandardOutput.ReadToEnd(); Stderr = "probe_timeout" }
        }
        return [pscustomobject]@{
            Started = $true
            ExitCode = [int]$proc.ExitCode
            Stdout = $proc.StandardOutput.ReadToEnd()
            Stderr = $proc.StandardError.ReadToEnd()
        }
    } catch {
        return [pscustomobject]@{ Started = $false; ExitCode = -1; Stdout = ""; Stderr = $_.Exception.Message }
    } finally {
        try { $proc.Dispose() } catch {}
    }
}

function Resolve-PlaywrightPython {
    # LOGIN.ps1 never falls back to a system/PATH Python.  The dependency
    # installer is the only component allowed to discover a base interpreter;
    # all production/login/scheduled execution is pinned to this Skill .venv.
    $lockedVenv = Join-Path $SkillRoot ".venv\Scripts\python.exe"
    if (!(Test-Path $lockedVenv)) {
        throw @"
Dedicated Skill runtime is missing:
  $lockedVenv

Create/repair it with:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_dependencies_windows.ps1

Google Chrome is not required; the installer provisions Playwright Chromium.
"@
    }

    $probeCode = @'
import importlib.metadata as md, json, os, pathlib, sys
from playwright.sync_api import sync_playwright
expected = pathlib.Path(sys.argv[1]).resolve()
actual = pathlib.Path(sys.executable).resolve()
if os.path.normcase(str(expected)) != os.path.normcase(str(actual)):
    print(f"WRONG_PYTHON:{actual}")
    raise SystemExit(31)
p = sync_playwright().start()
try:
    browser_path = p.chromium.executable_path
    if not browser_path or not os.path.exists(browser_path):
        print("CHROMIUM_EXECUTABLE_MISSING")
        raise SystemExit(32)
    browser = p.chromium.launch(headless=True)
    browser.close()
finally:
    p.stop()
try:
    version = md.version("playwright")
except Exception:
    version = "unknown"
print("PYTHON=" + str(actual))
print("PYTHON_VERSION=" + sys.version.split()[0])
print("PLAYWRIGHT_VERSION=" + version)
print("CHROMIUM=" + str(browser_path))
print("LAUNCH_PROBE_OK=true")
'@

    $probeEncoded = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($probeCode))
    $probeRunner = "import base64;exec(base64.b64decode('$probeEncoded'))"
    $probe = Invoke-CapturedProcess -FilePath $lockedVenv -Arguments @("-c", $probeRunner, $lockedVenv) -TimeoutSeconds 60
    if (-not $probe.Started -or $probe.ExitCode -ne 0) {
        $detail = (($probe.Stdout + " " + $probe.Stderr).Trim() -replace "`r?`n", " | ")
        if ([string]::IsNullOrWhiteSpace($detail)) { $detail = "probe exit $($probe.ExitCode)" }
        throw @"
Dedicated Skill .venv exists, but Playwright Chromium cannot launch.
Runtime: $lockedVenv
Probe:   $detail

Repair with:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_dependencies_windows.ps1 -RecreateVenv
"@
    }

    $pythonLine = ($probe.Stdout -split "`r?`n" | Where-Object { $_ -like "PYTHON=*" } | Select-Object -First 1)
    $browserLine = ($probe.Stdout -split "`r?`n" | Where-Object { $_ -like "CHROMIUM=*" } | Select-Object -First 1)
    $pythonVersionLine = ($probe.Stdout -split "`r?`n" | Where-Object { $_ -like "PYTHON_VERSION=*" } | Select-Object -First 1)
    $playwrightVersionLine = ($probe.Stdout -split "`r?`n" | Where-Object { $_ -like "PLAYWRIGHT_VERSION=*" } | Select-Object -First 1)
    $runtime = [pscustomobject]@{
        PythonExe = if ($pythonLine) { $pythonLine.Substring(7).Trim() } else { $lockedVenv }
        PythonVersion = if ($pythonVersionLine) { $pythonVersionLine.Substring(15).Trim() } else { "unknown" }
        PlaywrightVersion = if ($playwrightVersionLine) { $playwrightVersionLine.Substring(19).Trim() } else { "unknown" }
        ChromiumPath = if ($browserLine) { $browserLine.Substring(9).Trim() } else { "" }
        LaunchProbeOk = $true
    }
    try {
        $runtimeDir = Join-Path $SkillRoot "output\runtime"
        New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
        [ordered]@{
            checked_at_utc = (Get-Date).ToUniversalTime().ToString("o")
            python_executable = $runtime.PythonExe
            python_version = $runtime.PythonVersion
            playwright_version = $runtime.PlaywrightVersion
            chromium_executable = $runtime.ChromiumPath
            launch_probe_ok = $true
            runtime_authority = "skill_venv_only"
        } | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $runtimeDir "python_environment.json")
    } catch {}
    return $runtime
}

function Read-JsonFile([string]$Path) {
    if (!(Test-Path $Path)) { return $null }
    try { return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json } catch { return $null }
}

function Write-JsonFile([string]$Path, [object]$Value) {
    $parent = Split-Path -Parent $Path
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    $sessionPart = ""
    try { $sessionPart = [string]$Value.session_id } catch {}
    if ([string]::IsNullOrWhiteSpace($sessionPart)) { $sessionPart = [Guid]::NewGuid().ToString("N") }
    $tmp = "$Path.tmp.$sessionPart"
    $json = $Value | ConvertTo-Json -Depth 16
    $utf8NoBom = New-Object System.Text.UTF8Encoding -ArgumentList $false
    [System.IO.File]::WriteAllText($tmp, $json, $utf8NoBom)
    try {
        [System.IO.File]::Replace($tmp, $Path, $null, $true)
    } catch {
        Move-Item -LiteralPath $tmp -Destination $Path -Force
    } finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
}

function Get-ProcessIdentity([int]$ProcessId) {
    if ($ProcessId -le 0) { return $null }
    try {
        $proc = Get-Process -Id $ProcessId -ErrorAction Stop
        $path = ""
        try { $path = [string]$proc.Path } catch {}
        if ([string]::IsNullOrWhiteSpace($path)) {
            try { $path = [string]$proc.MainModule.FileName } catch {}
        }
        $commandLine = ""
        try {
            $cim = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $ProcessId) -ErrorAction Stop
            if ($cim) { $commandLine = [string]$cim.CommandLine }
        } catch {}
        return [pscustomobject]@{
            process_id = [int]$proc.Id
            process_name = [string]$proc.ProcessName
            process_path = $path
            process_start_ticks = [int64]$proc.StartTime.ToUniversalTime().Ticks
            process_command_line = $commandLine
        }
    } catch {
        return $null
    }
}

function Test-ProcessIdentity([object]$Control) {
    if ($null -eq $Control) { return $false }
    $pidValue = 0
    try { $pidValue = [int]$Control.process_id } catch { return $false }
    $current = Get-ProcessIdentity $pidValue
    if ($null -eq $current) { return $false }

    $expectedTicks = 0L
    try { $expectedTicks = [int64]$Control.process_start_ticks } catch { return $false }
    if ($current.process_start_ticks -ne $expectedTicks) { return $false }

    $expectedPath = [string]$Control.process_path
    if ([string]::IsNullOrWhiteSpace($expectedPath) -or [string]::IsNullOrWhiteSpace($current.process_path)) { return $false }
    try {
        $expectedFull = [System.IO.Path]::GetFullPath($expectedPath)
        $currentFull = [System.IO.Path]::GetFullPath([string]$current.process_path)
        if (-not $expectedFull.Equals($currentFull, [System.StringComparison]::OrdinalIgnoreCase)) { return $false }
    } catch { return $false }

    $commandLine = [string]$current.process_command_line
    $sessionId = [string]$Control.session_id
    if ([string]::IsNullOrWhiteSpace($commandLine) -or [string]::IsNullOrWhiteSpace($sessionId)) { return $false }
    if ($commandLine -notlike "*cloud_phone_monitor.login_controller*") { return $false }
    if ($commandLine -notlike "*$sessionId*") { return $false }

    return $true
}

function Stop-ManagedProcess([object]$Control) {
    if (-not (Test-ProcessIdentity $Control)) {
        throw "Refusing to terminate process because PID/path/start-time identity does not match the active login session."
    }
    $pidValue = [int]$Control.process_id
    $taskkill = Get-Command taskkill.exe -ErrorAction SilentlyContinue
    if ($taskkill) {
        & $taskkill.Source /PID $pidValue /T /F *> $null
        return
    }
    Stop-Process -Id $pidValue -Force -ErrorAction Stop
}

$selectedModes = @()
if ($Start) { $selectedModes += "Start" }
if ($Complete) { $selectedModes += "Complete" }
if ($Status) { $selectedModes += "Status" }
if ($Cancel) { $selectedModes += "Cancel" }
if ($selectedModes.Count -gt 1) { throw "Choose only one mode: -Start, -Complete, -Status, or -Cancel." }
$Mode = if ($selectedModes.Count -eq 1) { $selectedModes[0] } else { "Interactive" }

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

function Start-LoginSession {
    $controllerPath = Join-Path $SkillRoot "cloud_phone_monitor\login_controller.py"
    if (!(Test-Path $controllerPath)) { throw "Login controller is missing: $controllerPath. Reinstall from a complete source package." }

    $oldControl = Read-JsonFile $ControlPath
    if ($null -ne $oldControl) {
        if (Test-ProcessIdentity $oldControl) {
            $oldStatus = Read-JsonFile $StatusPath
            if ($null -ne $oldStatus -and [string]$oldStatus.session_id -eq [string]$oldControl.session_id -and $oldStatus.status -eq "waiting_for_user_signal") {
                throw "A $Platform login session is already active. Finish it and run -Complete, or run -Cancel first."
            }
            Stop-ManagedProcess $oldControl
        }
        Remove-Item -LiteralPath $ControlPath -Force -ErrorAction SilentlyContinue
    }

    foreach ($path in @($SignalPath, $StatusPath, $StdoutPath, $StderrPath)) {
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    }

    $runtime = Resolve-PlaywrightPython
    $protocolProbe = Invoke-CapturedProcess -FilePath $runtime.PythonExe -Arguments @(
        "-c", "from cloud_phone_monitor.auth_session_contract import LOGIN_PROTOCOL_VERSION; print(LOGIN_PROTOCOL_VERSION)"
    ) -TimeoutSeconds 15
    if ($protocolProbe.ExitCode -ne 0) {
        throw "Unable to read LOGIN_PROTOCOL_VERSION from the dedicated Skill runtime: $($protocolProbe.Stderr.Trim())"
    }
    $protocolLine = ($protocolProbe.Stdout -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -Last 1).Trim()
    try { $protocolVersion = [int]$protocolLine } catch { throw "Invalid LOGIN_PROTOCOL_VERSION from Python runtime: $protocolLine" }

    $sessionId = [Guid]::NewGuid().ToString("D")
    $arguments = @(
        "-m", "cloud_phone_monitor.login_controller",
        "--platform", $Platform,
        "--session-id", $sessionId,
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

    $argumentLine = (($arguments | ForEach-Object { Quote-Arg ([string]$_) }) -join " ")
    $process = Start-Process -FilePath $runtime.PythonExe -ArgumentList $argumentLine -WorkingDirectory $SkillRoot `
        -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath -PassThru

    $identity = $null
    for ($i = 0; $i -lt 40 -and $null -eq $identity; $i++) {
        Start-Sleep -Milliseconds 100
        $candidateIdentity = Get-ProcessIdentity ([int]$process.Id)
        if ($null -eq $candidateIdentity) { continue }
        $candidateCommand = [string]$candidateIdentity.process_command_line
        if ($candidateCommand -like "*cloud_phone_monitor.login_controller*" -and $candidateCommand -like "*$sessionId*") {
            $identity = $candidateIdentity
        }
    }
    if ($null -eq $identity) {
        try { $process.Kill() } catch {}
        throw "Login controller started but its process identity could not be captured safely."
    }

    $control = [ordered]@{
        schema_version = $protocolVersion
        login_protocol_version = $protocolVersion
        session_id = $sessionId
        platform = $Platform
        skill_root = $SkillRoot
        python_executable = $runtime.PythonExe
        chromium_executable = $runtime.ChromiumPath
        process_id = $identity.process_id
        process_name = $identity.process_name
        process_path = $identity.process_path
        process_start_ticks = [string]$identity.process_start_ticks
        process_command_line = $identity.process_command_line
        started_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        state = "starting"
    }
    Write-JsonFile $ControlPath $control

    $deadline = (Get-Date).AddSeconds(130)
    while ((Get-Date) -lt $deadline) {
        $statusValue = Read-JsonFile $StatusPath
        if ($null -ne $statusValue) {
            if ([string]$statusValue.session_id -ne $sessionId) {
                try { Stop-ManagedProcess $control } catch {}
                throw "Login status session mismatch during startup."
            }
            if ($statusValue.status -eq "waiting_for_user_signal") {
                $control.state = "waiting_for_user"
                Write-JsonFile $ControlPath $control
                Write-Host "[OK] Local Playwright Chromium is ready."
                Write-Host "LOGIN_AGENT_STATE=WAITING_FOR_USER"
                Write-Host "LOGIN_AGENT_SESSION_ID=$sessionId"
                Write-Host "LOGIN_AGENT_NEXT_COMMAND=.\LOGIN.ps1 $Platform -Complete"
                return
            }
            if ($statusValue.status -in @("failed", "verification_failed", "verification_failed_after_reopen")) {
                try { Stop-ManagedProcess $control } catch {}
                $startupReason = if ($statusValue.error) { $statusValue.error } elseif ($statusValue.reason) { $statusValue.reason } else { $statusValue.status }
                throw "Login controller failed during startup: $startupReason"
            }
        }
        if (-not (Test-ProcessIdentity $control)) { break }
        Start-Sleep -Milliseconds 500
    }

    if (Test-ProcessIdentity $control) { try { Stop-ManagedProcess $control } catch {} }
    $stderrTail = if (Test-Path $StderrPath) { (Get-Content $StderrPath -Tail 30) -join "`n" } else { "" }
    throw "Local login browser did not become ready within 130 seconds.`n$stderrTail"
}

function Complete-LoginSession {
    $control = Read-JsonFile $ControlPath
    if ($null -eq $control) { throw "No active $Platform login session exists. Run .\LOGIN.ps1 $Platform -Start first." }
    if ([string]$control.platform -ne $Platform) { throw "Control file platform mismatch." }
    if ([string]::IsNullOrWhiteSpace([string]$control.session_id)) { throw "Control file has no session_id; discard it with -Cancel and restart." }
    if (-not (Test-ProcessIdentity $control)) { throw "Active login process identity no longer matches PID/path/start-time. Refusing to signal or terminate an unrelated process." }

    $statusValue = Read-JsonFile $StatusPath
    if ($null -eq $statusValue) { throw "Active login session has no status file yet." }
    if ([string]$statusValue.session_id -ne [string]$control.session_id) { throw "Status/control session_id mismatch. Refusing stale completion." }
    if ($statusValue.status -ne "waiting_for_user_signal") { throw "Login session is not waiting for completion; current status=$($statusValue.status)." }

    $utf8NoBom = New-Object System.Text.UTF8Encoding -ArgumentList $false
    [System.IO.File]::WriteAllText($SignalPath, [string]$control.session_id, $utf8NoBom)
    Write-Host "Completion signal sent for session $($control.session_id). Verifying..."

    $deadline = (Get-Date).AddMinutes(10)
    while ((Get-Date) -lt $deadline -and (Test-ProcessIdentity $control)) { Start-Sleep -Milliseconds 500 }
    if (Test-ProcessIdentity $control) {
        Stop-ManagedProcess $control
        throw "Login verification timed out after 10 minutes."
    }

    $final = Read-JsonFile $StatusPath
    if ($null -eq $final) { throw "Login controller exited without final status." }
    if ([string]$final.session_id -ne [string]$control.session_id) { throw "Final status belongs to another session." }
    if ($final.status -ne "saved_and_verified") {
        $reason = if ($final.reason) { $final.reason } elseif ($final.error) { $final.error } else { $final.status }
        throw "$Platform login was not saved and verified: $reason"
    }

    Remove-Item -LiteralPath $ControlPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $SignalPath -Force -ErrorAction SilentlyContinue
    Write-Host "[OK] $Platform login state saved and verified."
    Write-Host "LOGIN_AGENT_STATE=SAVED_AND_VERIFIED"
    Write-Host "LOGIN_AGENT_SESSION_ID=$($control.session_id)"
}

function Show-LoginSessionStatus {
    $control = Read-JsonFile $ControlPath
    $statusValue = Read-JsonFile $StatusPath
    if ($null -eq $control) {
        Write-Host "Agent session: none"
        if ($null -ne $statusValue) { Write-Host "Historical helper status: $($statusValue.status) (not an active session)" }
        Write-Host "LOGIN_AGENT_STATE=NO_ACTIVE_SESSION"
        return
    }
    $identityOk = Test-ProcessIdentity $control
    $statusSessionOk = $null -ne $statusValue -and [string]$statusValue.session_id -eq [string]$control.session_id
    Write-Host "Session ID: $($control.session_id)"
    Write-Host "Process identity valid: $identityOk"
    Write-Host "Status session valid: $statusSessionOk"
    Write-Host "Status: $(if ($null -ne $statusValue) { $statusValue.status } else { 'missing' })"
    if ($identityOk -and $statusSessionOk -and $statusValue.status -eq "waiting_for_user_signal") {
        Write-Host "LOGIN_AGENT_STATE=WAITING_FOR_USER"
    } else {
        Write-Host "LOGIN_AGENT_STATE=STALE_OR_INVALID_SESSION"
    }
}

function Cancel-LoginSession {
    $control = Read-JsonFile $ControlPath
    if ($null -ne $control) {
        if (Test-ProcessIdentity $control) {
            Stop-ManagedProcess $control
        } else {
            Write-Warning "Stored PID does not match the recorded executable/start-time identity; no process was terminated."
        }
    }
    Remove-Item -LiteralPath $SignalPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ControlPath -Force -ErrorAction SilentlyContinue
    Write-Host "LOGIN_AGENT_STATE=CANCELLED"
}

Write-Host "Cloud Phone Monitor - Local Login"
Write-Host "Platform: $Platform"
Write-Host "Skill root: $SkillRoot"
Write-Host "Mode: $Mode"
Write-Host "Collector authentication must be completed in the LOCAL Playwright Chromium window, never ChatGPT Cloud Browser."

switch ($Mode) {
    "Start" { Start-LoginSession }
    "Complete" { Complete-LoginSession }
    "Status" { Show-LoginSessionStatus }
    "Cancel" { Cancel-LoginSession }
    "Interactive" {
        Start-LoginSession
        [void](Read-Host "After login is complete in the local Chromium window, press Enter")
        Complete-LoginSession
    }
}
