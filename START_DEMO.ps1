param(
    [string]$SkillRoot = "",
    [int]$DashboardPort = 5173,
    [int]$ApiPort = 8787,
    [switch]$SkipBootstrap,
    [switch]$EvidenceOnly,
    [switch]$BuildOnly,
    [switch]$NoBrowser,
    [switch]$KeepRuntime
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($SkillRoot)) {
    if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) { throw "Unable to determine SkillRoot." }
    $SkillRoot = $PSScriptRoot
}
$SkillRoot = (Resolve-Path -LiteralPath $SkillRoot).Path
$PythonExe = Join-Path $SkillRoot ".venv\Scripts\python.exe"
$DemoRoot = Join-Path $SkillRoot "output\demo_runtime"
$DemoDashboard = Join-Path $DemoRoot "dashboard"
$DemoContext = Join-Path $DemoDashboard "public\dashboard_data\ai"
$ApiProcess = $null
$DashboardProcess = $null
$PreviousContext = $env:AI_CONTEXT_DIR
$PreviousPort = $env:AI_PORT
$PreviousLLM = $env:AI_ENABLE_LLM
$PreviousCors = $env:AI_CORS_ORIGINS
$PreviousLaunchToken = $env:AI_SERVICE_LAUNCH_TOKEN

function Test-PythonProbe {
    param([string]$Code)
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
    return $cmd.Source
}

function Invoke-NpmChecked {
    param([string[]]$Arguments, [string]$Description)
    Write-Host "==> $Description"
    & $script:NpmExe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE." }
}

