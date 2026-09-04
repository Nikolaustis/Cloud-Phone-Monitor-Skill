param(
    [string]$SkillRoot = (Join-Path $env:USERPROFILE ".codex\skills\cloud-phone-monitor-skill"),
    [string]$SiteRepo = "C:\Sites\Cloud-Phone-Dashboard-Site"
)
$ErrorActionPreference = "Stop"
#_RESUME_PUBLISH
& "C:\Sites\publish_dashboard.ps1" -SkillRoot $SkillRoot -SiteRepo $SiteRepo -CommitPrefix "Resume publish dashboard"
if ($LASTEXITCODE -ne 0) { throw "resume publish failed with exit code $LASTEXITCODE" }
