param(
    [string]$SkillRoot = "",
    [switch]$InstallDashboardDependencies,
    [switch]$InstallDevDependencies,
    [switch]$RecreateVenv,
    [string]$PythonVersion = ""
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

$SupportedPythonMinors = @("3.12", "3.13", "3.14")

function Assert-SupportedPythonRequest([string]$Version) {
    if ([string]::IsNullOrWhiteSpace($Version)) { return }
    if ($SupportedPythonMinors -notcontains $Version) {
        throw "Unsupported -PythonVersion '$Version'. Supported CPython minors: $($SupportedPythonMinors -join ', ')."
    }
}

function Get-BasePythonCandidates([string]$RequestedVersion = "") {
    Assert-SupportedPythonRequest $RequestedVersion
    $items = New-Object System.Collections.Generic.List[object]
    $seen = @{}
    function Add-Candidate([string]$Exe, [string[]]$Prefix=@(), [string]$Label="") {
        if ([string]::IsNullOrWhiteSpace($Exe)) { return }
        $key = (($Exe + "|" + ($Prefix -join " ")).ToLowerInvariant())
        if ($seen.ContainsKey($key)) { return }
        $seen[$key] = $true
        $items.Add([pscustomobject]@{Exe=$Exe;Prefix=@($Prefix);Label=$Label})
    }

    # Prefer the active PATH interpreter when it is in the supported range so
    # a machine that already uses Python 3.13/3.14 does not need an artificial
    # downgrade. A requested version (used by CI/repro checks) is exact.
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { Add-Candidate $python.Source @() "PATH python" }

    $versions = if ([string]::IsNullOrWhiteSpace($RequestedVersion)) {
        @("3.14", "3.13", "3.12")
    } else {
        @($RequestedVersion)
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    foreach ($version in $versions) {
        $compact = $version.Replace(".", "")
        if ($py) { Add-Candidate $py.Source @("-$version") "py -$version" }
        foreach ($path in @(
            "C:\Python$compact\python.exe",
            (Join-Path $env:LOCALAPPDATA "Programs\Python\Python$compact\python.exe")
        )) {
            if (Test-Path $path) { Add-Candidate $path @() $path }
        }
        foreach ($pattern in @(
            (Join-Path $env:LOCALAPPDATA "Programs\Python\Python$compact*\python.exe"),
            (Join-Path $env:LOCALAPPDATA "Python\pythoncore-$version*\python.exe")
        )) {
            Get-ChildItem -Path $pattern -File -ErrorAction SilentlyContinue | ForEach-Object {
                Add-Candidate $_.FullName @() $_.FullName
            }
        }
    }
    return $items.ToArray()
}

function Resolve-BasePython([string]$RequestedVersion = "") {
    Assert-SupportedPythonRequest $RequestedVersion
    foreach ($candidate in Get-BasePythonCandidates $RequestedVersion) {
        $probeCode = if ([string]::IsNullOrWhiteSpace($RequestedVersion)) {
            "import sys; v=f'{sys.version_info.major}.{sys.version_info.minor}'; print(sys.executable); raise SystemExit(0 if v in {'3.12','3.13','3.14'} else 3)"
        } else {
            "import sys; v=f'{sys.version_info.major}.{sys.version_info.minor}'; print(sys.executable); raise SystemExit(0 if v == '$RequestedVersion' else 3)"
        }
        $probe = Invoke-CapturedProcess -FilePath $candidate.Exe -Arguments (@($candidate.Prefix) + @("-c", $probeCode)) -TimeoutSeconds 20
        if ($probe.ExitCode -eq 0) {
            $resolved = ($probe.Stdout -split "`r?`n" | Where-Object {$_.Trim()} | Select-Object -Last 1).Trim()
            if ($resolved -and (Test-Path $resolved)) { return $resolved }
            return $candidate.Exe
        }
    }
    if ([string]::IsNullOrWhiteSpace($RequestedVersion)) {
        throw "No supported CPython 3.12-3.14 interpreter was found. Install one of these versions and retry. Python 3.12 remains the recommended release baseline."
    }
    throw "Requested Python $($RequestedVersion).x was not found. Install it or omit -PythonVersion to use any supported CPython 3.12-3.14 interpreter."
}

function Get-PythonMinor([string]$Exe) {
    if (!(Test-Path -LiteralPath $Exe)) { return "" }
    $value = (& $Exe -B -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    if ($LASTEXITCODE -ne 0) { return "" }
    return $value
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
Assert-SupportedPythonRequest $PythonVersion

if ($RecreateVenv -and (Test-Path $VenvRoot)) {
    Remove-Item -LiteralPath $VenvRoot -Recurse -Force
}
if (!(Test-Path $VenvPython)) {
    $BasePython = Resolve-BasePython $PythonVersion
    Write-Host "Base Python: $BasePython"
    Invoke-Checked $BasePython @("-m", "venv", $VenvRoot) "Create dedicated .venv"
}
if (!(Test-Path $VenvPython)) { throw "Virtual environment creation did not produce: $VenvPython" }

$VenvMinor = Get-PythonMinor $VenvPython
if ($SupportedPythonMinors -notcontains $VenvMinor) {
    throw "Existing .venv uses unsupported Python $VenvMinor. Re-run with -RecreateVenv using CPython 3.12, 3.13, or 3.14."
}
if (-not [string]::IsNullOrWhiteSpace($PythonVersion) -and $VenvMinor -ne $PythonVersion) {
    throw "Existing .venv uses Python $VenvMinor but -PythonVersion $PythonVersion was requested. Re-run with -RecreateVenv."
}
Write-Host "Dedicated runtime: $VenvPython (Python $($VenvMinor).x)"

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
    if (-not $npm) { throw "npm was not found. Install Node.js 22 or 24 with npm, or omit -InstallDashboardDependencies." }
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    if (-not $node) { $node = Get-Command node -ErrorAction SilentlyContinue }
    if (-not $node) { throw "node was not found. Install Node.js 22.x or 24.x." }
    $nodeVersion = (& $node.Source --version).Trim()
    if ($LASTEXITCODE -ne 0 -or $nodeVersion -notmatch '^v(22|24)\.') {
        throw "Unsupported Node.js version: $nodeVersion. Supported majors are Node.js 22.x and 24.x; Node 22 remains the recommended baseline."
    }
    if ($nodeVersion -match '^v24\.') { Write-Warning "Using supported Node.js 24.x compatibility runtime; primary release baseline remains Node.js 22.x." }
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
