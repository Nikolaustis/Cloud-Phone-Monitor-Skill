param(
    [string]$SkillRoot = "",
    [string]$RepositoryUrl = "",
    [string]$RepoDir = "",
    [string]$Branch = "",
    [string]$CommitMessage = "",
    [string]$ConfigPath = "",
    [switch]$SkipVerification
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($SkillRoot)) {
    if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) { throw "Unable to determine SkillRoot." }
    $SkillRoot = $PSScriptRoot
}
$SkillRoot = (Resolve-Path -LiteralPath $SkillRoot).Path
$PythonExe = Join-Path $SkillRoot ".venv\Scripts\python.exe"
if ([string]::IsNullOrWhiteSpace($ConfigPath)) { $ConfigPath = Join-Path $SkillRoot "publisher.local.json" }

$config = $null
if (Test-Path -LiteralPath $ConfigPath) {
    $config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
}
if ([string]::IsNullOrWhiteSpace($RepositoryUrl) -and $config -and $config.source_repo_remote) {
    $RepositoryUrl = [string]$config.source_repo_remote
}
if ([string]::IsNullOrWhiteSpace($RepoDir) -and $config -and $config.source_repo_dir) {
    $RepoDir = [string]$config.source_repo_dir
}
if ([string]::IsNullOrWhiteSpace($Branch) -and $config -and $config.source_branch) {
    $Branch = [string]$config.source_branch
}
if ([string]::IsNullOrWhiteSpace($CommitMessage) -and $config -and $config.source_commit_message) {
    $CommitMessage = [string]$config.source_commit_message
}
if ([string]::IsNullOrWhiteSpace($Branch)) { $Branch = "main" }
if ([string]::IsNullOrWhiteSpace($CommitMessage)) { $CommitMessage = "Publish Cloud Phone Pricing Intelligence Platform" }
if ([string]::IsNullOrWhiteSpace($RepoDir)) { $RepoDir = Join-Path $SkillRoot "output\publisher\source_repo" }
if ([string]::IsNullOrWhiteSpace($RepositoryUrl)) {
    throw "Repository URL is required. Pass -RepositoryUrl or create publisher.local.json from publisher.local.example.json."
}
if ($RepositoryUrl -notmatch '^(https://github\.com/[^/]+/[^/]+(?:\.git)?|git@github\.com:[^/]+/[^/]+(?:\.git)?)$') {
    throw "RepositoryUrl must point to a GitHub repository."
}
if (!(Get-Command git -ErrorAction SilentlyContinue)) { throw "git was not found in PATH." }
if (!(Test-Path -LiteralPath $PythonExe)) { throw "Dedicated runtime is missing: $PythonExe" }

if (-not $SkipVerification) {
    Write-Host "Running full v2 release verification before publish..."
    & (Join-Path $SkillRoot "VERIFY_V2.ps1") -SkillRoot $SkillRoot
    if ($LASTEXITCODE -ne 0) { throw "VERIFY_V2.ps1 failed; source was not published." }
}

$ManifestSource = Join-Path $SkillRoot "MANIFEST_SHA256.txt"
if (!(Test-Path -LiteralPath $ManifestSource)) { throw "Validated Manifest is missing: $ManifestSource" }
$StageRoot = Join-Path ([IO.Path]::GetTempPath()) ("cloud_phone_public_publish_" + [Guid]::NewGuid().ToString("N"))

