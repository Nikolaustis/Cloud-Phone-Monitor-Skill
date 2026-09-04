param(
    [string]$SkillRoot = "",
    [string]$OutputZip = ""
)
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($SkillRoot)) {
    if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) { throw "Unable to determine SkillRoot." }
    $SkillRoot = $PSScriptRoot
}
$SkillRoot = (Resolve-Path -LiteralPath $SkillRoot).Path
$PythonExe = Join-Path $SkillRoot ".venv\Scripts\python.exe"
if (!(Test-Path $PythonExe)) {
    throw "Dedicated runtime missing: $PythonExe. Run .\install_dependencies_windows.ps1 -InstallDevDependencies first."
}
if ([string]::IsNullOrWhiteSpace($OutputZip)) {
    $OutputZip = Join-Path $SkillRoot "cloud-phone-monitor.public-release.zip"
}
$StageRoot = Join-Path ([IO.Path]::GetTempPath()) ("cloud_phone_monitor_release_" + [Guid]::NewGuid().ToString("N"))
$ManifestInStage = Join-Path $StageRoot "MANIFEST_SHA256.txt"
$ManifestInSource = Join-Path $SkillRoot "MANIFEST_SHA256.txt"
$PreviousDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE
$env:PYTHONDONTWRITEBYTECODE = "1"

try {
    Write-Host "Step 1: Run behavior tests without writing Python bytecode"
    & (Join-Path $SkillRoot "RUN_TESTS.ps1") -SkillRoot $SkillRoot
    if ($LASTEXITCODE -ne 0) { throw "Tests failed." }

    Write-Host "Step 2: Build explicit-allowlist public staging tree"
    & $PythonExe -B (Join-Path $SkillRoot "tools\build_release_staging.py") $SkillRoot $StageRoot
    if ($LASTEXITCODE -ne 0) { throw "Release staging failed." }

    Write-Host "Step 3: Validate staged public source and exact allowlist"
    & $PythonExe -B (Join-Path $StageRoot "tools\validate_source_package.py") $StageRoot --exact-public-tree
    if ($LASTEXITCODE -ne 0) { throw "Staged source package validation failed." }

    Write-Host "Step 4: Generate deterministic Manifest inside staging"
    & $PythonExe -B (Join-Path $StageRoot "tools\generate_manifest.py") $StageRoot
    if ($LASTEXITCODE -ne 0) { throw "Manifest generation failed." }

    Write-Host "Step 5: Validate staged Manifest"
    & $PythonExe -B (Join-Path $StageRoot "tools\validate_manifest.py") $StageRoot
    if ($LASTEXITCODE -ne 0) { throw "Manifest validation failed." }

    Write-Host "Step 6: Rebuild release contract and compare against staged Manifest before mutating working tree"
    & $PythonExe -B (Join-Path $SkillRoot "tools\validate_public_release.py") $SkillRoot --manifest $ManifestInStage
    if ($LASTEXITCODE -ne 0) { throw "Public release reproducibility validation failed before Manifest commit." }

    Write-Host "Step 7: Commit validated Manifest to working tree"
    Copy-Item -LiteralPath $ManifestInStage -Destination $ManifestInSource -Force

    Write-Host "Step 8: Validate committed Manifest against a fresh staging rebuild"
    & $PythonExe -B (Join-Path $SkillRoot "tools\validate_public_release.py") $SkillRoot --manifest $ManifestInSource
    if ($LASTEXITCODE -ne 0) { throw "Committed Manifest does not reproduce the public release tree." }

    Write-Host "Step 9: Build deterministic canonical public ZIP"
    & $PythonExe -B (Join-Path $StageRoot "tools\build_release_zip.py") $StageRoot $OutputZip
    if ($LASTEXITCODE -ne 0 -or !(Test-Path $OutputZip)) { throw "Public release ZIP was not created: $OutputZip" }

    $zipHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $OutputZip).Hash.ToLowerInvariant()
    Write-Host ""
    Write-Host "Release preparation passed."
    Write-Host "Manifest refreshed: $ManifestInSource"
    Write-Host "Canonical public package: $OutputZip"
    Write-Host "Canonical package SHA-256: $zipHash"
    Write-Host "Upload the staged/public package contents rather than local runtime/private working-tree files."
} finally {
    Remove-Item -LiteralPath $StageRoot -Recurse -Force -ErrorAction SilentlyContinue
    if ($null -eq $PreviousDontWriteBytecode) {
        Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONDONTWRITEBYTECODE = $PreviousDontWriteBytecode
    }
}
