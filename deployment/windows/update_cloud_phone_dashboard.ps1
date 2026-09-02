param(
    [string]$SkillRoot = (Join-Path $env:USERPROFILE ".codex\skills\cloud-phone-monitor-skill"),
    [string]$SiteRepo = "C:\Sites\Cloud-Phone-Dashboard-Site",
    [switch]$SkipLoginPreflight
)

$ErrorActionPreference = "Stop"
# CANONICAL_DAILY_UPDATE

function Resolve-PythonExe {
    $candidates = @("C:\Python314\python.exe", "C:\Python313\python.exe", "C:\Python312\python.exe")
    foreach ($candidate in $candidates) { if (Test-Path $candidate) { return $candidate } }
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
                if ($oldStatus.schedule_time_local) { $scheduleTime = [string]$oldStatus.schedule_time_local }
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
$LogsDir = Join-Path $SkillRoot "logs"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
$LogPath = Join-Path $LogsDir ("daily_publish_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")
$TranscriptStarted = $false

try {
    Start-Transcript -Path $LogPath -Force | Out-Null
    $TranscriptStarted = $true
    Write-SchedulerStatus "running" "Daily update started"

    Write-Host "============================================================"
    Write-Host "Cloud Phone Dashboard Daily Update"
    Write-Host "============================================================"

    Write-Host "Step 0: Check required paths and deployment contract"
    foreach ($path in @($SkillRoot, (Join-Path $SkillRoot "run.py"), (Join-Path $SkillRoot "rebuild_dashboard_history.py"), (Join-Path $SkillRoot "dashboard\package.json"), (Join-Path $SkillRoot "deployment_contract.json"), "C:\Sites\deployment_contract.json")) {
        if (!(Test-Path $path)) { throw "Required path not found: $path" }
    }
    $SkillContract = Get-Content -Raw -LiteralPath (Join-Path $SkillRoot "deployment_contract.json") | ConvertFrom-Json
    $PublisherContract = Get-Content -Raw -LiteralPath "C:\Sites\deployment_contract.json" | ConvertFrom-Json
    if ($SkillContract.schema_version -ne $PublisherContract.schema_version -or
        $SkillContract.history_storage -ne $PublisherContract.history_storage -or
        $SkillContract.publisher_capability -ne $PublisherContract.publisher_capability) {
        throw "Skill/publisher deployment contract mismatch. Re-run INSTALL.ps1 from the current source package."
    }
    if ($SkillContract.history_storage -ne "gzip-json-v1") { throw "Unexpected history storage contract: $($SkillContract.history_storage)" }
    if ($SkillContract.publisher_capability -ne "gzip-history-pages") { throw "Unexpected publisher capability: $($SkillContract.publisher_capability)" }

    if (-not $SkipLoginPreflight) {
        Write-Host "Step 1: Login preflight check"
        $Preflight = "C:\Sites\check_skill_login_state.py"
        if (!(Test-Path $Preflight)) { throw "Login preflight script not found: $Preflight" }
        & $PythonExe $Preflight --skill-root $SkillRoot --report "C:\Sites\login_preflight_report.json"
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
    $js = Get-ChildItem -Path (Join-Path $SkillRoot "dashboard\dist\assets") -Filter "*.js" | Sort-Object Length -Descending | Select-Object -First 1
    if (-not $js) { throw "No built JS asset found." }
    node --check $js.FullName
    if ($LASTEXITCODE -ne 0) { throw "Built JS syntax validation failed." }

    Write-Host "Step 6/7: Validate, mirror, commit and push GitHub Pages"
    & "C:\Sites\publish_dashboard.ps1" -SkillRoot $SkillRoot -SiteRepo $SiteRepo
    if ($LASTEXITCODE -ne 0) { throw "Dashboard publish failed with exit code $LASTEXITCODE" }

    Write-SchedulerStatus "success" "Collection/build/publish completed"
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
    if ($TranscriptStarted) { try { Stop-Transcript | Out-Null } catch {} }
}
