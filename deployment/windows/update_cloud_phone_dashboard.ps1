param(
    [string]$SkillRoot = (Join-Path $env:USERPROFILE ".codex\skills\cloud-phone-monitor-skill"),
    [string]$PublisherConfigPath = "",
    [switch]$SkipLoginPreflight
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

function Write-SchedulerStatus([string]$Status, [string]$Message = "") {
    try {
        $logDir = Join-Path $SkillRoot "output\scheduler_logs"
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        $path = Join-Path $logDir "schedule_status.json"
        $scheduleTime = "10:00"
        if (Test-Path $path) {
            try {
                $oldStatus = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
                if ($oldStatus.schedule_time_local) {
                    $scheduleTime = [string]$oldStatus.schedule_time_local
                }
            } catch {}
        }
        $payload = [ordered]@{
            scheduler_enabled = $true
            scheduler_type = "windows_task_scheduler"
            schedule_time_local = $scheduleTime
            last_run_time = (Get-Date).ToString("s")
            last_run_status = $Status
            last_run_message = $Message
            logs_path = "output/scheduler_logs"
            stale_after_hours = 30
        }
        $payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $path
    } catch {
        Write-Warning "Unable to update scheduler status: $($_.Exception.Message)"
    }
}

$PythonExe = Resolve-PythonExe
$SitesRoot = $PSScriptRoot
$LogsDir = Join-Path $SkillRoot "logs"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
$LogPath = Join-Path $LogsDir ("daily_update_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")
$TranscriptStarted = $false

if ([string]::IsNullOrWhiteSpace($PublisherConfigPath)) {
    $PublisherConfigPath = Join-Path $SkillRoot "publisher.local.json"
}

try {
    Start-Transcript -Path $LogPath -Force | Out-Null
    $TranscriptStarted = $true
    Write-SchedulerStatus "running" "Daily update started"

    Write-Host "============================================================"
    Write-Host "Cloud Phone Dashboard Daily Update"
    Write-Host "============================================================"

    Write-Host "Step 0: Check required paths and deployment contract"
    foreach ($path in @(
        $SkillRoot,
        (Join-Path $SkillRoot "run.py"),
        (Join-Path $SkillRoot "rebuild_dashboard_history.py"),
        (Join-Path $SkillRoot "dashboard\package.json"),
        (Join-Path $SkillRoot "deployment_contract.json"),
        (Join-Path $SitesRoot "deployment_contract.json")
    )) {
        if (!(Test-Path $path)) { throw "Required path not found: $path" }
    }

    $SkillContract = Get-Content -Raw -LiteralPath (Join-Path $SkillRoot "deployment_contract.json") | ConvertFrom-Json
    $InstalledContract = Get-Content -Raw -LiteralPath (Join-Path $SitesRoot "deployment_contract.json") | ConvertFrom-Json

    if ($SkillContract.schema_version -ne $InstalledContract.schema_version -or
        $SkillContract.history_storage -ne $InstalledContract.history_storage -or
        $SkillContract.publisher_capability -ne $InstalledContract.publisher_capability) {
        throw "Skill/deployment contract mismatch. Re-run INSTALL.ps1 from the current source package."
    }

    if (-not $SkipLoginPreflight) {
        Write-Host "Step 1: Login preflight check"
        $Preflight = Join-Path $SitesRoot "check_skill_login_state.py"
        if (!(Test-Path $Preflight)) { throw "Login preflight script not found: $Preflight" }
        & $PythonExe $Preflight --skill-root $SkillRoot --report (Join-Path $SitesRoot "login_preflight_report.json")
        if ($LASTEXITCODE -ne 0) { throw "Login preflight failed with exit code $LASTEXITCODE" }
    } else {
        Write-Host "Step 1: Login preflight skipped by explicit switch."
    }

    Write-Host "Step 2: Run cloud phone collector"
    Set-Location $SkillRoot
    & $PythonExe .\run.py
    if ($LASTEXITCODE -ne 0) { throw "Cloud phone collector failed with exit code $LASTEXITCODE" }

    Write-Host "Step 3: Rebuild dashboard history"
    & $PythonExe .\rebuild_dashboard_history.py --incremental
    if ($LASTEXITCODE -ne 0) { throw "Dashboard history rebuild failed with exit code $LASTEXITCODE" }

    Write-Host "Step 4: Build dashboard"
    Set-Location (Join-Path $SkillRoot "dashboard")
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed with exit code $LASTEXITCODE" }

    Write-Host "Step 5: Validate built JS syntax"
    $js = Get-ChildItem -Path (Join-Path $SkillRoot "dashboard\dist\assets") -Filter "*.js" |
        Sort-Object Length -Descending |
        Select-Object -First 1
    if (-not $js) { throw "No built JS asset found." }

    node --check $js.FullName
    if ($LASTEXITCODE -ne 0) { throw "Built JS syntax validation failed." }

    Write-Host "Step 6: Validate Dashboard and optionally publish GitHub Pages"
    & (Join-Path $SitesRoot "publish_dashboard.ps1") `
        -SkillRoot $SkillRoot `
        -ConfigPath $PublisherConfigPath
    if ($LASTEXITCODE -ne 0) {
        throw "Dashboard validation/publish step failed with exit code $LASTEXITCODE"
    }

    Write-SchedulerStatus "success" "Collection/build completed; optional publishing step completed"
    Write-Host "Cloud Phone Dashboard Daily Update finished successfully."
} catch {
    Write-SchedulerStatus "failed" $_.Exception.Message
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "Cloud Phone Dashboard Daily Update Failed"
    Write-Host $_.Exception.Message
    Write-Host "============================================================"
    throw
} finally {
    if ($TranscriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
}
