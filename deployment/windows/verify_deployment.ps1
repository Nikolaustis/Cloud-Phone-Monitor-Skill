param(
    [string]$SkillRoot = (Join-Path $env:USERPROFILE ".codex\skills\cloud-phone-monitor-skill"),
    [string]$SitesRoot = "C:\Sites"
)
$ErrorActionPreference = "Stop"

$required = @(
    (Join-Path $SkillRoot "LOGIN.ps1"),
    (Join-Path $SkillRoot "install_dependencies_windows.ps1"),
    (Join-Path $SkillRoot "cloud_phone_monitor\login_controller.py"),
    (Join-Path $SkillRoot "cloud_phone_monitor\auth_session_contract.py"),
    (Join-Path $SkillRoot "cloud_phone_monitor\login_wait_for_signal.py"),
    (Join-Path $SitesRoot "update_cloud_phone_dashboard.ps1"),
    (Join-Path $SitesRoot "publish_dashboard.ps1"),
    (Join-Path $SitesRoot "resume_dashboard_publish.ps1"),
    (Join-Path $SitesRoot "validate_cloud_phone_dashboard.py"),
    (Join-Path $SitesRoot "check_skill_login_state.py"),
    (Join-Path $SitesRoot "deployment_contract.json")
)
foreach ($path in $required) {
    if (!(Test-Path $path)) { throw "Deployment file missing: $path" }
}

$contract = Get-Content -Raw -LiteralPath (Join-Path $SitesRoot "deployment_contract.json") | ConvertFrom-Json
if ($contract.schema_version -ne 9) { throw "Unsupported schema version: $($contract.schema_version)" }
if ($contract.history_storage -ne "gzip-json-v1") { throw "Unsupported history storage contract: $($contract.history_storage)" }
if ($contract.publisher_capability -ne "gzip-history-pages") { throw "Unsupported publisher capability: $($contract.publisher_capability)" }

$PythonExe = $null
$candidates = @("C:\Python314\python.exe", "C:\Python313\python.exe", "C:\Python312\python.exe")
$cmd = Get-Command python -ErrorAction SilentlyContinue
if ($cmd) { $candidates += $cmd.Source }
foreach ($candidate in ($candidates | Select-Object -Unique)) {
    if (!(Test-Path $candidate)) { continue }
    $proc = Start-Process -FilePath $candidate -ArgumentList '-c "import sys; print(sys.executable)"' -Wait -PassThru -NoNewWindow
    if ($proc.ExitCode -eq 0) { $PythonExe = $candidate; break }
}
if (-not $PythonExe) { throw "No runnable Python executable found." }

& $PythonExe -c "import sys; sys.path.insert(0, r'$SkillRoot'); from cloud_phone_monitor.data_contracts import SCHEMA_VERSION; assert SCHEMA_VERSION == 9; print('Schema:', SCHEMA_VERSION)"
if ($LASTEXITCODE -ne 0) { throw "Installed Skill schema verification failed." }
& $PythonExe -m py_compile (Join-Path $SkillRoot "cloud_phone_monitor\login_controller.py")
if ($LASTEXITCODE -ne 0) { throw "login_controller.py syntax verification failed." }

$LoginScript = Get-Content -Raw -LiteralPath (Join-Path $SkillRoot "LOGIN.ps1")
foreach ($marker in @(
    'cloud_phone_monitor.login_controller',
    '[switch]$Start',
    '[switch]$Complete',
    'session_id',
    'process_start_ticks',
    'LOGIN_AGENT_STATE=WAITING_FOR_USER',
    'LOGIN_AGENT_STATE=SAVED_AND_VERIFIED'
)) {
    if (-not $LoginScript.Contains($marker)) { throw "Installed LOGIN.ps1 missing required marker: $marker" }
}

$Controller = Get-Content -Raw -LiteralPath (Join-Path $SkillRoot "cloud_phone_monitor\login_controller.py")
foreach ($marker in @('verify_saved_auth_state', 'signal_matches_session', '.pending.')) {
    if (-not $Controller.Contains($marker)) { throw "Installed login_controller.py missing required marker: $marker" }
}


$AuthContract = Get-Content -Raw -LiteralPath (Join-Path $SkillRoot "cloud_phone_monitor\auth_session_contract.py")
foreach ($marker in @('no_server_acknowledged_auth_evidence', 'server_authenticated')) {
    if (-not $AuthContract.Contains($marker)) { throw "Installed auth_session_contract.py missing required marker: $marker" }
}

$DistDir = Join-Path $SkillRoot "dashboard\dist"
if (Test-Path (Join-Path $DistDir "dashboard_data")) {
    & $PythonExe (Join-Path $SitesRoot "validate_cloud_phone_dashboard.py") --dist-dir $DistDir
    if ($LASTEXITCODE -ne 0) { throw "Existing Dashboard dist failed validation." }
} else {
    Write-Host "No existing Dashboard dist data; runtime validation skipped."
}

Write-Host "Deployment verification passed."
Write-Host "Login controller: session-bound, PID/path/start-time guarded, pending-state commit enabled."
