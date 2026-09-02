param(
    [string]$SkillRoot = (Join-Path $env:USERPROFILE ".codex\skills\cloud-phone-monitor-skill"),
    [string]$PublisherConfigPath = ""
)
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($PublisherConfigPath)) {
    $PublisherConfigPath = Join-Path $SkillRoot "publisher.local.json"
}

& (Join-Path $PSScriptRoot "publish_dashboard.ps1") `
    -SkillRoot $SkillRoot `
    -ConfigPath $PublisherConfigPath `
    -CommitPrefix "Resume publish dashboard"

if ($LASTEXITCODE -ne 0) {
    throw "Resume publish failed with exit code $LASTEXITCODE"
}
