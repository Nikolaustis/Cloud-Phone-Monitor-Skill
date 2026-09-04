param(
    [string]$SkillRoot = "",
    [switch]$SkipDashboardBuild
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($SkillRoot)) {
    if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) { throw "Unable to determine SkillRoot." }
    $SkillRoot = $PSScriptRoot
}
$SkillRoot = (Resolve-Path -LiteralPath $SkillRoot).Path
$PythonExe = Join-Path $SkillRoot ".venv\Scripts\python.exe"
$ReportPath = Join-Path $SkillRoot "output\runtime\real_collector_verification.json"
$AuthReport = Join-Path $SkillRoot "output\runtime\real_collector_auth_preflight.json"
$LatestSummary = Join-Path $SkillRoot "output\latest\run_summary.json"
$AiManifest = Join-Path $SkillRoot "dashboard\public\dashboard_data\ai\manifest.json"

if (!(Test-Path -LiteralPath $PythonExe)) {
    throw "Dedicated runtime is missing: $PythonExe. Run VERIFY_V2.ps1 -Bootstrap first."
}
& $PythonExe -B -c "import sys; raise SystemExit(0 if sys.version_info[:2] in {(3,12),(3,13),(3,14)} else 3)" *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Dedicated runtime uses an unsupported Python version. Run VERIFY_V2.ps1 -Bootstrap with CPython 3.12-3.14."
}

$results = [ordered]@{}
function Set-Result([string]$Name, [string]$Value) {
    $script:results[$Name] = $Value
    Write-Host ("{0,-30} {1}" -f $Name, $Value)
}
function Write-Report([bool]$Ready) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ReportPath) | Out-Null
    [ordered]@{
        schema_version = "real-collector-verification-v1"
        verified_at_utc = [DateTime]::UtcNow.ToString("o")
        skill_root = $SkillRoot
        real_collector_ready = $Ready
        results = $results
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
}

Write-Host "============================================================"
Write-Host "Cloud Phone Pricing Intelligence - REAL collector acceptance"
Write-Host "============================================================"
Write-Host "This check uses private local login state and performs a live collection."
Write-Host ""

try {
    Write-Host "Checking live authentication for all supported platforms..."
    & $PythonExe -B (Join-Path $SkillRoot "deployment\windows\check_skill_login_state.py") `
        --skill-root $SkillRoot --report $AuthReport
    if ($LASTEXITCODE -ne 0) { throw "Live authentication preflight failed. Repair login locally before collection." }
    Set-Result "Live auth preflight" "PASS"

    Write-Host ""
    Write-Host "Running canonical live collector across all configured platforms..."
    Push-Location $SkillRoot
    try {
        & $PythonExe -B (Join-Path $SkillRoot "run.py")
        if ($LASTEXITCODE -ne 0) { throw "Canonical collector failed." }
    } finally {
        Pop-Location
    }
    if (!(Test-Path -LiteralPath $LatestSummary)) { throw "Latest run_summary.json was not produced." }
    $summary = Get-Content -LiteralPath $LatestSummary -Raw | ConvertFrom-Json
    $requiredPlatforms = @("UgPhone", "VSPhone", "Redfinger", "LDCloud")
    foreach ($platform in $requiredPlatforms) {
        $prop = $summary.records_by_platform.PSObject.Properties[$platform]
        $count = if ($null -eq $prop) { 0 } else { [int]$prop.Value }
        if ($count -le 0) { throw "Live collection produced no records for $platform." }
    }
    Set-Result "Four-platform collection" "PASS"

    Write-Host ""
    Write-Host "Rebuilding AI semantic context from the newly collected Dashboard dataset..."
    & $PythonExe -B (Join-Path $SkillRoot "build_ai_context.py")
    if ($LASTEXITCODE -ne 0) { throw "AI context build failed after live collection." }
    if (!(Test-Path -LiteralPath $AiManifest)) { throw "AI context manifest missing after live collection." }
    $manifest = Get-Content -LiteralPath $AiManifest -Raw | ConvertFrom-Json
    if ([string]$manifest.schema_version -ne "ai-context-v2") { throw "Unexpected live AI context schema." }
    Set-Result "Live AI context" "PASS"

    if (-not $SkipDashboardBuild) {
        $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
        if (-not $npm) { $npm = Get-Command npm -ErrorAction SilentlyContinue }
        if (-not $npm) { throw "npm was not found. Install Node.js 22.x or 24.x." }
        $node = Get-Command node.exe -ErrorAction SilentlyContinue
        if (-not $node) { $node = Get-Command node -ErrorAction SilentlyContinue }
        if (-not $node) { throw "node was not found. Install Node.js 22.x or 24.x." }
        $nodeVersion = (& $node.Source --version).Trim()
        if ($LASTEXITCODE -ne 0 -or $nodeVersion -notmatch '^v(22|24)\.') {
            throw "Unsupported Node.js version: $nodeVersion. Supported majors are Node.js 22.x and 24.x."
        }
        Push-Location (Join-Path $SkillRoot "dashboard")
        try {
            & $npm.Source ci
            if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
            & $npm.Source run build
            if ($LASTEXITCODE -ne 0) { throw "Dashboard build failed after live collection." }
        } finally {
            Pop-Location
        }
        Set-Result "Live Dashboard build" "PASS"
    } else {
        Set-Result "Live Dashboard build" "SKIPPED"
    }

    $ready = -not $SkipDashboardBuild
    Write-Report $ready
    Write-Host "Report: $ReportPath"
    if ($ready) {
        Write-Host "REAL_COLLECTOR_READY=True"
    } else {
        Write-Host "REAL_COLLECTOR_READY=False"
        Write-Host "Reason: Dashboard build was explicitly skipped."
    }
} catch {
    Set-Result "Verification" "FAIL"
    Write-Report $false
    throw
}
