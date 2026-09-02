param(
    [string]$SkillRoot = (Join-Path $env:USERPROFILE ".codex\skills\cloud-phone-monitor-skill"),
    [string]$SitesRoot = "C:\Sites"
)
$ErrorActionPreference = "Stop"

$required = @(
    (Join-Path $SitesRoot "update_cloud_phone_dashboard.ps1"),
    (Join-Path $SitesRoot "publish_dashboard.ps1"),
    (Join-Path $SitesRoot "resume_dashboard_publish.ps1"),
    (Join-Path $SitesRoot "validate_cloud_phone_dashboard.py"),
    (Join-Path $SitesRoot "check_skill_login_state.py"),
    (Join-Path $SitesRoot "deployment_contract.json")
)
foreach ($path in $required) { if (!(Test-Path $path)) { throw "Deployment file missing: $path" } }

$daily = Get-Content -Raw -LiteralPath (Join-Path $SitesRoot "update_cloud_phone_dashboard.ps1")
$publisher = Get-Content -Raw -LiteralPath (Join-Path $SitesRoot "publish_dashboard.ps1")
if ($daily -notmatch "CANONICAL_DAILY_UPDATE") { throw "Daily publisher marker missing." }
if ($publisher -notmatch "CANONICAL_PUBLISHER") { throw "Canonical publisher marker missing." }

$contract = Get-Content -Raw -LiteralPath (Join-Path $SitesRoot "deployment_contract.json") | ConvertFrom-Json
if ($contract.history_storage -ne "gzip-json-v1") { throw "Unsupported history storage contract: $($contract.history_storage)" }
if ($contract.publisher_capability -ne "gzip-history-pages") { throw "Unsupported publisher capability: $($contract.publisher_capability)" }

$PythonExe = "C:\Python314\python.exe"
if (!(Test-Path $PythonExe)) { $PythonExe = "python" }
& $PythonExe -c "import sys; sys.path.insert(0, r'$SkillRoot'); from cloud_phone_monitor.data_contracts import SCHEMA_VERSION; assert SCHEMA_VERSION == 9; print('Schema:', SCHEMA_VERSION)"
if ($LASTEXITCODE -ne 0) { throw "Installed Skill schema verification failed." }

$DistDir = Join-Path $SkillRoot "dashboard\dist"
if (Test-Path (Join-Path $DistDir "dashboard_data")) {
    & $PythonExe (Join-Path $SitesRoot "validate_cloud_phone_dashboard.py") --dist-dir $DistDir
    if ($LASTEXITCODE -ne 0) { throw "Existing Dashboard dist failed validation." }
} else {
    Write-Host "No existing dashboard dist data; runtime validation skipped."
}

Write-Host "Deployment verification passed."
