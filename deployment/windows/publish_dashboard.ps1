param(
    [string]$SkillRoot = (Join-Path $env:USERPROFILE ".codex\skills\cloud-phone-monitor-skill"),
    [string]$ConfigPath = "",
    [string]$SiteRepo = "",
    [string]$RemoteUrl = "",
    [string]$Branch = "",
    [string]$CommitPrefix = ""
)

$ErrorActionPreference = "Stop"

function Get-OptionalProperty {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

$PythonExe = Join-Path $SkillRoot ".venv\Scripts\python.exe"
if (!(Test-Path -LiteralPath $PythonExe)) {
    throw "Dedicated Skill runtime is missing: $PythonExe"
}
$DistDir = Join-Path $SkillRoot "dashboard\dist"
$Validator = Join-Path $PSScriptRoot "validate_cloud_phone_dashboard.py"
if (!(Test-Path -LiteralPath $DistDir)) { throw "Dashboard dist not found: $DistDir" }
if (!(Test-Path -LiteralPath $Validator)) { throw "Dashboard validator not found: $Validator" }

Write-Host "Validating Dashboard dist..."
& $PythonExe -B $Validator --dist-dir $DistDir
if ($LASTEXITCODE -ne 0) { throw "Dashboard validation failed with exit code $LASTEXITCODE" }

if ([string]::IsNullOrWhiteSpace($ConfigPath)) { $ConfigPath = Join-Path $SkillRoot "publisher.local.json" }
$Settings = $null
if (Test-Path -LiteralPath $ConfigPath) {
    try { $Settings = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json }
    catch { throw "Unable to parse publisher configuration: $ConfigPath" }
}

if ([string]::IsNullOrWhiteSpace($RemoteUrl)) { $RemoteUrl = [string](Get-OptionalProperty $Settings "dashboard_site_remote") }
if ([string]::IsNullOrWhiteSpace($SiteRepo)) { $SiteRepo = [string](Get-OptionalProperty $Settings "dashboard_site_repo") }
if ([string]::IsNullOrWhiteSpace($Branch)) { $Branch = [string](Get-OptionalProperty $Settings "dashboard_branch") }
if ([string]::IsNullOrWhiteSpace($CommitPrefix)) { $CommitPrefix = [string](Get-OptionalProperty $Settings "dashboard_commit_prefix") }

if ([string]::IsNullOrWhiteSpace($RemoteUrl)) {
    Write-Host "GitHub Pages publishing is not configured. Dashboard validation completed locally only."
    return
}
if ($RemoteUrl -match "YOUR_ACCOUNT|YOUR_DASHBOARD_REPO") { throw "publisher.local.json still contains placeholder GitHub values." }
if ($RemoteUrl -notmatch '^(https://github\.com/[^/]+/[^/]+(?:\.git)?|git@github\.com:[^/]+/[^/]+(?:\.git)?)$') {
    throw "dashboard_site_remote must point to a GitHub repository."
}
if ([string]::IsNullOrWhiteSpace($SiteRepo)) { $SiteRepo = Join-Path $SkillRoot "output\publisher\dashboard_site" }
if ([string]::IsNullOrWhiteSpace($Branch)) { $Branch = "main" }
if ([string]::IsNullOrWhiteSpace($CommitPrefix)) { $CommitPrefix = "Auto publish dashboard" }

$DocsDir = Join-Path $SiteRepo "docs"
if (!(Test-Path -LiteralPath $SiteRepo)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $SiteRepo) | Out-Null
    git clone $RemoteUrl $SiteRepo
    if ($LASTEXITCODE -ne 0) { throw "git clone failed." }
}
if (!(Test-Path -LiteralPath (Join-Path $SiteRepo ".git"))) { throw "Not a Git repository: $SiteRepo" }

$origin = git -C $SiteRepo remote get-url origin 2>$null
if ($LASTEXITCODE -ne 0) {
    git -C $SiteRepo remote add origin $RemoteUrl
    if ($LASTEXITCODE -ne 0) { throw "Unable to add configured Git remote." }
} elseif ($origin.Trim() -ne $RemoteUrl.Trim()) {
    throw "Existing dashboard repository origin differs from publisher.local.json."
}

git -C $SiteRepo fetch origin
if ($LASTEXITCODE -ne 0) { throw "git fetch failed." }
git -C $SiteRepo checkout $Branch
if ($LASTEXITCODE -ne 0) {
    git -C $SiteRepo checkout -B $Branch "origin/$Branch"
    if ($LASTEXITCODE -ne 0) { throw "Unable to checkout branch $Branch." }
}
git -C $SiteRepo pull --rebase --autostash origin $Branch
if ($LASTEXITCODE -ne 0) { throw "git pull failed." }

$CNameBackup = $null
$ExistingCName = Join-Path $DocsDir "CNAME"
if (Test-Path -LiteralPath $ExistingCName) { $CNameBackup = Get-Content -Raw -LiteralPath $ExistingCName }
New-Item -ItemType Directory -Force -Path $DocsDir | Out-Null
robocopy $DistDir $DocsDir /MIR /R:2 /W:2 /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -gt 7) { throw "robocopy failed with exit code $LASTEXITCODE" }
if ($null -ne $CNameBackup) { Set-Content -LiteralPath $ExistingCName -Value $CNameBackup -Encoding ASCII }
New-Item -ItemType File -Path (Join-Path $DocsDir ".nojekyll") -Force | Out-Null

git -C $SiteRepo add -A -- docs
$changes = git -C $SiteRepo status --porcelain -- docs
if (-not $changes) { Write-Host "No Dashboard changes detected. Nothing to push."; return }
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
git -C $SiteRepo commit -m "$CommitPrefix $stamp"
if ($LASTEXITCODE -ne 0) { throw "git commit failed." }
git -C $SiteRepo push origin $Branch
if ($LASTEXITCODE -ne 0) { throw "git push failed." }
Write-Host "Configured GitHub Pages repository updated successfully."
