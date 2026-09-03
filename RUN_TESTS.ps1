param(
    [string]$SkillRoot = ""
)
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($SkillRoot)) { $SkillRoot = $PSScriptRoot }
$SkillRoot = (Resolve-Path -LiteralPath $SkillRoot).Path

$windowsSmoke = Join-Path $SkillRoot "tests\auth_state_machine\windows_login_smoke.ps1"
if (!(Test-Path $windowsSmoke)) { throw "Windows login smoke test missing: $windowsSmoke" }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $windowsSmoke
if ($LASTEXITCODE -ne 0) { throw "Windows login state-machine smoke tests failed." }

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw "python was not found on PATH." }
& $python.Source -c "import pytest" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "pytest is not installed for PATH python. Run: python -m pip install -r requirements-dev.txt"
}
& $python.Source -m pytest -q (Join-Path $SkillRoot "tests")
if ($LASTEXITCODE -ne 0) { throw "pytest failed with exit code $LASTEXITCODE" }
