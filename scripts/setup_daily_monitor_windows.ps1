param(
    [string]$TaskName = "CloudPhoneMonitorDaily",
    [string]$ScheduleTime = "10:00",
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillDir = Split-Path -Parent $ScriptDir
$LogDir = Join-Path $SkillDir "output\scheduler_logs"
$StatusPath = Join-Path $LogDir "schedule_status.json"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$taskCommand = "Set-Location -LiteralPath '$SkillDir'; New-Item -ItemType Directory -Force -Path 'output\scheduler_logs' | Out-Null; & '$PythonExe' run.py *>> 'output\scheduler_logs\daily.log'"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -Command ""$taskCommand"""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $ScheduleTime
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel LeastPrivilege
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Daily Cloud Phone Monitor collection. Logs are written to output\scheduler_logs." -Force | Out-Null

$status = [ordered]@{
    scheduler_enabled = $true
    scheduler_type = "windows_task_scheduler"
    schedule_time_local = $ScheduleTime
    task_name = $TaskName
    logs_path = "output\scheduler_logs"
    installed_at_local = (Get-Date).ToString("s")
    last_run_status = "unknown"
    stale_after_hours = 30
}

$status | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -Path $StatusPath

Write-Host "Created Windows Task Scheduler task: $TaskName"
Write-Host "Working directory: $SkillDir"
Write-Host "Logs: $LogDir"
Write-Host "Status file: $StatusPath"
