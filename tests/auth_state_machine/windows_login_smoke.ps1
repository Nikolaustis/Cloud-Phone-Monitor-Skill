$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LoginSource = Join-Path $RepoRoot "LOGIN.ps1"
$InstallSource = Join-Path $RepoRoot "INSTALL.ps1"
$TempRoot = Join-Path ([IO.Path]::GetTempPath()) ("cloud_phone_login_test_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "ASSERTION FAILED: $Message" }
}

function Quote-Arg([string]$Value) {
    if ($null -eq $Value) { return '""' }
    if ($Value -notmatch '[\s"]') { return $Value }
    return '"' + (($Value -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
}

function Invoke-ChildPowerShell([string[]]$Arguments, [int]$TimeoutSeconds = 60) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "powershell.exe"
    $psi.Arguments = (($Arguments | ForEach-Object { Quote-Arg ([string]$_) }) -join " ")
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    try {
        if (-not $proc.Start()) { return [pscustomobject]@{ExitCode=-1;Output="process_start_failed"} }
        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            try { $proc.Kill() } catch {}
            return [pscustomobject]@{ExitCode=-2;Output="process_timeout"}
        }
        $output = ($proc.StandardOutput.ReadToEnd() + "`n" + $proc.StandardError.ReadToEnd()).Trim()
        return [pscustomobject]@{ExitCode=[int]$proc.ExitCode;Output=$output}
    } finally {
        try { $proc.Dispose() } catch {}
    }
}

try {
    # 1) Default SkillRoot must resolve from $PSScriptRoot under powershell.exe -File.
    $LoginDir = Join-Path $TempRoot "login_copy"
    New-Item -ItemType Directory -Force -Path $LoginDir | Out-Null
    Copy-Item $LoginSource (Join-Path $LoginDir "LOGIN.ps1") -Force
    $r = Invoke-ChildPowerShell @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $LoginDir "LOGIN.ps1"), "UgPhone", "-Status")
    Assert-True ($r.ExitCode -eq 0) "LOGIN.ps1 -Status should execute with default SkillRoot"
    Assert-True ($r.Output -match [regex]::Escape("Skill root: $LoginDir")) "default SkillRoot should equal PSScriptRoot"

    # 2) Historical saved status without an active control file must NOT satisfy -Complete.
    $AuthDir = Join-Path $LoginDir "output\auth"
    New-Item -ItemType Directory -Force -Path $AuthDir | Out-Null
    @{ session_id = "old-session"; platform = "UgPhone"; status = "saved_and_verified" } |
        ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $AuthDir "ugphone_login_status.json")
    $r = Invoke-ChildPowerShell @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $LoginDir "LOGIN.ps1"), "UgPhone", "-Complete")
    Assert-True ($r.ExitCode -ne 0) "stale historical status must not make -Complete succeed"
    Assert-True ($r.Output -match "No active UgPhone login session exists") "stale completion should explain missing active session"

    # 3) A stale/mismatched PID identity must never be terminated by -Cancel.
    $benign = Start-Process powershell.exe -ArgumentList '-NoProfile -Command "Start-Sleep -Seconds 30"' -PassThru
    try {
        Start-Sleep -Milliseconds 300
        $path = ""
        try { $path = [string](Get-Process -Id $benign.Id).Path } catch {}
        @{
            schema_version = 4
            session_id = "stale-session"
            platform = "UgPhone"
            process_id = $benign.Id
            process_path = $path
            process_start_ticks = "1"
        } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $AuthDir "ugphone_login_agent_session.json")
        $r = Invoke-ChildPowerShell @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $LoginDir "LOGIN.ps1"), "UgPhone", "-Cancel")
        Assert-True ($r.ExitCode -eq 0) "-Cancel should clean stale metadata without killing a mismatched PID"
        $stillRunning = Get-Process -Id $benign.Id -ErrorAction SilentlyContinue
        Assert-True ($null -ne $stillRunning) "mismatched PID identity must not be terminated"
    } finally {
        Stop-Process -Id $benign.Id -Force -ErrorAction SilentlyContinue
    }

    # 4) INSTALL.ps1 must fail before copy when a required source file is absent.
    $InstallDir = Join-Path $TempRoot "incomplete_package"
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Copy-Item $InstallSource (Join-Path $InstallDir "INSTALL.ps1") -Force
    $r = Invoke-ChildPowerShell @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $InstallDir "INSTALL.ps1"),
        "-SkillRoot", (Join-Path $TempRoot "installed"), "-SitesRoot", (Join-Path $TempRoot "sites")
    )
    Assert-True ($r.ExitCode -ne 0) "incomplete source package must fail installation"
    Assert-True ($r.Output -match "Required source package file missing") "installer must fail-fast with a required-file message"

    # 5) Source==destination handling must be present in the actual installer.
    $installerText = Get-Content -Raw -LiteralPath $InstallSource
    Assert-True ($installerText -match '\$SameRoot') "installer should calculate source/target identity"
    Assert-True ($installerText -match 'skipping self-copy') "installer should skip copy when PackageRoot equals SkillRoot"
    Assert-True ($installerText -match 'Unblock-File') "trusted installer should unblock downloaded package scripts without changing machine policy"

    # 6) Windows PowerShell 5.1 must not use the List[object] @($list) conversion that fails at runtime.
    $loginText = Get-Content -Raw -LiteralPath $LoginSource
    $depsText = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "install_dependencies_windows.ps1")
    Assert-True ($loginText -notmatch 'return @\(\$candidates\)') "LOGIN.ps1 must avoid incompatible List[object] array conversion"
    Assert-True ($depsText -match 'return \$items\.ToArray\(\)') "dependency installer should convert List[object] via ToArray()"

    # 7) PowerShell 7 should parse/run -Status too when pwsh is installed.
    $pwsh = Get-Command pwsh.exe -ErrorAction SilentlyContinue
    if ($pwsh) {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $pwsh.Source
        $psi.Arguments = "-NoProfile -File " + (Quote-Arg (Join-Path $LoginDir "LOGIN.ps1")) + " UgPhone -Status"
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $proc = New-Object System.Diagnostics.Process
        $proc.StartInfo = $psi
        [void]$proc.Start()
        [void]$proc.WaitForExit(30000)
        $pwshOutput = ($proc.StandardOutput.ReadToEnd() + "`n" + $proc.StandardError.ReadToEnd())
        Assert-True ($proc.ExitCode -eq 0) "PowerShell 7 LOGIN.ps1 -Status should execute"
        Assert-True ($pwshOutput -match 'LOGIN_AGENT_STATE=') "PowerShell 7 should produce login state output"
        $proc.Dispose()
    }

    Write-Host "Windows login state-machine smoke tests passed."
} finally {
    Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
