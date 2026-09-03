param(
    [string]$SkillRoot = (Join-Path $env:USERPROFILE ".codex\skills\cloud-phone-monitor-skill"),
    [string]$SitesRoot = "C:\Sites"
)
$ErrorActionPreference = "Stop"

$required = @(
    (Join-Path $SkillRoot "LOGIN.ps1"),
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
if ($contract.schema_version -ne 9) {
    throw "Unsupported schema version: $($contract.schema_version)"
}
if ($contract.history_storage -ne "gzip-json-v1") {
    throw "Unsupported history storage contract: $($contract.history_storage)"
}
if ($contract.publisher_capability -ne "gzip-history-pages") {
    throw "Unsupported publisher capability: $($contract.publisher_capability)"
}

$PythonExe = $null
foreach ($candidate in @("C:\Python314\python.exe", "C:\Python313\python.exe", "C:\Python312\python.exe")) {
    if (Test-Path $candidate) {
        $PythonExe = $candidate
        break
    }
}
if (-not $PythonExe) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "Python executable not found." }
    $PythonExe = $cmd.Source
}

& $PythonExe -c "import sys; sys.path.insert(0, r'$SkillRoot'); from cloud_phone_monitor.data_contracts import SCHEMA_VERSION; assert SCHEMA_VERSION == 9; print('Schema:', SCHEMA_VERSION)"
if ($LASTEXITCODE -ne 0) { throw "Installed Skill schema verification failed." }

$LoginScript = Get-Content -Raw -LiteralPath (Join-Path $SkillRoot "LOGIN.ps1")
if ($LoginScript -notmatch "cloud_phone_monitor\.login_wait_for_signal") {
    throw "Installed LOGIN.ps1 does not reference the canonical local Playwright login helper."
}
if ($LoginScript -notmatch '\[switch\]\$Start' -or
    $LoginScript -notmatch '\[switch\]\$Complete' -or
    $LoginScript -notmatch 'LOGIN_AGENT_STATE=WAITING_FOR_USER' -or
    $LoginScript -notmatch 'LOGIN_AGENT_STATE=SAVED_AND_VERIFIED') {
    throw "Installed LOGIN.ps1 does not contain the required two-stage local agent login controller."
}

$DistDir = Join-Path $SkillRoot "dashboard\dist"
if (Test-Path (Join-Path $DistDir "dashboard_data")) {
    & $PythonExe (Join-Path $SitesRoot "validate_cloud_phone_dashboard.py") --dist-dir $DistDir
    if ($LASTEXITCODE -ne 0) { throw "Existing Dashboard dist failed validation." }
} else {
    Write-Host "No existing Dashboard dist data; runtime validation skipped."
}

Write-Host "Deployment verification passed."
Write-Host "Local login entrypoint: $SkillRoot\LOGIN.ps1"
Write-Host "Agent login protocol: -Start -> user login in local Chromium -> -Complete"
