param(
    [string]$SkillRoot = (Join-Path $env:USERPROFILE ".codex\skills\cloud-phone-monitor-skill"),
    [string]$SitesRoot = "C:\Sites",
    [switch]$InstallDependencies,
    [switch]$InstallDailyTask,
    [string]$DailyTime = "10:00"
)
$ErrorActionPreference = "Stop"
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Cloud Phone Monitor installer"
Write-Host "Package:   $PackageRoot"
Write-Host "SkillRoot: $SkillRoot"
Write-Host "SitesRoot: $SitesRoot"

New-Item -ItemType Directory -Force -Path $SkillRoot | Out-Null

# Overlay program files while preserving local runtime data and generated output.
$dirs = @("cloud_phone_monitor", "dashboard", "tests", "tools", "deployment", "scripts")
foreach ($dir in $dirs) {
    $src = Join-Path $PackageRoot $dir
    if (Test-Path $src) {
        $dst = Join-Path $SkillRoot $dir
        New-Item -ItemType Directory -Force -Path $dst | Out-Null
        robocopy $src $dst /E /R:2 /W:1 /XD node_modules dist __pycache__ .pytest_cache /XF *.pyc | Out-Null
        if ($LASTEXITCODE -gt 7) { throw "Failed to copy $dir (robocopy exit $LASTEXITCODE)" }
    }
}

$rootFiles = @(
    ".gitignore",
    ".gitattributes",
    "README.md",
    "SKILL.md",
    "DEPLOYMENT_DATA_GUIDE.md",
    "requirements.txt",
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
foreach ($name in $rootFiles) {
    $src = Join-Path $PackageRoot $name
    if (Test-Path $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $SkillRoot $name) -Force
    }
}

& (Join-Path $PackageRoot "deployment\windows\install_deployment.ps1") `
    -RepoRoot $PackageRoot -SitesRoot $SitesRoot -SkipVerify
if ($LASTEXITCODE -ne 0) { throw "Deployment installation failed." }

if ($InstallDependencies) {
    & (Join-Path $PackageRoot "install_dependencies_windows.ps1") -SkillRoot $SkillRoot
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
}

& (Join-Path $SitesRoot "verify_deployment.ps1") -SkillRoot $SkillRoot -SitesRoot $SitesRoot
if ($LASTEXITCODE -ne 0) { throw "Install verification failed." }

if ($InstallDailyTask) {
    & (Join-Path $SkillRoot "scripts\setup_daily_monitor_windows.ps1") `
        -ScheduleTime $DailyTime `
        -Updater (Join-Path $SitesRoot "update_cloud_phone_dashboard.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Task Scheduler installation failed." }
}

Write-Host ""
Write-Host "Installation completed."
Write-Host "Local login:    $SkillRoot\LOGIN.ps1 <UgPhone|VSPhone|Redfinger|LDCloud>"
Write-Host "Daily updater:  $SitesRoot\update_cloud_phone_dashboard.ps1"
Write-Host "GitHub Pages publishing is disabled unless publisher.local.json is configured."
