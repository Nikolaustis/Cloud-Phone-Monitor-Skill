param(
    [string]$SkillRoot = "",
    [switch]$SkipWindowsSmoke
)
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($SkillRoot)) {
    if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) { throw "Unable to determine SkillRoot." }
    $SkillRoot = $PSScriptRoot
}
$SkillRoot = (Resolve-Path -LiteralPath $SkillRoot).Path
$PythonExe = Join-Path $SkillRoot ".venv\Scripts\python.exe"
if (!(Test-Path $PythonExe)) {
    throw "Dedicated test/runtime Python is missing: $PythonExe. Run .\install_dependencies_windows.ps1 -InstallDevDependencies first."
}
$PreviousDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE
$env:PYTHONDONTWRITEBYTECODE = "1"
try {
    if (-not $SkipWindowsSmoke) {
        $windowsSmoke = Join-Path $SkillRoot "tests\auth_state_machine\windows_login_smoke.ps1"
        if (!(Test-Path $windowsSmoke)) { throw "Windows login smoke test missing: $windowsSmoke" }
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $windowsSmoke
        if ($LASTEXITCODE -ne 0) { throw "Windows login state-machine smoke tests failed." }
    }

    & $PythonExe -B -c "import pytest; print('pytest OK')"
    if ($LASTEXITCODE -ne 0) {
        throw "pytest is not installed in the Skill .venv. Run .\install_dependencies_windows.ps1 -InstallDevDependencies."
    }
    & $PythonExe -B -m pytest -q (Join-Path $SkillRoot "tests")
    if ($LASTEXITCODE -ne 0) { throw "pytest failed with exit code $LASTEXITCODE" }

    Write-Host "All requested tests passed using: $PythonExe"
} finally {
    if ($null -eq $PreviousDontWriteBytecode) {
        Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONDONTWRITEBYTECODE = $PreviousDontWriteBytecode
    }
}
