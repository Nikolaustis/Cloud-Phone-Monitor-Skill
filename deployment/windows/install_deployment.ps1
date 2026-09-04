param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$SitesRoot = "C:\Sites",
    [switch]$SkipVerify
)
$ErrorActionPreference = "Stop"

$Source = Join-Path $RepoRoot "deployment\windows"
if (!(Test-Path $Source)) { throw "Deployment source not found: $Source" }

New-Item -ItemType Directory -Force -Path $SitesRoot | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $SitesRoot ("backup_before_deployment_" + $stamp)
New-Item -ItemType Directory -Force -Path $backup | Out-Null

$files = @(
    "update_cloud_phone_dashboard.ps1",
    "publish_dashboard.ps1",
    "resume_dashboard_publish.ps1",
    "validate_cloud_phone_dashboard.py",
    "check_skill_login_state.py",
    "verify_deployment.ps1"
)

foreach ($name in $files) {
    $sourcePath = Join-Path $Source $name
    if (!(Test-Path $sourcePath)) { throw "Deployment file missing from package: $sourcePath" }
    $dest = Join-Path $SitesRoot $name
    if (Test-Path $dest) { Copy-Item -LiteralPath $dest -Destination (Join-Path $backup $name) -Force }
    Copy-Item -LiteralPath $sourcePath -Destination $dest -Force
}

Copy-Item -LiteralPath (Join-Path $RepoRoot "deployment_contract.json") `
    -Destination (Join-Path $SitesRoot "deployment_contract.json") -Force

Write-Host "Deployment files installed to: $SitesRoot"
Write-Host "Previous deployment files backed up to: $backup"

if (-not $SkipVerify) {
    & (Join-Path $SitesRoot "verify_deployment.ps1") -SitesRoot $SitesRoot
    if ($LASTEXITCODE -ne 0) { throw "Deployment verification failed." }
}