try {
    Write-Host "Building a fresh explicit-allowlist public staging tree..."
    & $PythonExe -B (Join-Path $SkillRoot "tools\build_release_staging.py") $SkillRoot $StageRoot
    if ($LASTEXITCODE -ne 0) { throw "Public staging build failed." }
    & $PythonExe -B (Join-Path $StageRoot "tools\validate_source_package.py") $StageRoot --exact-public-tree
    if ($LASTEXITCODE -ne 0) { throw "Public staging validation failed." }
    & $PythonExe -B (Join-Path $StageRoot "tools\generate_manifest.py") $StageRoot
    if ($LASTEXITCODE -ne 0) { throw "Public staging Manifest generation failed." }
    & $PythonExe -B (Join-Path $StageRoot "tools\validate_manifest.py") $StageRoot
    if ($LASTEXITCODE -ne 0) { throw "Public staging Manifest validation failed." }

    $ManifestStage = Join-Path $StageRoot "MANIFEST_SHA256.txt"
    $sourceText = (Get-Content -LiteralPath $ManifestSource -Raw).Replace("`r`n", "`n")
    $stageText = (Get-Content -LiteralPath $ManifestStage -Raw).Replace("`r`n", "`n")
    if ($sourceText -ne $stageText) {
        throw "Working-tree Manifest does not match the fresh public staging tree. Re-run VERIFY_V2.ps1."
    }

    $RepoDirParent = Split-Path -Parent $RepoDir
    if (-not [string]::IsNullOrWhiteSpace($RepoDirParent)) { New-Item -ItemType Directory -Force -Path $RepoDirParent | Out-Null }
    if (!(Test-Path -LiteralPath $RepoDir)) {
        git clone $RepositoryUrl $RepoDir
        if ($LASTEXITCODE -ne 0) { throw "git clone failed." }
    }
    if (!(Test-Path -LiteralPath (Join-Path $RepoDir ".git"))) { throw "Not a Git repository: $RepoDir" }

    $origin = git -C $RepoDir remote get-url origin 2>$null
    if ($LASTEXITCODE -ne 0) {
        git -C $RepoDir remote add origin $RepositoryUrl
        if ($LASTEXITCODE -ne 0) { throw "Unable to add Git origin." }
    } elseif ($origin.Trim() -ne $RepositoryUrl.Trim()) {
        git -C $RepoDir remote set-url origin $RepositoryUrl
        if ($LASTEXITCODE -ne 0) { throw "Unable to update Git origin." }
    }

    git -C $RepoDir fetch origin
    if ($LASTEXITCODE -ne 0) { throw "git fetch failed." }
    git -C $RepoDir checkout $Branch
    if ($LASTEXITCODE -ne 0) {
        git -C $RepoDir checkout -B $Branch "origin/$Branch"
        if ($LASTEXITCODE -ne 0) { throw "Unable to checkout branch $Branch." }
    }
    git -C $RepoDir pull --rebase --autostash origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "git pull failed." }

    Write-Host "Mirroring only the validated public staging tree into the Git repository..."
    robocopy $StageRoot $RepoDir /MIR /R:2 /W:1 /XD .git | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy failed with exit code $LASTEXITCODE" }

    git -C $RepoDir add -A

    Write-Host "Validating the actual Git-tracked/indexed public tree before commit..."
    & $PythonExe -B (Join-Path $RepoDir "tools\validate_git_tracked_files.py") $RepoDir
    if ($LASTEXITCODE -ne 0) {
        throw "Git-tracked public-tree validation failed; nothing was committed."
    }

    $changes = git -C $RepoDir status --porcelain
    if (-not $changes) {
        Write-Host "GitHub repository already matches the validated public release tree."
        return
    }

    Write-Host "Files to publish:"
    git -C $RepoDir status --short
    git -C $RepoDir commit -m $CommitMessage
    if ($LASTEXITCODE -ne 0) { throw "git commit failed." }
    git -C $RepoDir push origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "git push failed." }

    Write-Host ""
    Write-Host "PUBLIC_SOURCE_PUBLISHED=True"
    Write-Host "Repository: $RepositoryUrl"
    Write-Host "Branch:     $Branch"
    Write-Host "Source:     validated explicit-allowlist staging only"
} finally {
    Remove-Item -LiteralPath $StageRoot -Recurse -Force -ErrorAction SilentlyContinue
}
