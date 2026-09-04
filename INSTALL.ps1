param(
    [string]$SkillRoot = (Join-Path $env:USERPROFILE ".codex\skills\cloud-phone-monitor-skill"),
    [string]$SitesRoot = "C:\Sites",
    [switch]$InstallDependencies,
    [switch]$InstallDashboardDependencies,
    [switch]$InstallDevDependencies,
    [switch]$InstallAIDependencies,
    [switch]$InstallDailyTask,
    [string]$DailyTime = "10:00"
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) { throw "Unable to determine source package root." }
$PackageRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$SkillRootFull = [System.IO.Path]::GetFullPath($SkillRoot).TrimEnd('\')
$PackageRootFull = [System.IO.Path]::GetFullPath($PackageRoot).TrimEnd('\')
$SameRoot = $PackageRootFull.Equals($SkillRootFull, [System.StringComparison]::OrdinalIgnoreCase)

# Explicit trust boundary for ZIP downloads carrying Mark-of-the-Web. This does
# not change the machine execution policy; it only unblocks script files inside
# the package the user chose to run with -ExecutionPolicy Bypass.
try {
    Get-ChildItem -LiteralPath $PackageRoot -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @(".ps1", ".psm1", ".bat") } |
        ForEach-Object { Unblock-File -LiteralPath $_.FullName -ErrorAction SilentlyContinue }
} catch {}

$RequiredRootFiles = @(
    ".gitignore",
    ".gitattributes",
    ".python-version",
    ".nvmrc",
    "runtime-versions.json",
    "LICENSE",
    "MIGRATION_GUIDE.md",
    "README.md",
    "AI_GUIDE.md",
    "PROJECT_PORTFOLIO.md",
    "SKILL.md",
    "DEPLOYMENT_DATA_GUIDE.md",
    "requirements.txt",
    "constraints-runtime.txt",
    "requirements-dev.txt",
    "requirements-ai.txt",
    "RUN_TESTS.ps1",
    "RUN_AI_TESTS.ps1",
    "START_DEMO.ps1",
    "VERIFY_V2.ps1",
    "VERIFY_REAL_COLLECTORS.ps1",
    "PUBLISH_PUBLIC_SOURCE.ps1",
    "PREPARE_RELEASE.ps1",
    "config.example.json",
    "publisher.local.example.json",
    "install_dependencies_windows.ps1",
    "install_ai_dependencies_windows.ps1",
    "ai.env.example",
    "build_ai_context.py",
    "run_ai_api.py",
    "run_windows.bat",
    "run.py",
    "rebuild_dashboard_history.py",
    "deployment_contract.json",
    "INSTALL_GUIDE.md",
    "VALIDATION.md",
    "MANIFEST_SHA256.txt",
    "LOGIN.ps1",
    "INSTALL.ps1"
)
$RequiredPackageFiles = @(
    "cloud_phone_monitor\login_wait_for_signal.py",
    "cloud_phone_monitor\login_controller.py",
    "cloud_phone_monitor\login_helper_session_entry.py",
    "cloud_phone_monitor\auth_session_contract.py",
    "cloud_phone_monitor\auth_file_transaction.py",
    "cloud_phone_monitor\profile_lock.py",
    "cloud_phone_monitor\main.py",
    "cloud_phone_monitor\ai_context.py",
    "ai_backend\__init__.py",
    "ai_backend\app.py",
    "ai_backend\config.py",
    "ai_backend\orchestrator.py",
    "ai_backend\schemas.py",
    "ai_backend\store.py",
    "ai_backend\tools.py",
    "ai_backend\providers\__init__.py",
    "ai_backend\providers\base.py",
    "ai_backend\providers\openai_compatible.py",
    "dashboard\package.json",
    "dashboard\src\components\AICopilot.jsx",
    "dashboard\src\lib\aiClient.js",
    "dashboard\src\main.jsx",
    "evals\benchmark_questions.json",
    "evals\run_eval.py",
    "demo\dashboard_data\meta.json",
    "demo\ai_context\manifest.json",
    "deployment\windows\install_deployment.ps1",
    "deployment\windows\verify_deployment.ps1",
    "scripts\setup_daily_monitor_windows.ps1",
    "tools\validate_source_package.py",
    "tools\validate_git_tracked_files.py",
    "tools\generate_manifest.py",
    "tools\validate_manifest.py",
    "tools\build_release_staging.py",
    "tools\public_release_policy.py",
    "tools\prepare_demo_runtime.py",
    "tools\verify_demo_contract.py",
    "tools\validate_public_release.py",
    "tools\build_release_zip.py"
)

Write-Host "Cloud Phone Pricing Intelligence installer"
Write-Host "Package:   $PackageRoot"
Write-Host "SkillRoot: $SkillRoot"
Write-Host "SitesRoot: $SitesRoot"

Write-Host "Step 0: Validate source package completeness"
foreach ($rel in @($RequiredRootFiles) + @($RequiredPackageFiles)) {
    $src = Join-Path $PackageRoot $rel
    if (!(Test-Path $src)) { throw "Required source package file missing: $src" }
}

New-Item -ItemType Directory -Force -Path $SkillRoot | Out-Null

if ($SameRoot) {
    Write-Host "Step 1-3: Source and installed Skill are the same directory; skipping self-copy."
    Write-Host "           $PackageRootFull"
} else {
    Write-Host "Step 1: Copy program directories"
    $dirs = @("cloud_phone_monitor", "ai_backend", "dashboard", "tests", "evals", "demo", "tools", "deployment", "scripts")
    foreach ($dir in $dirs) {
        $src = Join-Path $PackageRoot $dir
        if (!(Test-Path $src)) { throw "Required source directory missing: $src" }
        $dst = Join-Path $SkillRoot $dir
        New-Item -ItemType Directory -Force -Path $dst | Out-Null
        robocopy $src $dst /E /R:2 /W:1 /XD node_modules dist __pycache__ .pytest_cache .venv /XF *.pyc | Out-Null
        if ($LASTEXITCODE -gt 7) { throw "Failed to copy $dir (robocopy exit $LASTEXITCODE)" }
    }

    Write-Host "Step 2: Copy required root files"
    foreach ($name in $RequiredRootFiles) {
        Copy-Item -LiteralPath (Join-Path $PackageRoot $name) -Destination (Join-Path $SkillRoot $name) -Force
    }

    Write-Host "Step 3: Validate installed Skill completeness"
    foreach ($rel in @($RequiredRootFiles) + @($RequiredPackageFiles)) {
        $dst = Join-Path $SkillRoot $rel
        if (!(Test-Path $dst)) { throw "Installed Skill is incomplete; required file missing after copy: $dst" }
    }
}

Write-Host "Step 4: Install deployment scripts"
& (Join-Path $PackageRoot "deployment\windows\install_deployment.ps1") -RepoRoot $PackageRoot -SitesRoot $SitesRoot -SkipVerify
if ($LASTEXITCODE -ne 0) { throw "Deployment installation failed." }

if ($InstallDependencies) {
    Write-Host "Step 5: Install runtime dependencies"
    $dependencyArgs = @{ SkillRoot = $SkillRoot }
    if ($InstallDashboardDependencies) { $dependencyArgs.InstallDashboardDependencies = $true }
    if ($InstallDevDependencies) { $dependencyArgs.InstallDevDependencies = $true }
    & (Join-Path $SkillRoot "install_dependencies_windows.ps1") @dependencyArgs
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
} else {
    Write-Host "Step 5: Dependency installation skipped. Use -InstallDependencies for a new machine."
}

if ($InstallAIDependencies) {
    Write-Host "Step 5.5: Install optional AI service dependencies"
    $AIInstaller = Join-Path $SkillRoot "install_ai_dependencies_windows.ps1"
    if (!(Test-Path $AIInstaller)) { throw "AI dependency installer missing: $AIInstaller" }
    & $AIInstaller -SkillRoot $SkillRoot
    if ($LASTEXITCODE -ne 0) { throw "AI dependency installation failed." }
} else {
    Write-Host "Step 5.5: Optional AI service dependency installation skipped."
}

Write-Host "Step 6: Verify deployment"
$verifyArgs = @{ SkillRoot = $SkillRoot; SitesRoot = $SitesRoot }
if ($InstallDependencies) { $verifyArgs.RequireRuntime = $true }
& (Join-Path $SitesRoot "verify_deployment.ps1") @verifyArgs
if ($LASTEXITCODE -ne 0) { throw "Install verification failed." }

if ($InstallDailyTask) {
    & (Join-Path $SkillRoot "scripts\setup_daily_monitor_windows.ps1") -ScheduleTime $DailyTime -Updater (Join-Path $SitesRoot "update_cloud_phone_dashboard.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Task Scheduler installation failed." }
}

Write-Host ""
Write-Host "Installation completed."
Write-Host "Local login:   $SkillRoot\LOGIN.ps1 <Platform>"
Write-Host "Agent login:   $SkillRoot\LOGIN.ps1 <Platform> -Start / -Complete"
Write-Host "Dependencies:  .\install_dependencies_windows.ps1 creates/updates the dedicated .venv runtime."
Write-Host "Dashboard deps: add -InstallDashboardDependencies only when npm dependencies are needed."
Write-Host "AI context:      $SkillRoot\build_ai_context.py"
Write-Host "AI API:          $SkillRoot\run_ai_api.py (optional FastAPI backend)"
Write-Host "AI dependencies: add -InstallAIDependencies or run install_ai_dependencies_windows.ps1."
Write-Host "One-command demo: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\START_DEMO.ps1"
Write-Host "Release verifier: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\VERIFY_V2.ps1 -Bootstrap"
Write-Host "Live collector acceptance: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\VERIFY_REAL_COLLECTORS.ps1"
Write-Host "Safe publisher: PUBLISH_PUBLIC_SOURCE.ps1 publishes only a freshly validated public staging tree."
Write-Host "Google Chrome is not required."
