param(
    [string]$RepoDir = "C:\Sites\Cloud-Phone-Monitor-Skill-Repo",
    [string]$RemoteUrl = "https://github.com/Nikolaustis/Cloud-Phone-Monitor-Skill.git",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = "C:\Python314\python.exe"
if (!(Test-Path $PythonExe)) { $PythonExe = "python" }
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
    [System.IO.File]::WriteAllText($Path, $Content, $Utf8NoBom)
}

function Ensure-RepositoryMetadata {
    param([string]$Root)

    $gitignore = @(
        "# Runtime/private data",
        "output/",
        "baselines/",
        "logs/",
        ".env",
        "*.log",
        "*.xlsx",
        "*.xls",
        "*.csv",
        "*.jsonl",
        "*_state.json",
        "",
        "# Python",
        "__pycache__/",
        "*.py[cod]",
        ".pytest_cache/",
        ".venv/",
        "venv/",
        "",
        "# Dashboard generated/dependencies",
        "dashboard/node_modules/",
        "dashboard/dist/",
        "dashboard/public/dashboard_data/",
        "",
        "# Editors/OS",
        ".vscode/",
        ".idea/",
        ".DS_Store",
        "Thumbs.db",
        "",
        "# Local deployment clones/backups",
        "*.bak_*",
        "backup_before_deployment_*/",
        ""
    ) -join "`n"

    $gitattributes = @(
        "*.ps1 text eol=crlf",
        "*.py text eol=lf",
        "*.js text eol=lf",
        "*.jsx text eol=lf",
        "*.json text eol=lf",
        "*.md text eol=lf",
        "*.gz binary",
        ""
    ) -join "`n"

    Write-Utf8NoBom (Join-Path $Root ".gitignore") $gitignore
    Write-Utf8NoBom (Join-Path $Root ".gitattributes") $gitattributes
}

function Ensure-DashboardBuildConfigs {
    param([string]$Root)

    $dashboard = Join-Path $Root "dashboard"
    New-Item -ItemType Directory -Force -Path $dashboard | Out-Null

    $postcssPath = Join-Path $dashboard "postcss.config.js"
    if (!(Test-Path $postcssPath)) {
        $postcss = @(
            "export default {",
            "  plugins: {",
            "    tailwindcss: {},",
            "    autoprefixer: {},",
            "  },",
            "};",
            ""
        ) -join "`n"
        Write-Utf8NoBom $postcssPath $postcss
        Write-Host "Restored missing dashboard/postcss.config.js"
    }

    $tailwindPath = Join-Path $dashboard "tailwind.config.js"
    if (!(Test-Path $tailwindPath)) {
        $tailwind = @(
            "/** @type {import('tailwindcss').Config} */",
            "export default {",
            '  content: ["./index.html", "./src/**/*.{js,jsx}"],',
            "  theme: {",
            "    extend: {",
            "      colors: {",
            '        surface: "#f6f8fc",',
            '        panel: "#ffffff",',
            '        ink: "#172033",',
            '        muted: "#667085",',
            '        line: "#dfe5f0",',
            '        primary: "#2563eb",',
            '        secondary: "#7c3aed",',
            '        success: "#059669",',
            '        warning: "#d97706",',
            '        danger: "#dc2626",',
            "      },",
            "      boxShadow: {",
            '        panel: "0 10px 28px rgba(20, 31, 51, 0.07)",',
            "      },",
            "      borderRadius: {",
            '        xl: "0.75rem",',
            "      },",
            "      fontFamily: {",
            "        sans: [",
            '          "Inter",',
            '          "ui-sans-serif",',
            '          "system-ui",',
            '          "-apple-system",',
            '          "BlinkMacSystemFont",',
            '          "Segoe UI",',
            '          "sans-serif",',
            "        ],",
            "      },",
            "    },",
            "  },",
            "  plugins: [],",
            "};",
            ""
        ) -join "`n"
        Write-Utf8NoBom $tailwindPath $tailwind
        Write-Host "Restored missing dashboard/tailwind.config.js"
    }
}

