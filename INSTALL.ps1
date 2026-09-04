param(
    [string]$SkillRoot = (Join-Path $env:USERPROFILE ".codex\skills\cloud-phone-monitor-skill"),
    [string]$SitesRoot = "C:\Sites",
    [switch]$InstallDependencies,
    [switch]$InstallDashboardDependencies,
    [switch]$InstallDevDependencies,
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
    "README.md",
    "SKILL.md",
    "DEPLOYMENT_DATA_GUIDE.md",
    "requirements.txt",
    "constraints-runtime.txt",
    "requirements-dev.txt",
    "RUN_TESTS.ps1",
    "PREPARE_RELEASE.ps1",
    "config.example.json",
    "publisher.local.example.json",
    "install_dependencies_windows.ps1",
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
    "dashboard\package.json",
    "deployment\windows\install_deployment.ps1",
    "deployment\windows\verify_deployment.ps1",
    "scripts\setup_daily_monitor_windows.ps1",
    "tools\validate_source_package.py",
    "tools\generate_manifest.py",
    "tools\validate_manifest.py",
    "tools\build_release_staging.py",
    "tools\public_release_policy.py",
    "tools\validate_public_release.py",
    "tools\build_release_zip.py"
)

Write-Host "Cloud Phone Monitor installer"
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
    $dirs = @("cloud_phone_monitor", "dashboard", "tests", "tools", "deployment", "scripts")
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
Write-Host "Google Chrome is not required."
