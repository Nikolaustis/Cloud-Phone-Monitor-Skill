param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$SitesRoot = "C:\Sites",
    [switch]$SkipVerify
)
$ErrorActionPreference = "Stop"

$Source = Join-Path $RepoRoot "deployment\windows"
if (!(Test-Path $Source)) { throw "deployment source not found: $Source" }
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
    $dest = Join-Path $SitesRoot $name
    if (Test-Path $dest) { Copy-Item -LiteralPath $dest -Destination (Join-Path $backup $name) -Force }
    Copy-Item -LiteralPath (Join-Path $Source $name) -Destination $dest -Force
}
Copy-Item -LiteralPath (Join-Path $RepoRoot "deployment_contract.json") -Destination (Join-Path $SitesRoot "deployment_contract.json") -Force

# Remove obsolete release-branded compatibility helpers after the canonical
# publisher has been installed. The current publisher files above are preserved.
$obsoleteSitePatterns = @(
    "verify_v*_publish_compat.ps1", "install_v*_publish_compat.ps1",
    "validate_cloud_phone_dashboard_v*.py", "resume_dashboard_publish_v*.ps1"
)
foreach ($pattern in $obsoleteSitePatterns) {
    Get-ChildItem -LiteralPath $SitesRoot -File -Filter $pattern -ErrorAction SilentlyContinue | Remove-Item -Force
}
$legacyContract = Join-Path $SitesRoot "release_contract.json"
if (Test-Path $legacyContract) { Remove-Item -LiteralPath $legacyContract -Force }

Write-Host "Canonical deployment installed to: $SitesRoot"
Write-Host "Previous overwritten files backed up to: $backup"

if (-not $SkipVerify) {
    & (Join-Path $SitesRoot "verify_deployment.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Deployment verification failed." }
}
