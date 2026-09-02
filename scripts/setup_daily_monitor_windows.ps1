param(
    [string]$TaskName = "CloudPhoneMonitorDaily",
    [string]$ScheduleTime = "10:00",
    [Alias("Publisher")]
    [string]$Updater = "C:\Sites\update_cloud_phone_dashboard.ps1"
)
$ErrorActionPreference = "Stop"

if (!(Test-Path $Updater)) {
    throw "Daily updater not found: $Updater. Run INSTALL.ps1 first."
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Updater`""

$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At $ScheduleTime

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel LeastPrivilege

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Cloud Phone Monitor: collect and build locally; publish only when publisher.local.json is configured." `
    -Force | Out-Null

Write-Host "Created/updated task: $TaskName"
Write-Host "Schedule: weekdays $ScheduleTime"
Write-Host "Updater: $Updater"
