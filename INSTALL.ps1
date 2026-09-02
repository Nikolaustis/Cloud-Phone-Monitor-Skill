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

# Overlay source without mirroring/deleting runtime directories. output/, baselines/,
# dashboard/node_modules/ and dashboard/dist/ therefore survive upgrades.
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
    ".gitignore", ".gitattributes", "README.md", "SKILL.md", "DEPLOYMENT_DATA_GUIDE.md", "requirements.txt", "config.example.json",
    "install_windows.ps1", "run_windows.bat", "run.py", "rebuild_dashboard_history.py", "deployment_contract.json", "INSTALL_GUIDE.md", "VALIDATION.md", "INSTALL.ps1",
    "PUBLISH_SOURCE_TO_GITHUB.ps1"
)
foreach ($name in $rootFiles) {
    $src = Join-Path $PackageRoot $name
    if (Test-Path $src) { Copy-Item -LiteralPath $src -Destination (Join-Path $SkillRoot $name) -Force }
}

# Remove obsolete release-branded source files left by earlier packages. Runtime
# data is never touched.
Get-ChildItem -LiteralPath $SkillRoot -File -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match "(?i)^(PATCH_NOTES|INSTALL_GUIDE|VALIDATION|MANIFEST|INSTALL|PUBLISH).*V\d+"
} | Remove-Item -Force
$legacyContract = Join-Path $SkillRoot "release_contract.json"
if (Test-Path $legacyContract) { Remove-Item -LiteralPath $legacyContract -Force }
$testsDir = Join-Path $SkillRoot "tests"
if (Test-Path $testsDir) {
    Get-ChildItem -LiteralPath $testsDir -File -Filter "test_v*.py" -ErrorAction SilentlyContinue | Remove-Item -Force
    $fixturesDir = Join-Path $testsDir "fixtures"
    if (Test-Path $fixturesDir) {
        Get-ChildItem -LiteralPath $fixturesDir -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "(?i)^v\d+$" } | Remove-Item -Recurse -Force
    }
}

& (Join-Path $PackageRoot "deployment\windows\install_deployment.ps1") -RepoRoot $PackageRoot -SitesRoot $SitesRoot -SkipVerify
if ($LASTEXITCODE -ne 0) { throw "Deployment installation failed." }

if ($InstallDependencies) {
    Set-Location $SkillRoot
    $PythonExe = "C:\Python314\python.exe"
    if (!(Test-Path $PythonExe)) { $PythonExe = "python" }
    & $PythonExe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "pip install failed." }
    & $PythonExe -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw "Playwright Chromium install failed." }
    Set-Location (Join-Path $SkillRoot "dashboard")
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
}

& (Join-Path $SitesRoot "verify_deployment.ps1") -SkillRoot $SkillRoot -SitesRoot $SitesRoot
if ($LASTEXITCODE -ne 0) { throw "Install verification failed." }

if ($InstallDailyTask) {
    & (Join-Path $SkillRoot "scripts\setup_daily_monitor_windows.ps1") -ScheduleTime $DailyTime -Publisher (Join-Path $SitesRoot "update_cloud_phone_dashboard.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Task Scheduler installation failed." }
}

Write-Host ""
Write-Host "Installation completed."
Write-Host "Daily publisher: $SitesRoot\update_cloud_phone_dashboard.ps1"
Write-Host "Resume publish:  $SitesRoot\resume_dashboard_publish.ps1"
Write-Host "Source upload:   run PUBLISH_SOURCE_TO_GITHUB.ps1 from this extracted package."
