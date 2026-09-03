$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LoginSource = Join-Path $RepoRoot "LOGIN.ps1"
$InstallSource = Join-Path $RepoRoot "INSTALL.ps1"
$TempRoot = Join-Path ([IO.Path]::GetTempPath()) ("cloud_phone_login_test_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "ASSERTION FAILED: $Message" }
}

try {
    # 1) Default SkillRoot must resolve from $PSScriptRoot under powershell.exe -File.
    $LoginDir = Join-Path $TempRoot "login_copy"
    New-Item -ItemType Directory -Force -Path $LoginDir | Out-Null
    Copy-Item $LoginSource (Join-Path $LoginDir "LOGIN.ps1") -Force
    $statusOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $LoginDir "LOGIN.ps1") UgPhone -Status 2>&1
    Assert-True ($LASTEXITCODE -eq 0) "LOGIN.ps1 -Status should execute with default SkillRoot"
    Assert-True (($statusOutput -join "`n") -match [regex]::Escape("Skill root: $LoginDir")) "default SkillRoot should equal PSScriptRoot"

    # 2) Historical saved status without an active control file must NOT satisfy -Complete.
    $AuthDir = Join-Path $LoginDir "output\auth"
    New-Item -ItemType Directory -Force -Path $AuthDir | Out-Null
    @{ session_id = "old-session"; platform = "UgPhone"; status = "saved_and_verified" } |
        ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $AuthDir "ugphone_login_status.json")
    $completeOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $LoginDir "LOGIN.ps1") UgPhone -Complete 2>&1
    Assert-True ($LASTEXITCODE -ne 0) "stale historical status must not make -Complete succeed"
    Assert-True (($completeOutput -join "`n") -match "No active UgPhone login session exists") "stale completion should explain missing active session"

    # 3) A stale/mismatched PID identity must never be terminated by -Cancel.
    $benign = Start-Process powershell.exe -ArgumentList '-NoProfile -Command "Start-Sleep -Seconds 30"' -PassThru
    try {
        Start-Sleep -Milliseconds 300
        $path = ""
        try { $path = [string](Get-Process -Id $benign.Id).Path } catch {}
        @{
            schema_version = 2
            session_id = "stale-session"
            platform = "UgPhone"
            process_id = $benign.Id
            process_path = $path
            process_start_ticks = "1"
        } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $AuthDir "ugphone_login_agent_session.json")
        $cancelOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $LoginDir "LOGIN.ps1") UgPhone -Cancel 2>&1
        Assert-True ($LASTEXITCODE -eq 0) "-Cancel should clean stale metadata without killing a mismatched PID"
        $stillRunning = Get-Process -Id $benign.Id -ErrorAction SilentlyContinue
        Assert-True ($null -ne $stillRunning) "mismatched PID identity must not be terminated"
    } finally {
        Stop-Process -Id $benign.Id -Force -ErrorAction SilentlyContinue
    }

    # 4) INSTALL.ps1 must fail before copy when a required source file is absent.
    $InstallDir = Join-Path $TempRoot "incomplete_package"
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Copy-Item $InstallSource (Join-Path $InstallDir "INSTALL.ps1") -Force
    $installOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallDir "INSTALL.ps1") `
        -SkillRoot (Join-Path $TempRoot "installed") -SitesRoot (Join-Path $TempRoot "sites") 2>&1
    Assert-True ($LASTEXITCODE -ne 0) "incomplete source package must fail installation"
    Assert-True (($installOutput -join "`n") -match "Required source package file missing") "installer must fail-fast with a required-file message"

    Write-Host "Windows login state-machine smoke tests passed."
} finally {
    Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
