param(
    [string]$SkillRoot = "",
    [switch]$InstallDashboardDependencies,
    [switch]$InstallDevDependencies,
    [switch]$RecreateVenv
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($SkillRoot)) {
    if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        throw "Unable to determine SkillRoot. Pass -SkillRoot explicitly."
    }
    $SkillRoot = $PSScriptRoot
}
$SkillRoot = (Resolve-Path -LiteralPath $SkillRoot).Path

# If this trusted source came from an Internet-downloaded ZIP, extracted PowerShell
# files may inherit Mark-of-the-Web and be blocked by RemoteSigned.  Running this
# installer via -ExecutionPolicy Bypass is the explicit trust boundary; unblocking
# only local script files avoids changing the machine-wide execution policy.
try {
    Get-ChildItem -LiteralPath $SkillRoot -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @(".ps1", ".psm1", ".bat") } |
        ForEach-Object { Unblock-File -LiteralPath $_.FullName -ErrorAction SilentlyContinue }
} catch {}

function Quote-Arg([string]$Value) {
    if ($null -eq $Value) { return '""' }
    if ($Value -notmatch '[\s"]') { return $Value }
    return '"' + (($Value -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
}

function Invoke-CapturedProcess {
    param([string]$FilePath, [string[]]$Arguments = @(), [int]$TimeoutSeconds = 60)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = (($Arguments | ForEach-Object { Quote-Arg ([string]$_) }) -join " ")
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    try {
        if (-not $proc.Start()) { return [pscustomobject]@{ExitCode=-1;Stdout="";Stderr="process_start_failed"} }
        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            try { $proc.Kill() } catch {}
            return [pscustomobject]@{ExitCode=-2;Stdout=$proc.StandardOutput.ReadToEnd();Stderr="process_timeout"}
        }
        return [pscustomobject]@{
            ExitCode=[int]$proc.ExitCode
            Stdout=$proc.StandardOutput.ReadToEnd()
            Stderr=$proc.StandardError.ReadToEnd()
        }
    } catch {
        return [pscustomobject]@{ExitCode=-1;Stdout="";Stderr=$_.Exception.Message}
    } finally {
        try { $proc.Dispose() } catch {}
    }
}

function Get-BasePythonCandidates {
    $items = New-Object System.Collections.Generic.List[object]
    $seen = @{}
    function Add-Candidate([string]$Exe, [string[]]$Prefix=@(), [string]$Label="") {
        if ([string]::IsNullOrWhiteSpace($Exe)) { return }
        $key = (($Exe + "|" + ($Prefix -join " ")).ToLowerInvariant())
        if ($seen.ContainsKey($key)) { return }
        $seen[$key] = $true
        $items.Add([pscustomobject]@{Exe=$Exe;Prefix=@($Prefix);Label=$Label})
    }

    foreach ($path in @("C:\Python314\python.exe", "C:\Python313\python.exe", "C:\Python312\python.exe")) {
        if (Test-Path $path) { Add-Candidate $path @() $path }
    }
    foreach ($pattern in @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python*\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Python\pythoncore-*\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Python\bin\python.exe")
    )) {
        Get-ChildItem -Path $pattern -File -ErrorAction SilentlyContinue | ForEach-Object {
            Add-Candidate $_.FullName @() $_.FullName
        }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { Add-Candidate $python.Source @() "PATH python" }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { Add-Candidate $py.Source @("-3") "py -3" }
    return $items.ToArray()
}

function Resolve-BasePython {
    foreach ($candidate in Get-BasePythonCandidates) {
        $probe = Invoke-CapturedProcess -FilePath $candidate.Exe -Arguments (@($candidate.Prefix) + @("-c", "import sys; print(sys.executable); raise SystemExit(0 if sys.version_info >= (3,12) else 3)")) -TimeoutSeconds 20
        if ($probe.ExitCode -eq 0) {
            $resolved = ($probe.Stdout -split "`r?`n" | Where-Object {$_.Trim()} | Select-Object -Last 1).Trim()
            if ($resolved -and (Test-Path $resolved)) { return $resolved }
            return $candidate.Exe
        }
    }
    throw "No runnable Python 3.12+ interpreter was found. Install Python 3.12+ and retry."
}

function Invoke-Checked {
    param([string]$FilePath, [string[]]$Arguments, [string]$Description)
    Write-Host "==> $Description"
    $argumentLine = (($Arguments | ForEach-Object { Quote-Arg ([string]$_) }) -join " ")
    $proc = Start-Process -FilePath $FilePath -ArgumentList $argumentLine -Wait -PassThru -NoNewWindow
    if ($proc.ExitCode -ne 0) {
        throw "$Description failed with exit code $($proc.ExitCode)."
    }
}

$required = @(
    (Join-Path $SkillRoot "requirements.txt"),
    (Join-Path $SkillRoot "constraints-runtime.txt"),
    (Join-Path $SkillRoot "cloud_phone_monitor\login_controller.py"),
    (Join-Path $SkillRoot "cloud_phone_monitor\login_helper_session_entry.py")
)
foreach ($path in $required) {
    if (!(Test-Path $path)) { throw "Required dependency-install file missing: $path" }
}

$VenvRoot = Join-Path $SkillRoot ".venv"
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
$BasePython = Resolve-BasePython
Write-Host "Base Python: $BasePython"
Write-Host "Dedicated runtime: $VenvPython"

if ($RecreateVenv -and (Test-Path $VenvRoot)) {
    Remove-Item -LiteralPath $VenvRoot -Recurse -Force
}
if (!(Test-Path $VenvPython)) {
    Invoke-Checked $BasePython @("-m", "venv", $VenvRoot) "Create dedicated .venv"
}
if (!(Test-Path $VenvPython)) { throw "Virtual environment creation did not produce: $VenvPython" }

Invoke-Checked $VenvPython @("-m", "pip", "install", "--upgrade", "pip") "Upgrade .venv pip"
$RuntimeConstraints = Join-Path $SkillRoot "constraints-runtime.txt"
Invoke-Checked $VenvPython @("-m", "pip", "install", "-r", (Join-Path $SkillRoot "requirements.txt"), "-c", $RuntimeConstraints) "Install Python runtime requirements with pinned Playwright constraint"
Invoke-Checked $VenvPython @("-m", "playwright", "install", "chromium") "Install Playwright Chromium paired with the pinned package"

if ($InstallDevDependencies) {
    $dev = Join-Path $SkillRoot "requirements-dev.txt"
    if (!(Test-Path $dev)) { throw "Dev requirements file missing: $dev" }
    Invoke-Checked $VenvPython @("-m", "pip", "install", "-r", $dev) "Install test requirements"
}

$probeCode = @'
import importlib.metadata as md, json, os, pathlib, sys
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
path = p.chromium.executable_path
if not path or not os.path.exists(path):
    p.stop(); raise SystemExit("Chromium executable missing")
b = p.chromium.launch(headless=True)
b.close(); p.stop()
try: version = md.version("playwright")
except Exception: version = "unknown"
expected_version = sys.argv[2]
if expected_version and version != expected_version:
    raise SystemExit(f"Playwright version mismatch: expected={expected_version} actual={version}")
out = pathlib.Path(sys.argv[1])
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({
    "python_executable": sys.executable,
    "python_version": sys.version.split()[0],
    "playwright_version": version,
    "chromium_executable": path,
    "launch_probe_ok": True,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"python": sys.executable, "playwright": version, "chromium": path, "launch_probe_ok": True}))
