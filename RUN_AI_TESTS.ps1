param([string]$SkillRoot = "")
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($SkillRoot)) {
    if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) { throw "Unable to determine SkillRoot." }
    $SkillRoot = $PSScriptRoot
}
$SkillRoot = (Resolve-Path -LiteralPath $SkillRoot).Path
$PythonExe = Join-Path $SkillRoot ".venv\Scripts\python.exe"
if (!(Test-Path $PythonExe)) { throw "Dedicated Skill runtime is missing: $PythonExe" }
& $PythonExe -B -m pytest -q (Join-Path $SkillRoot "tests\ai")
if ($LASTEXITCODE -ne 0) { throw "AI tests failed." }
& $PythonExe -B (Join-Path $SkillRoot "evals\run_eval.py")
if ($LASTEXITCODE -ne 0) { throw "AI deterministic benchmark failed." }
Write-Host "AI tests and deterministic benchmark passed."
