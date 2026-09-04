param(
    [string]$SkillRoot = (Join-Path $env:USERPROFILE ".codex\skills\cloud-phone-monitor-skill"),
    [string]$SitesRoot = "C:\Sites",
    [switch]$RequireRuntime
)
$ErrorActionPreference = "Stop"

$required = @(
    (Join-Path $SkillRoot "LOGIN.ps1"),
    (Join-Path $SkillRoot "install_dependencies_windows.ps1"),
    (Join-Path $SkillRoot "cloud_phone_monitor\login_controller.py"),
    (Join-Path $SkillRoot "cloud_phone_monitor\login_helper_session_entry.py"),
    (Join-Path $SkillRoot "cloud_phone_monitor\auth_session_contract.py"),
    (Join-Path $SkillRoot "cloud_phone_monitor\auth_file_transaction.py"),
    (Join-Path $SkillRoot "cloud_phone_monitor\profile_lock.py"),
    (Join-Path $SkillRoot "cloud_phone_monitor\login_wait_for_signal.py"),
    (Join-Path $SkillRoot "cloud_phone_monitor\ai_context.py"),
    (Join-Path $SkillRoot "build_ai_context.py"),
    (Join-Path $SkillRoot "run_ai_api.py"),
    (Join-Path $SkillRoot "ai_backend\app.py"),
    (Join-Path $SkillRoot "ai_backend\tools.py"),
    (Join-Path $SkillRoot "dashboard\src\components\AICopilot.jsx"),
    (Join-Path $SkillRoot "dashboard\src\lib\aiClient.js"),
    (Join-Path $SkillRoot "tools\generate_manifest.py"),
    (Join-Path $SkillRoot "tools\validate_manifest.py"),
    (Join-Path $SkillRoot "tools\build_release_staging.py"),
    (Join-Path $SkillRoot "tools\public_release_policy.py"),
    (Join-Path $SkillRoot "tools\validate_public_release.py"),
    (Join-Path $SkillRoot "tools\build_release_zip.py"),
    (Join-Path $SkillRoot "constraints-runtime.txt"),
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

$PythonExe = Join-Path $SkillRoot ".venv\Scripts\python.exe"
$RuntimeAvailable = Test-Path $PythonExe
if ($RequireRuntime -and -not $RuntimeAvailable) {
    throw "Dedicated Skill runtime is required but missing: $PythonExe. Run install_dependencies_windows.ps1."
}

if ($RuntimeAvailable) {
    & $PythonExe -c "import sys; sys.path.insert(0, r'$SkillRoot'); from cloud_phone_monitor.data_contracts import SCHEMA_VERSION; assert SCHEMA_VERSION == 9; print('Schema:', SCHEMA_VERSION)"
    if ($LASTEXITCODE -ne 0) { throw "Installed Skill schema verification failed." }

    foreach ($rel in @(
        "cloud_phone_monitor\login_controller.py",
        "cloud_phone_monitor\login_helper_session_entry.py",
        "cloud_phone_monitor\auth_session_contract.py",
        "cloud_phone_monitor\auth_file_transaction.py",
        "cloud_phone_monitor\profile_lock.py",
        "cloud_phone_monitor\ai_context.py",
        "ai_backend\config.py",
        "ai_backend\orchestrator.py",
        "ai_backend\schemas.py",
        "ai_backend\store.py",
        "ai_backend\tools.py",
        "ai_backend\providers\base.py",
        "ai_backend\providers\openai_compatible.py"
    )) {
        & $PythonExe -m py_compile (Join-Path $SkillRoot $rel)
        if ($LASTEXITCODE -ne 0) { throw "Python syntax verification failed: $rel" }
    }

    $launchProbe = 'from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop(); print("Playwright Chromium launch probe: OK")'
    & $PythonExe -c $launchProbe
    if ($LASTEXITCODE -ne 0) { throw "Dedicated .venv exists but Playwright Chromium launch probe failed." }
} else {
    Write-Warning "Dedicated .venv runtime is not installed yet; static deployment verification only."
}

$LoginScript = Get-Content -Raw -LiteralPath (Join-Path $SkillRoot "LOGIN.ps1")
foreach ($marker in @(
    'cloud_phone_monitor.login_controller',
    '.venv\Scripts\python.exe',
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
foreach ($marker in @(
    'cloud_phone_monitor.login_helper_session_entry',
    '"--session-id"',
    'verify_saved_auth_state',
    'signal_matches_session',
    '.pending.',
    'commit_auth_artifacts',
    'acquire_profile_lock'
)) {
    if (-not $Controller.Contains($marker)) { throw "Installed login_controller.py missing required marker: $marker" }
}

$Adapter = Get-Content -Raw -LiteralPath (Join-Path $SkillRoot "cloud_phone_monitor\login_helper_session_entry.py")
foreach ($marker in @('_helper_capabilities', 'LOGIN_PROTOCOL_VERSION', 'value["session_id"] = session_id', '--session-id')) {
    if (-not $Adapter.Contains($marker)) { throw "Installed login_helper_session_entry.py missing required marker: $marker" }
}

$AuthContract = Get-Content -Raw -LiteralPath (Join-Path $SkillRoot "cloud_phone_monitor\auth_session_contract.py")
foreach ($marker in @('LOGIN_PROTOCOL_VERSION', 'normalize_session_id', 'verify_vsphone_auth', 'verify_redfinger_auth', 'verify_ldcloud_auth', 'no_server_acknowledged_auth_evidence')) {
    if (-not $AuthContract.Contains($marker)) { throw "Installed auth_session_contract.py missing required marker: $marker" }
}


$Runner = Get-Content -Raw -LiteralPath (Join-Path $SkillRoot "run.py")
foreach ($marker in @('locked_profile', 'owner_kind="collector"', 'ugphone_profile')) {
    if (-not $Runner.Contains($marker)) { throw "Installed run.py missing persistent-profile lock marker: $marker" }
}

$AIContextSource = Get-Content -Raw -LiteralPath (Join-Path $SkillRoot "cloud_phone_monitor\ai_context.py")
foreach ($aiMarker in @('ai-context-v2', 'fact_id', 'market_summary.json', 'pairing_index.json', 'trend_index.json')) {
    if (-not $AIContextSource.Contains($aiMarker)) { throw "Installed ai_context.py missing required marker: $aiMarker" }
}

$AICopilot = Get-Content -Raw -LiteralPath (Join-Path $SkillRoot "dashboard\src\components\AICopilot.jsx")
foreach ($aiMarker in @('Market Brief', 'Explain', 'What-if', 'Evidence')) {
    if (-not $AICopilot.Contains($aiMarker)) { throw "Installed AICopilot.jsx missing required marker: $aiMarker" }
}

$AIManifestPath = Join-Path $SkillRoot "dashboard\public\dashboard_data\ai\manifest.json"
if (Test-Path $AIManifestPath) {
    $AIManifest = Get-Content -Raw -LiteralPath $AIManifestPath | ConvertFrom-Json
    if ([string]$AIManifest.schema_version -ne "ai-context-v2") {
        throw "Unsupported AI context schema: $($AIManifest.schema_version)"
    }
    Write-Host "AI context manifest: ai-context-v2"
} else {
    Write-Host "AI context manifest not built yet; run build_ai_context.py after Dashboard data is available."
}

$DistDir = Join-Path $SkillRoot "dashboard\dist"
if ($RuntimeAvailable -and (Test-Path (Join-Path $DistDir "dashboard_data"))) {
    & $PythonExe (Join-Path $SitesRoot "validate_cloud_phone_dashboard.py") --dist-dir $DistDir
    if ($LASTEXITCODE -ne 0) { throw "Existing Dashboard dist failed validation." }
} else {
    Write-Host "Dashboard runtime validation skipped (no runtime or no existing dist data)."
}

Write-Host "Deployment verification passed."
Write-Host "Runtime: $(if ($RuntimeAvailable) { $PythonExe } else { 'not installed' })"
Write-Host "Login controller: session-bound adapter, guarded pending-state commit, and shared UgPhone profile lock enabled."
Write-Host "AI layer: ai-context-v2 semantic export, deterministic pricing tools and Dashboard Copilot source verified."
