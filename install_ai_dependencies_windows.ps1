param(
    [string]$SkillRoot = ""
)
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($SkillRoot)) {
    if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) { throw "Unable to determine SkillRoot." }
    $SkillRoot = $PSScriptRoot
}
$SkillRoot = (Resolve-Path -LiteralPath $SkillRoot).Path
$PythonExe = Join-Path $SkillRoot ".venv\Scripts\python.exe"
$Requirements = Join-Path $SkillRoot "requirements-ai.txt"
if (!(Test-Path $PythonExe)) {
    throw "Dedicated Skill runtime is missing: $PythonExe. Run install_dependencies_windows.ps1 first."
}
if (!(Test-Path $Requirements)) { throw "AI requirements file not found: $Requirements" }

& $PythonExe -B -c "import sys; raise SystemExit(0 if sys.version_info[:2] in {(3,12),(3,13),(3,14)} else 3)"
if ($LASTEXITCODE -ne 0) {
    throw "AI runtime requires a supported CPython 3.12-3.14 environment. Recreate .venv with VERIFY_V2.ps1 -Bootstrap."
}

Write-Host "Installing Cloud Phone Pricing Intelligence dependencies into: $PythonExe"
& $PythonExe -B -m pip install -r $Requirements
if ($LASTEXITCODE -ne 0) { throw "AI dependency installation failed." }
& $PythonExe -B -c "import fastapi, uvicorn; print('AI backend dependencies OK')"
if ($LASTEXITCODE -ne 0) { throw "AI backend dependency probe failed." }
Write-Host "AI dependencies installed."
Write-Host "Next: & `"$PythonExe`" -B .\build_ai_context.py"
Write-Host "Then: & `"$PythonExe`" -B .\run_ai_api.py"
