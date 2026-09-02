param(
    [string]$RepoDir = "C:\Sites\Cloud-Phone-Monitor-Skill-Repo",
    [string]$RemoteUrl = "https://github.com/Nikolaustis/Cloud-Phone-Monitor-Skill.git",
    [string]$Branch = "main"
)
$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = "C:\Python314\python.exe"
if (!(Test-Path $PythonExe)) { $PythonExe = "python" }

& $PythonExe (Join-Path $SourceRoot "tools\validate_source_package.py") $SourceRoot
if ($LASTEXITCODE -ne 0) { throw "Source package contains forbidden or missing files." }

if (!(Test-Path $RepoDir)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $RepoDir) | Out-Null
    git clone $RemoteUrl $RepoDir
    if ($LASTEXITCODE -ne 0) { throw "git clone failed." }
}
Set-Location $RepoDir
if (!(Test-Path ".git")) { throw "Not a Git repository: $RepoDir" }

$origin = git remote get-url origin 2>$null
if ($LASTEXITCODE -ne 0) {
    git remote add origin $RemoteUrl
    if ($LASTEXITCODE -ne 0) { throw "Unable to add Git origin." }
} elseif ($origin.Trim() -ne $RemoteUrl) {
    git remote set-url origin $RemoteUrl
    if ($LASTEXITCODE -ne 0) { throw "Unable to update Git origin." }
}
git fetch origin
if ($LASTEXITCODE -ne 0) { throw "git fetch failed." }
git checkout $Branch
if ($LASTEXITCODE -ne 0) {
    git checkout -B $Branch "origin/$Branch"
    if ($LASTEXITCODE -ne 0) { throw "Unable to checkout branch $Branch." }
}
git pull --rebase --autostash origin $Branch
if ($LASTEXITCODE -ne 0) { throw "git pull failed." }

# Mirror the clean package into the source repository. .git is explicitly
# excluded so stale tracked __pycache__/pyc files are removed by the mirror.
robocopy $SourceRoot $RepoDir /MIR /R:2 /W:1 /XD .git __pycache__ .pytest_cache node_modules dist output baselines /XF *.pyc *.log *.xlsx *.xls *.csv *.jsonl
$RoboCode = $LASTEXITCODE
if ($RoboCode -gt 7) { throw "robocopy failed with exit code $RoboCode" }

# Remove legacy tracked/generated/private material that older repository versions
# accidentally contained. This is a source repository, not a runtime backup.
$legacyDirs = @(
    (Join-Path $RepoDir "output"),
    (Join-Path $RepoDir "baselines"),
    (Join-Path $RepoDir "logs"),
    (Join-Path $RepoDir "dashboard\node_modules"),
    (Join-Path $RepoDir "dashboard\dist"),
    (Join-Path $RepoDir "dashboard\public\dashboard_data")
)
foreach ($legacy in $legacyDirs) { if (Test-Path $legacy) { Remove-Item -LiteralPath $legacy -Recurse -Force } }
Get-ChildItem $RepoDir -Directory -Recurse -Force -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Get-ChildItem $RepoDir -File -Recurse -Force -ErrorAction SilentlyContinue | Where-Object {
    $_.Extension -in @(".pyc", ".pyo", ".log", ".xlsx", ".xls", ".csv", ".jsonl") -or $_.Name -like "*_state.json"
} | Remove-Item -Force
Get-ChildItem $RepoDir -File -Filter "*.zip" -ErrorAction SilentlyContinue | Remove-Item -Force

git add -A
$changes = git status --porcelain
if (-not $changes) {
    Write-Host "GitHub source repository already matches the package."
    return
}

git commit -m "Cloud Phone Monitor deployment integration"
if ($LASTEXITCODE -ne 0) { throw "git commit failed." }
git push origin $Branch
if ($LASTEXITCODE -ne 0) {
    git fetch origin
    git pull --rebase --autostash origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "git rebase retry failed." }
    git push origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "git push failed after retry." }
}
Write-Host "Cloud-Phone-Monitor-Skill Source pushed successfully."
