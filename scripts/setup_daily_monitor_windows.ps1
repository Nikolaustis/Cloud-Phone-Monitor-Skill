param(
    [string]$TaskName = "CloudPhoneMonitorDaily",
    [string]$ScheduleTime = "10:00",
    [string]$Publisher = "C:\Sites\update_cloud_phone_dashboard.ps1"
)
$ErrorActionPreference = "Stop"
if (!(Test-Path $Publisher)) { throw "publisher not found: $Publisher. Run INSTALL.ps1 first." }

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Publisher`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $ScheduleTime
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel LeastPrivilege
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Cloud Phone Monitor: collect, build and publish GitHub Pages." -Force | Out-Null
Write-Host "Created/updated task: $TaskName"
Write-Host "Schedule: weekdays $ScheduleTime"
Write-Host "Publisher: $Publisher"