'@
$RuntimeReport = Join-Path $SkillRoot "output\runtime\python_environment.json"
$PinnedPlaywright = "1.62.0"
Invoke-Checked $VenvPython @("-c", $probeCode, $RuntimeReport, $PinnedPlaywright) "Verify pinned Playwright Chromium can launch headless"

if ($InstallDashboardDependencies) {
    $packageJson = Join-Path $SkillRoot "dashboard\package.json"
    if (!(Test-Path $packageJson)) { throw "Dashboard package.json missing: $packageJson" }
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npm) { $npm = Get-Command npm -ErrorAction SilentlyContinue }
    if (-not $npm) { throw "npm was not found. Install Node.js/npm or omit -InstallDashboardDependencies." }
    $oldLocation = Get-Location
    try {
        Set-Location (Join-Path $SkillRoot "dashboard")
        Invoke-Checked $npm.Source @("ci") "Install Dashboard dependencies"
    } finally {
        Set-Location $oldLocation
    }
} else {
    Write-Host "Dashboard/npm dependencies skipped. Use -InstallDashboardDependencies when needed."
}

Write-Host ""
Write-Host "Runtime dependencies installed successfully."
Write-Host "Locked Python: $VenvPython"
Write-Host "Runtime diagnostic: $RuntimeReport"
Write-Host "Google Chrome is not required; Playwright Chromium was launch-tested."
