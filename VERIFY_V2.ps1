param(
    [string]$SkillRoot = "",
    [switch]$Bootstrap,
    [switch]$SkipDashboardBuild,
    [switch]$SkipRelease,
    [switch]$KeepDemoRuntime
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($SkillRoot)) {
    if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) { throw "Unable to determine SkillRoot." }
    $SkillRoot = $PSScriptRoot
}
$SkillRoot = (Resolve-Path -LiteralPath $SkillRoot).Path
$PythonExe = Join-Path $SkillRoot ".venv\Scripts\python.exe"
$DemoRoot = Join-Path $SkillRoot "output\verification_demo_runtime"
$DemoDashboard = Join-Path $DemoRoot "dashboard"
$DemoContext = Join-Path $DemoDashboard "public\dashboard_data\ai"
$ReportPath = Join-Path $SkillRoot "output\runtime\v2_release_verification.json"
$ReleaseZip = Join-Path $SkillRoot "cloud-phone-pricing-intelligence.public-release.zip"
$ApiProcess = $null
$PreviousContext = $env:AI_CONTEXT_DIR
$PreviousPort = $env:AI_PORT
$PreviousLLM = $env:AI_ENABLE_LLM
$PreviousCors = $env:AI_CORS_ORIGINS
$PreviousLaunchToken = $env:AI_SERVICE_LAUNCH_TOKEN
$Results = [ordered]@{}

function Set-Result([string]$Name, [string]$Value) {
    $script:Results[$Name] = $Value
    Write-Host ("{0,-30} {1}" -f $Name, $Value)
}

function Test-PythonProbe([string]$Code) {
    if (!(Test-Path -LiteralPath $PythonExe)) { return $false }
    & $PythonExe -B -c $Code *> $null
    return ($LASTEXITCODE -eq 0)
}

function Resolve-Npm {
    $cmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $cmd) { $cmd = Get-Command npm -ErrorAction SilentlyContinue }
    if (-not $cmd) { throw "npm was not found. Install Node.js 22.x or 24.x and retry." }
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    if (-not $node) { $node = Get-Command node -ErrorAction SilentlyContinue }
    if (-not $node) { throw "node was not found. Install Node.js 22.x or 24.x and retry." }
    $version = (& $node.Source --version).Trim()
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^v(22|24)\.') {
        throw "Unsupported Node.js version: $version. Supported majors are Node.js 22.x and 24.x."
    }
    $script:NodeVersion = $version
    Set-Result "Node runtime" "PASS ($version)"
    return $cmd.Source
}

function Assert-TcpPortAvailable {
    param([int]$Port, [string]$Label)
    $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
    try {
        $listener.Start()
    } catch {
        throw "$Label port $Port is already in use. Verification refuses to reuse an existing service."
    } finally {
        try { $listener.Stop() } catch {}
    }
}

function Wait-AiServiceReady {
    param(
        [string]$Uri,
        $Process,
        [string]$ExpectedToken,
        [string]$ExpectedRevision,
        [int]$TimeoutSeconds = 30
    )
    # Windows venv python.exe may redirect to a direct child interpreter.
    $expectedExecutable = (& $PythonExe -B -c "import sys; print(sys._base_executable)").Trim()
    if ($LASTEXITCODE -ne 0) { return $null }
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        try {
            $Process.Refresh()
            if ($Process.HasExited) { return $null }
            $value = Invoke-RestMethod -Uri $Uri -TimeoutSec 2
            $processMatches = [int]$value.service_pid -eq [int]$Process.Id
            if (-not $processMatches -and [int]$value.service_pid -gt 0) {
                $child = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$value.service_pid)" -ErrorAction Stop
                $processMatches = $null -ne $child -and
                    [int]$child.ParentProcessId -eq [int]$Process.Id -and
                    [string]::Equals([string]$child.ExecutablePath, $expectedExecutable, [StringComparison]::OrdinalIgnoreCase) -and
                    $child.CreationDate -ge $Process.StartTime.AddSeconds(-1)
            }
            if (
                $value.ok -eq $true -and
                [string]$value.service -eq "cloud-phone-pricing-intelligence-api" -and
                $processMatches -and
                [string]$value.service_launch_token -eq $ExpectedToken -and
                [string]$value.api_version -eq "2.0.0-beta.1" -and
                [string]$value.schema_version -eq "ai-context-v2" -and
                [string]$value.data_revision -eq $ExpectedRevision -and
                $value.safe_data_only -eq $true
            ) {
                return $value
            }
        } catch {}
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    return $null
}

