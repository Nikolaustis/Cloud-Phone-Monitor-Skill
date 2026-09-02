param(
    [string]$SkillRoot = (Join-Path $env:USERPROFILE ".codex\skills\cloud-phone-monitor-skill"),
    [string]$SiteRepo = "C:\Sites\Cloud-Phone-Dashboard-Site",
    [string]$RemoteUrl = "https://github.com/Nikolaustis/Cloud-Phone-Price-Dashboard-Site.git",
    [string]$Branch = "main",
    [string]$CommitPrefix = "Auto publish dashboard"
)

$ErrorActionPreference = "Stop"
# CANONICAL_PUBLISHER

function Resolve-PythonExe {
    $candidates = @("C:\Python314\python.exe", "C:\Python313\python.exe", "C:\Python312\python.exe")
    foreach ($candidate in $candidates) { if (Test-Path $candidate) { return $candidate } }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Python executable not found."
}

$PythonExe = Resolve-PythonExe
$DistDir = Join-Path $SkillRoot "dashboard\dist"
$DocsDir = Join-Path $SiteRepo "docs"
$Validator = "C:\Sites\validate_cloud_phone_dashboard.py"

if (!(Test-Path $DistDir)) { throw "Dashboard dist not found: $DistDir" }
if (!(Test-Path $Validator)) { throw "Dashboard validator not found: $Validator" }

Write-Host "Validating Dashboard dist..."
& $PythonExe $Validator --dist-dir $DistDir
if ($LASTEXITCODE -ne 0) { throw "Dashboard validation failed with exit code $LASTEXITCODE" }

if (!(Test-Path $SiteRepo)) {
    Write-Host "Dashboard site repository is missing; cloning it..."
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $SiteRepo) | Out-Null
    git clone $RemoteUrl $SiteRepo
    if ($LASTEXITCODE -ne 0) { throw "git clone failed." }
}

Set-Location $SiteRepo
if (!(Test-Path (Join-Path $SiteRepo ".git"))) { throw "Not a Git repository: $SiteRepo" }

$origin = git remote get-url origin 2>$null
if ($LASTEXITCODE -ne 0) {
    git remote add origin $RemoteUrl
} elseif ($origin.Trim() -ne $RemoteUrl) {
    git remote set-url origin $RemoteUrl
}

Write-Host "Synchronizing GitHub Pages repository..."
git fetch origin
if ($LASTEXITCODE -ne 0) { throw "git fetch failed." }

git checkout $Branch
if ($LASTEXITCODE -ne 0) {
    git checkout -B $Branch "origin/$Branch"
    if ($LASTEXITCODE -ne 0) { throw "Unable to checkout branch $Branch." }
}

git pull --rebase --autostash origin $Branch
if ($LASTEXITCODE -ne 0) { throw "git pull --rebase --autostash failed." }

# Preserve a custom-domain CNAME if this generated-site repository has one.
$CNameBackup = $null
$ExistingCName = Join-Path $DocsDir "CNAME"
if (Test-Path $ExistingCName) {
    $CNameBackup = Get-Content -Raw -LiteralPath $ExistingCName
}

Write-Host "Mirroring dashboard dist -> docs..."
New-Item -ItemType Directory -Force -Path $DocsDir | Out-Null
robocopy $DistDir $DocsDir /MIR /R:2 /W:2 /NFL /NDL /NJH /NJS /NP
$RoboCode = $LASTEXITCODE
if ($RoboCode -gt 7) { throw "robocopy failed with exit code $RoboCode" }
if ($null -ne $CNameBackup) { Set-Content -LiteralPath $ExistingCName -Value $CNameBackup -Encoding ASCII }
New-Item -ItemType File -Path (Join-Path $DocsDir ".nojekyll") -Force | Out-Null

Write-Host "Committing generated site..."
git add -A -- docs
$changes = git status --porcelain -- docs
if (-not $changes) {
    Write-Host "No Dashboard changes detected. Nothing to push."
    return
}

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
git commit -m "$CommitPrefix $stamp"
if ($LASTEXITCODE -ne 0) { throw "git commit failed." }

git push origin $Branch
if ($LASTEXITCODE -ne 0) {
    Write-Host "Initial push failed; rebasing once and retrying..."
    git fetch origin
    if ($LASTEXITCODE -ne 0) { throw "git fetch failed during retry." }
    git pull --rebase --autostash origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "git pull --rebase failed during retry." }
    git push origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "git push failed after retry." }
}

Write-Host "GitHub Pages push completed successfully."