function Remove-GeneratedAndLegacyFiles {
    param([string]$Root)

    $forbiddenDirs = @(
        (Join-Path $Root "output"),
        (Join-Path $Root "baselines"),
        (Join-Path $Root "logs"),
        (Join-Path $Root "dashboard\node_modules"),
        (Join-Path $Root "dashboard\dist"),
        (Join-Path $Root "dashboard\public\dashboard_data")
    )
    foreach ($dir in $forbiddenDirs) {
        if (Test-Path $dir) { Remove-Item -LiteralPath $dir -Recurse -Force }
    }

    Get-ChildItem $Root -Directory -Recurse -Force -Filter "__pycache__" -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    Get-ChildItem $Root -File -Recurse -Force -ErrorAction SilentlyContinue | Where-Object {
        $_.Extension -in @(".pyc", ".pyo", ".log", ".xlsx", ".xls", ".csv", ".jsonl") -or
        $_.Name -like "*_state.json"
    } | Remove-Item -Force -ErrorAction SilentlyContinue

    Get-ChildItem $Root -File -Filter "*.zip" -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue

    # Remove only known obsolete release-branded files. Do not mirror-delete
    # arbitrary source files that happen to be absent from the package.
    Get-ChildItem $Root -File -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match "(?i)^(PATCH_NOTES|INSTALL_GUIDE|VALIDATION|MANIFEST|INSTALL|PUBLISH).*V\d+"
    } | Remove-Item -Force -ErrorAction SilentlyContinue

    $legacyContract = Join-Path $Root "release_contract.json"
    if (Test-Path $legacyContract) { Remove-Item -LiteralPath $legacyContract -Force }

    $testsDir = Join-Path $Root "tests"
    if (Test-Path $testsDir) {
        Get-ChildItem $testsDir -File -Filter "test_v*.py" -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction SilentlyContinue
        $fixturesDir = Join-Path $testsDir "fixtures"
        if (Test-Path $fixturesDir) {
            Get-ChildItem $fixturesDir -Directory -ErrorAction SilentlyContinue | Where-Object {
                $_.Name -match "(?i)^v\d+$"
            } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

function Write-Manifest {
    param([string]$Root)

    $manifestPath = Join-Path $Root "MANIFEST_SHA256.txt"

    # Stage first so deleted stale files disappear from git ls-files.
    git -C $Root add -A
    if ($LASTEXITCODE -ne 0) { throw "git add failed before manifest generation." }

    $paths = @(git -C $Root ls-files)
    if ($LASTEXITCODE -ne 0) { throw "git ls-files failed." }

    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($rel in ($paths | Sort-Object)) {
        if ([string]::IsNullOrWhiteSpace($rel)) { continue }
        if ($rel -eq "MANIFEST_SHA256.txt") { continue }
        $full = Join-Path $Root ($rel -replace "/", "\")
        if (!(Test-Path -LiteralPath $full -PathType Leaf)) { continue }
        $hash = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
        $lines.Add("$hash  $rel")
    }
    $content = ($lines -join "`n") + "`n"
    Write-Utf8NoBom $manifestPath $content

    git -C $Root add -- "MANIFEST_SHA256.txt"
    if ($LASTEXITCODE -ne 0) { throw "Unable to stage MANIFEST_SHA256.txt." }
}

# Validate the extracted source package before touching Git.
& $PythonExe (Join-Path $SourceRoot "tools\validate_source_package.py") $SourceRoot
if ($LASTEXITCODE -ne 0) { throw "Source package contains forbidden or missing files." }

if (!(Test-Path $RepoDir)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $RepoDir) | Out-Null
    git clone $RemoteUrl $RepoDir
    if ($LASTEXITCODE -ne 0) { throw "git clone failed." }
}

if (!(Test-Path (Join-Path $RepoDir ".git"))) {
    throw "Not a Git repository: $RepoDir"
}

$origin = git -C $RepoDir remote get-url origin 2>$null
if ($LASTEXITCODE -ne 0) {
    git -C $RepoDir remote add origin $RemoteUrl
    if ($LASTEXITCODE -ne 0) { throw "Unable to add Git origin." }
} elseif ($origin.Trim() -ne $RemoteUrl) {
    git -C $RepoDir remote set-url origin $RemoteUrl
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

# Overlay source non-destructively. We intentionally do NOT use /MIR:
# a packaging omission must never silently delete a valid tracked source file.
robocopy $SourceRoot $RepoDir /E /R:2 /W:1 `
    /XD .git __pycache__ .pytest_cache node_modules dist output baselines `
    /XF MANIFEST_SHA256.txt *.pyc *.pyo *.log *.xlsx *.xls *.csv *.jsonl *.zip
$RoboCode = $LASTEXITCODE
if ($RoboCode -gt 7) { throw "robocopy failed with exit code $RoboCode" }

Remove-GeneratedAndLegacyFiles -Root $RepoDir
Ensure-RepositoryMetadata -Root $RepoDir
Ensure-DashboardBuildConfigs -Root $RepoDir

$required = @(
    ".gitignore",
    ".gitattributes",
    "SKILL.md",
    "README.md",
    "run.py",
    "rebuild_dashboard_history.py",
    "deployment_contract.json",
    "cloud_phone_monitor\main.py",
    "dashboard\package.json",
    "dashboard\postcss.config.js",
    "dashboard\tailwind.config.js",
    "dashboard\src\App.jsx",
    "deployment\windows\update_cloud_phone_dashboard.ps1",
    "deployment\windows\publish_dashboard.ps1",
    "deployment\windows\validate_cloud_phone_dashboard.py"
)
foreach ($rel in $required) {
    if (!(Test-Path -LiteralPath (Join-Path $RepoDir $rel) -PathType Leaf)) {
        throw "Required repository file missing after overlay: $rel"
    }
}

Write-Manifest -Root $RepoDir

$changes = git -C $RepoDir status --porcelain
if (-not $changes) {
    Write-Host "GitHub source repository already matches the current source tree."
    return
}

Write-Host ""
Write-Host "Files to be committed:"
git -C $RepoDir status --short

git -C $RepoDir commit -m "Maintain Cloud Phone Monitor source and deployment"
if ($LASTEXITCODE -ne 0) { throw "git commit failed." }

git -C $RepoDir push origin $Branch
if ($LASTEXITCODE -ne 0) {
    git -C $RepoDir fetch origin
    git -C $RepoDir pull --rebase --autostash origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "git rebase retry failed." }
    git -C $RepoDir push origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "git push failed after retry." }
}

Write-Host "Cloud-Phone-Monitor-Skill source pushed successfully."
Write-Host "Repository metadata (.gitignore/.gitattributes) and MANIFEST_SHA256.txt were regenerated automatically."
