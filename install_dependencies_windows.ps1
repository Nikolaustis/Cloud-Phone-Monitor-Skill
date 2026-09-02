param(
    [string]$SkillRoot = (Split-Path -Parent $MyInvocation.MyCommand.Path)
)
$ErrorActionPreference = "Stop"

function Resolve-PythonExe {
    $candidates = @("C:\Python314\python.exe", "C:\Python313\python.exe", "C:\Python312\python.exe")
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Python executable not found."
}

$PythonExe = Resolve-PythonExe
Set-Location $SkillRoot

& $PythonExe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed." }

& $PythonExe -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "Playwright Chromium install failed." }

Set-Location (Join-Path $SkillRoot "dashboard")
npm ci
if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }

Write-Host "Dependencies installed successfully."
