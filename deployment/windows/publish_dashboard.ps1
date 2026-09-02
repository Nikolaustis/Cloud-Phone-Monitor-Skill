param(
    [string]$SkillRoot = (Join-Path $env:USERPROFILE ".codex\skills\cloud-phone-monitor-skill"),
    [string]$ConfigPath = "",
    [string]$SiteRepo = "",
    [string]$RemoteUrl = "",
    [string]$Branch = "",
    [string]$CommitPrefix = ""
)
$ErrorActionPreference = "Stop"

function Resolve-PythonExe {
    $candidates = @("C:\Python314\python.exe", "C:\Python313\python.exe", "C:\Python312\python.exe")
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Python executable not found."
}

function Get-OptionalProperty {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

$PythonExe = Resolve-PythonExe
$DistDir = Join-Path $SkillRoot "dashboard\dist"
$Validator = Join-Path $PSScriptRoot "validate_cloud_phone_dashboard.py"

if (!(Test-Path $DistDir)) { throw "Dashboard dist not found: $DistDir" }
if (!(Test-Path $Validator)) { throw "Dashboard validator not found: $Validator" }

Write-Host "Validating Dashboard dist..."
& $PythonExe $Validator --dist-dir $DistDir
if ($LASTEXITCODE -ne 0) { throw "Dashboard validation failed with exit code $LASTEXITCODE" }

if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Join-Path $SkillRoot "publisher.local.json"
}

$Settings = $null
if (Test-Path $ConfigPath) {
    try {
        $Settings = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
    } catch {
        throw "Unable to parse publisher configuration: $ConfigPath"
    }
}

if ([string]::IsNullOrWhiteSpace($RemoteUrl)) {
    $RemoteUrl = [string](Get-OptionalProperty $Settings "dashboard_site_remote")
}
if ([string]::IsNullOrWhiteSpace($SiteRepo)) {
    $SiteRepo = [string](Get-OptionalProperty $Settings "dashboard_site_repo")
}
if ([string]::IsNullOrWhiteSpace($Branch)) {
    $Branch = [string](Get-OptionalProperty $Settings "branch")
}
if ([string]::IsNullOrWhiteSpace($CommitPrefix)) {
    $CommitPrefix = [string](Get-OptionalProperty $Settings "commit_prefix")
}

if ([string]::IsNullOrWhiteSpace($RemoteUrl)) {
    Write-Host "GitHub Pages publishing is not configured."
    Write-Host "Dashboard validation completed; keeping this run local only."
    return
}

if ($RemoteUrl -match "YOUR_ACCOUNT|YOUR_DASHBOARD_REPO") {
    throw "publisher.local.json still contains placeholder GitHub values."
}

if ([string]::IsNullOrWhiteSpace($SiteRepo)) {
    $SiteRepo = Join-Path $PSScriptRoot "Cloud-Phone-Dashboard-Site"
}
if ([string]::IsNullOrWhiteSpace($Branch)) { $Branch = "main" }
if ([string]::IsNullOrWhiteSpace($CommitPrefix)) { $CommitPrefix = "Auto publish dashboard" }

$DocsDir = Join-Path $SiteRepo "docs"

if (!(Test-Path $SiteRepo)) {
    Write-Host "Dashboard site repository is missing; cloning configured remote..."
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $SiteRepo) | Out-Null
    git clone $RemoteUrl $SiteRepo
    if ($LASTEXITCODE -ne 0) { throw "git clone failed." }
}

if (!(Test-Path (Join-Path $SiteRepo ".git"))) {
    throw "Not a Git repository: $SiteRepo"
}

$origin = git -C $SiteRepo remote get-url origin 2>$null
if ($LASTEXITCODE -ne 0) {
    git -C $SiteRepo remote add origin $RemoteUrl
    if ($LASTEXITCODE -ne 0) { throw "Unable to add configured Git remote." }
} elseif ($origin.Trim() -ne $RemoteUrl) {
    throw "Existing repository origin does not match publisher.local.json. Use a separate dashboard_site_repo or update the local configuration."
}

Write-Host "Synchronizing configured Dashboard repository..."
git -C $SiteRepo fetch origin
if ($LASTEXITCODE -ne 0) { throw "git fetch failed." }

git -C $SiteRepo checkout $Branch
if ($LASTEXITCODE -ne 0) {
    git -C $SiteRepo checkout -B $Branch "origin/$Branch"
    if ($LASTEXITCODE -ne 0) { throw "Unable to checkout branch $Branch." }
}

git -C $SiteRepo pull --rebase --autostash origin $Branch
if ($LASTEXITCODE -ne 0) { throw "git pull --rebase --autostash failed." }

$CNameBackup = $null
$ExistingCName = Join-Path $DocsDir "CNAME"
if (Test-Path $ExistingCName) {
    $CNameBackup = Get-Content -Raw -LiteralPath $ExistingCName
}

Write-Host "Mirroring Dashboard dist -> docs..."
New-Item -ItemType Directory -Force -Path $DocsDir | Out-Null
robocopy $DistDir $DocsDir /MIR /R:2 /W:2 /NFL /NDL /NJH /NJS /NP
$RoboCode = $LASTEXITCODE
if ($RoboCode -gt 7) { throw "robocopy failed with exit code $RoboCode" }

if ($null -ne $CNameBackup) {
    Set-Content -LiteralPath $ExistingCName -Value $CNameBackup -Encoding ASCII
}
New-Item -ItemType File -Path (Join-Path $DocsDir ".nojekyll") -Force | Out-Null

git -C $SiteRepo add -A -- docs
$changes = git -C $SiteRepo status --porcelain -- docs
if (-not $changes) {
    Write-Host "No Dashboard changes detected. Nothing to push."
    return
}

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
git -C $SiteRepo commit -m "$CommitPrefix $stamp"
if ($LASTEXITCODE -ne 0) { throw "git commit failed." }

git -C $SiteRepo push origin $Branch
if ($LASTEXITCODE -ne 0) {
    Write-Host "Initial push failed; rebasing once and retrying..."
    git -C $SiteRepo fetch origin
    if ($LASTEXITCODE -ne 0) { throw "git fetch failed during retry." }
    git -C $SiteRepo pull --rebase --autostash origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "git pull --rebase failed during retry." }
    git -C $SiteRepo push origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "git push failed after retry." }
}

Write-Host "Configured GitHub Pages repository updated successfully."