function Write-VerificationReport([bool]$ReleaseReady) {
    $dir = Split-Path -Parent $ReportPath
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $payload = [ordered]@{
        schema_version = "v2-release-verification-v3"
        verified_at_utc = [DateTime]::UtcNow.ToString("o")
        skill_root = $SkillRoot
        release_ready = $ReleaseReady
        recommended_runtime = [ordered]@{
            python = "3.12.x"
            node = "22.x"
            playwright = "1.62.0"
        }
        supported_runtime = [ordered]@{
            python = "3.12.x, 3.13.x, 3.14.x"
            node = "22.x or 24.x"
            playwright = "1.62.0"
        }
        actual_runtime = [ordered]@{
            python = $script:PythonMinor
            node = $script:NodeVersion
        }
        results = $Results
    }
    $tmp = "$ReportPath.tmp.$PID"
    $payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $tmp -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $ReportPath -Force
}

Write-Host "============================================================"
Write-Host "Cloud Phone Pricing Intelligence Platform v2 verification"
Write-Host "============================================================"
Write-Host "SkillRoot: $SkillRoot"
Write-Host "Recommended baseline: Python 3.12.x / Node 22.x / Playwright 1.62.0`nSupported compatibility: Python 3.12-3.14 / Node 22 or 24"
Write-Host ""