function Assert-TcpPortAvailable {
    param([int]$Port, [string]$Label)
    $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
    try {
        $listener.Start()
    } catch {
        throw "$Label port $Port is already in use. Stop the existing process or choose another port."
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

function Wait-HttpForProcess {
    param([string]$Uri, $Process, [int]$TimeoutSeconds = 30)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        try {
            $Process.Refresh()
            if ($Process.HasExited) { return $false }
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) { return $true }
        } catch {}
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    return $false
}

Write-Host "============================================================"
Write-Host "Cloud Phone Pricing Intelligence Platform - Synthetic Demo"
Write-Host "============================================================"
Write-Host "Source:  $SkillRoot"
Write-Host "Runtime: $DemoRoot"
Write-Host "Data:    synthetic safe demo only"
Write-Host ""

try {
    if (-not $SkipBootstrap) {
        if (-not (Test-PythonProbe "import sys, playwright, pytest; raise SystemExit(0 if sys.version_info[:2] in {(3,12),(3,13),(3,14)} else 3)")) {
            Write-Host "Bootstrapping supported CPython 3.12-3.14 / Playwright runtime..."
            & (Join-Path $SkillRoot "install_dependencies_windows.ps1") -SkillRoot $SkillRoot -InstallDevDependencies
            if ($LASTEXITCODE -ne 0) { throw "Base runtime bootstrap failed." }
        }
        if (-not (Test-PythonProbe "import fastapi, uvicorn; print('ai runtime ok')")) {
            Write-Host "Installing AI service dependencies..."
            & (Join-Path $SkillRoot "install_ai_dependencies_windows.ps1") -SkillRoot $SkillRoot
            if ($LASTEXITCODE -ne 0) { throw "AI runtime bootstrap failed." }
        }
    }

    if (!(Test-Path -LiteralPath $PythonExe)) {
        throw "Dedicated runtime is missing: $PythonExe. Run START_DEMO.ps1 without -SkipBootstrap or install dependencies first."
    }
    if (-not (Test-PythonProbe "import sys, playwright, pytest, fastapi, uvicorn; raise SystemExit(0 if sys.version_info[:2] in {(3,12),(3,13),(3,14)} else 3)")) {
        throw "Dedicated runtime is incomplete or outside supported CPython 3.12-3.14. Re-run START_DEMO.ps1 without -SkipBootstrap."
    }

    $script:NpmExe = Resolve-Npm

    Write-Host "Preparing isolated demo runtime without modifying real Dashboard data..."
    & $PythonExe -B (Join-Path $SkillRoot "tools\prepare_demo_runtime.py") $SkillRoot $DemoRoot
    if ($LASTEXITCODE -ne 0) { throw "Demo runtime preparation failed." }
    $DemoManifestPath = Join-Path $DemoContext "manifest.json"
    if (!(Test-Path -LiteralPath $DemoManifestPath)) {
        throw "Demo AI context manifest was not generated: $DemoManifestPath"
    }
    $DemoManifest = Get-Content -LiteralPath $DemoManifestPath -Raw | ConvertFrom-Json
    if ([string]$DemoManifest.schema_version -ne "ai-context-v2" -or $DemoManifest.safe_data_only -ne $true) {
        throw "Demo AI manifest failed schema/safety validation."
    }
    $ExpectedRevision = [string]$DemoManifest.data_revision
    if ([string]::IsNullOrWhiteSpace($ExpectedRevision)) { throw "Demo AI manifest has no data_revision." }

    Write-Host "Verifying deterministic AI + FastAPI demo contract..."
    & $PythonExe -B (Join-Path $SkillRoot "tools\verify_demo_contract.py") --context-dir $DemoContext
    if ($LASTEXITCODE -ne 0) { throw "Demo AI contract verification failed." }

    Push-Location $DemoDashboard
    try {
        Invoke-NpmChecked @("ci") "Install isolated demo Dashboard dependencies"
        Invoke-NpmChecked @("run", "build") "Build synthetic demo Dashboard"
    } finally {
        Pop-Location
    }
    if (!(Test-Path -LiteralPath (Join-Path $DemoDashboard "dist\index.html"))) {
        throw "Demo Dashboard build did not produce dist\index.html."
    }

    if ($BuildOnly) {
        Write-Host ""
        Write-Host "DEMO_READY=True"
        Write-Host "Dashboard build: PASS"
        Write-Host "AI context:      PASS"
        Write-Host "FastAPI contract: PASS"
        return
    }

    Assert-TcpPortAvailable -Port $DashboardPort -Label "Dashboard"

    if (-not $EvidenceOnly) {
        Assert-TcpPortAvailable -Port $ApiPort -Label "AI API"
        $LaunchToken = [Guid]::NewGuid().ToString("N")
        $env:AI_CONTEXT_DIR = $DemoContext
        $env:AI_PORT = [string]$ApiPort
        $env:AI_ENABLE_LLM = "0"
        $env:AI_CORS_ORIGINS = "http://127.0.0.1:$DashboardPort,http://localhost:$DashboardPort"
        $env:AI_SERVICE_LAUNCH_TOKEN = $LaunchToken
        Set-Content -LiteralPath (Join-Path $DemoDashboard ".env.local") -Encoding UTF8 -Value "VITE_AI_API_BASE_URL=http://127.0.0.1:$ApiPort"

        $apiOut = Join-Path $DemoRoot "ai_api.stdout.log"
        $apiErr = Join-Path $DemoRoot "ai_api.stderr.log"
        # Module launch avoids an unquoted script-path argument and therefore
        # works when SkillRoot contains spaces.
        $ApiProcess = Start-Process -FilePath $PythonExe `
            -ArgumentList @("-B", "-m", "uvicorn", "ai_backend.app:app", "--host", "127.0.0.1", "--port", [string]$ApiPort) `
            -WorkingDirectory $SkillRoot -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr
        $health = Wait-AiServiceReady -Uri "http://127.0.0.1:$ApiPort/health" -Process $ApiProcess `
            -ExpectedToken $LaunchToken -ExpectedRevision $ExpectedRevision -TimeoutSeconds 30
        if ($null -eq $health) {
            throw "AI API did not become the expected healthy process on port $ApiPort. Inspect $apiErr"
        }
    } else {
        Remove-Item -LiteralPath (Join-Path $DemoDashboard ".env.local") -Force -ErrorAction SilentlyContinue
    }

    $dashOut = Join-Path $DemoRoot "dashboard.stdout.log"
    $dashErr = Join-Path $DemoRoot "dashboard.stderr.log"
    $DashboardProcess = Start-Process -FilePath $script:NpmExe -ArgumentList @("run", "dev", "--", "--port", [string]$DashboardPort) `
        -WorkingDirectory $DemoDashboard -PassThru -WindowStyle Hidden -RedirectStandardOutput $dashOut -RedirectStandardError $dashErr
    $DashboardUrl = "http://127.0.0.1:$DashboardPort/"
    if (-not (Wait-HttpForProcess -Uri $DashboardUrl -Process $DashboardProcess -TimeoutSeconds 30)) {
        throw "Dashboard dev server did not become available from the process started by this run. Inspect $dashErr"
    }

    Write-Host ""
    Write-Host "DEMO_READY=True"
    Write-Host "Dashboard: $DashboardUrl"
    if ($EvidenceOnly) {
        Write-Host "AI mode:   Evidence Mode (static safe AI context; no backend key)"
    } else {
        Write-Host "AI API:    http://127.0.0.1:$ApiPort/"
        Write-Host "AI mode:   FastAPI evidence backend (LLM disabled by default)"
        Write-Host "AI PID:    $($health.service_pid) (launcher $($ApiProcess.Id))"
    }
    Write-Host "Dataset:   synthetic / safe_data_only=true"
    Write-Host "Revision:  $ExpectedRevision"
    Write-Host ""

    if (-not $NoBrowser) {
        try { Start-Process $DashboardUrl | Out-Null } catch {}
    }
    [void](Read-Host "Press ENTER to stop the demo")
} finally {
    if ($DashboardProcess -and -not $DashboardProcess.HasExited) {
        try { Stop-Process -Id $DashboardProcess.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
    if ($ApiProcess -and -not $ApiProcess.HasExited) {
        try { Stop-Process -Id $ApiProcess.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
    if ($null -eq $PreviousContext) { Remove-Item Env:AI_CONTEXT_DIR -ErrorAction SilentlyContinue } else { $env:AI_CONTEXT_DIR = $PreviousContext }
    if ($null -eq $PreviousPort) { Remove-Item Env:AI_PORT -ErrorAction SilentlyContinue } else { $env:AI_PORT = $PreviousPort }
    if ($null -eq $PreviousLLM) { Remove-Item Env:AI_ENABLE_LLM -ErrorAction SilentlyContinue } else { $env:AI_ENABLE_LLM = $PreviousLLM }
    if ($null -eq $PreviousCors) { Remove-Item Env:AI_CORS_ORIGINS -ErrorAction SilentlyContinue } else { $env:AI_CORS_ORIGINS = $PreviousCors }
    if ($null -eq $PreviousLaunchToken) { Remove-Item Env:AI_SERVICE_LAUNCH_TOKEN -ErrorAction SilentlyContinue } else { $env:AI_SERVICE_LAUNCH_TOKEN = $PreviousLaunchToken }
    if (-not $KeepRuntime -and (Test-Path -LiteralPath $DemoRoot)) {
        Remove-Item -LiteralPath $DemoRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