try {
    if ($Bootstrap) {
        Write-Host "Bootstrapping required runtime layers..."
        $installArgs = @{ SkillRoot = $SkillRoot; InstallDevDependencies = $true }
        if (Test-Path -LiteralPath $PythonExe) {
            & $PythonExe -B -c "import sys; raise SystemExit(0 if sys.version_info[:2] in {(3,12),(3,13),(3,14)} else 3)" *> $null
            if ($LASTEXITCODE -ne 0) { $installArgs["RecreateVenv"] = $true }
        }
        & (Join-Path $SkillRoot "install_dependencies_windows.ps1") @installArgs
        if ($LASTEXITCODE -ne 0) { throw "Base runtime bootstrap failed." }
        & (Join-Path $SkillRoot "install_ai_dependencies_windows.ps1") -SkillRoot $SkillRoot
        if ($LASTEXITCODE -ne 0) { throw "AI runtime bootstrap failed." }
    }

    if (!(Test-Path -LiteralPath $PythonExe)) {
        throw "Dedicated runtime is missing: $PythonExe. Run VERIFY_V2.ps1 -Bootstrap or install dependencies first."
    }
    if (-not (Test-PythonProbe "import sys; raise SystemExit(0 if sys.version_info[:2] in {(3,12),(3,13),(3,14)} else 3)")) {
        throw "Dedicated runtime must use supported CPython 3.12, 3.13, or 3.14. Recreate .venv with VERIFY_V2.ps1 -Bootstrap."
    }
    $script:PythonMinor = (& $PythonExe -B -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    Set-Result "Dedicated Python" "PASS ($($script:PythonMinor).x)"

    if (-not (Test-PythonProbe "import playwright, pytest, fastapi, uvicorn; print('imports ok')")) {
        throw "Required Python modules are missing from the dedicated .venv. Run VERIFY_V2.ps1 -Bootstrap."
    }
    Set-Result "Python dependencies" "PASS"

    & $PythonExe -B -c "import importlib.metadata as m; assert m.version('playwright') == '1.62.0'; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); print(p.chromium.executable_path); b.close(); p.stop()"
    if ($LASTEXITCODE -ne 0) { throw "Pinned Playwright 1.62.0 Chromium launch probe failed." }
    Set-Result "Playwright Chromium" "PASS"

    $npm = Resolve-Npm

    Write-Host ""
    Write-Host "Running base behavior tests..."
    & (Join-Path $SkillRoot "RUN_TESTS.ps1") -SkillRoot $SkillRoot
    if ($LASTEXITCODE -ne 0) { throw "Base behavior tests failed." }
    Set-Result "Base test suite" "PASS"

    Write-Host ""
    Write-Host "Running AI tests and deterministic benchmark..."
    & (Join-Path $SkillRoot "RUN_AI_TESTS.ps1") -SkillRoot $SkillRoot
    if ($LASTEXITCODE -ne 0) { throw "AI tests/benchmark failed." }
    Set-Result "AI test suite" "PASS"

    $ProductionDashboardData = Join-Path $SkillRoot "dashboard\public\dashboard_data"
    $ProductionDurationInventory = Join-Path $ProductionDashboardData "duration_price_comparison.json"
    if (Test-Path -LiteralPath $ProductionDurationInventory) {
        Write-Host ""
        Write-Host "Refreshing and validating production AI selector inventory..."
        & $PythonExe -B (Join-Path $SkillRoot "build_ai_context.py") --data-dir $ProductionDashboardData
        if ($LASTEXITCODE -ne 0) { throw "Production AI context rebuild failed." }
        & $PythonExe -B (Join-Path $SkillRoot "tools\verify_ai_selector_inventory.py") --data-dir $ProductionDashboardData
        if ($LASTEXITCODE -ne 0) { throw "Production AI selector inventory is incomplete or stale." }
        Set-Result "Production AI context" "PASS"
    } else {
        Set-Result "Production AI context" "SKIPPED (no local Dashboard runtime data)"
    }

    Write-Host ""
    Write-Host "Preparing isolated synthetic demo runtime..."
    & $PythonExe -B (Join-Path $SkillRoot "tools\prepare_demo_runtime.py") $SkillRoot $DemoRoot
    if ($LASTEXITCODE -ne 0) { throw "Demo runtime preparation failed." }
    $DemoManifestPath = Join-Path $DemoContext "manifest.json"
    if (!(Test-Path -LiteralPath $DemoManifestPath)) { throw "Demo AI manifest missing." }
    $DemoManifest = Get-Content -LiteralPath $DemoManifestPath -Raw | ConvertFrom-Json
    if ([string]$DemoManifest.schema_version -ne "ai-context-v2" -or $DemoManifest.safe_data_only -ne $true) {
        throw "Demo AI manifest failed schema/safety validation."
    }
    $ExpectedRevision = [string]$DemoManifest.data_revision
    if ([string]::IsNullOrWhiteSpace($ExpectedRevision)) { throw "Demo AI manifest has no data_revision." }
    Set-Result "Demo AI context" "PASS"

    & $PythonExe -B (Join-Path $SkillRoot "tools\verify_demo_contract.py") --context-dir $DemoContext
    if ($LASTEXITCODE -ne 0) { throw "Demo semantic/API contract failed." }
    Set-Result "AI semantic contract" "PASS"

    $ApiPort = 18787
    Assert-TcpPortAvailable -Port $ApiPort -Label "AI API verification"
    $LaunchToken = [Guid]::NewGuid().ToString("N")
    $env:AI_CONTEXT_DIR = $DemoContext
    $env:AI_PORT = [string]$ApiPort
    $env:AI_ENABLE_LLM = "0"
    $env:AI_CORS_ORIGINS = "http://127.0.0.1:5173,http://localhost:5173"
    $env:AI_SERVICE_LAUNCH_TOKEN = $LaunchToken
    $apiOut = Join-Path $DemoRoot "verification_ai_api.stdout.log"
    $apiErr = Join-Path $DemoRoot "verification_ai_api.stderr.log"
    # Launch by module so a SkillRoot containing spaces never becomes an
    # unquoted Python script argument.
    $ApiProcess = Start-Process -FilePath $PythonExe `
        -ArgumentList @("-B", "-m", "uvicorn", "ai_backend.app:app", "--host", "127.0.0.1", "--port", [string]$ApiPort) `
        -WorkingDirectory $SkillRoot -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr
    $health = Wait-AiServiceReady -Uri "http://127.0.0.1:$ApiPort/health" -Process $ApiProcess `
        -ExpectedToken $LaunchToken -ExpectedRevision $ExpectedRevision -TimeoutSeconds 30
    if ($null -eq $health) { throw "FastAPI did not become the expected healthy process. Inspect $apiErr" }
    $brief = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/ai/brief" -TimeoutSec 5
    if ([string]::IsNullOrWhiteSpace([string]$brief.answer)) { throw "FastAPI market brief smoke test returned no answer." }
    if ([string]$brief.data_revision -ne $ExpectedRevision) { throw "FastAPI market brief revision mismatch." }
    Set-Result "FastAPI network smoke" "PASS (PID $($ApiProcess.Id))"
    if ($ApiProcess -and -not $ApiProcess.HasExited) { Stop-Process -Id $ApiProcess.Id -Force -ErrorAction SilentlyContinue }
    $ApiProcess = $null

    if (-not $SkipDashboardBuild) {
        Push-Location $DemoDashboard
        try {
            & $npm ci
            if ($LASTEXITCODE -ne 0) { throw "npm ci failed in isolated demo Dashboard." }
            & $npm run build
            if ($LASTEXITCODE -ne 0) { throw "npm run build failed in isolated demo Dashboard." }
        } finally {
            Pop-Location
        }
        if (!(Test-Path -LiteralPath (Join-Path $DemoDashboard "dist\index.html"))) {
            throw "Dashboard build did not produce dist\index.html."
        }
        Set-Result "Dashboard demo build" "PASS"
    } else {
        Set-Result "Dashboard demo build" "SKIPPED"
    }

    if (-not $SkipRelease) {
        Write-Host ""
        Write-Host "Preparing canonical public release after runtime verification..."
        & (Join-Path $SkillRoot "PREPARE_RELEASE.ps1") -SkillRoot $SkillRoot -OutputZip $ReleaseZip -SkipTests
        if ($LASTEXITCODE -ne 0) { throw "Canonical public release preparation failed." }
        if (!(Test-Path -LiteralPath $ReleaseZip)) { throw "Canonical public release ZIP missing: $ReleaseZip" }
        Set-Result "Public release contract" "PASS"
    } else {
        Set-Result "Public release contract" "SKIPPED"
    }

    $ReleaseReady = (-not $SkipDashboardBuild) -and (-not $SkipRelease)
    Write-VerificationReport $ReleaseReady

    Write-Host ""
    Write-Host "============================================================"
    Write-Host "Verification summary"
    Write-Host "============================================================"
    foreach ($key in $Results.Keys) {
        Write-Host ("{0,-30} {1}" -f $key, $Results[$key])
    }
    Write-Host "Report: $ReportPath"
    if ($ReleaseReady) {
        Write-Host "RELEASE_READY=True"
    } else {
        Write-Host "RELEASE_READY=False"
        Write-Host "Reason: one or more verification stages were explicitly skipped."
    }
} catch {
    Set-Result "Verification" "FAIL"
    Write-VerificationReport $false
    throw
} finally {
    if ($ApiProcess -and -not $ApiProcess.HasExited) {
        try { Stop-Process -Id $ApiProcess.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
    if ($null -eq $PreviousContext) { Remove-Item Env:AI_CONTEXT_DIR -ErrorAction SilentlyContinue } else { $env:AI_CONTEXT_DIR = $PreviousContext }
    if ($null -eq $PreviousPort) { Remove-Item Env:AI_PORT -ErrorAction SilentlyContinue } else { $env:AI_PORT = $PreviousPort }
    if ($null -eq $PreviousLLM) { Remove-Item Env:AI_ENABLE_LLM -ErrorAction SilentlyContinue } else { $env:AI_ENABLE_LLM = $PreviousLLM }
    if ($null -eq $PreviousCors) { Remove-Item Env:AI_CORS_ORIGINS -ErrorAction SilentlyContinue } else { $env:AI_CORS_ORIGINS = $PreviousCors }
    if ($null -eq $PreviousLaunchToken) { Remove-Item Env:AI_SERVICE_LAUNCH_TOKEN -ErrorAction SilentlyContinue } else { $env:AI_SERVICE_LAUNCH_TOKEN = $PreviousLaunchToken }
    if (-not $KeepDemoRuntime -and (Test-Path -LiteralPath $DemoRoot)) {
        Remove-Item -LiteralPath $DemoRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
