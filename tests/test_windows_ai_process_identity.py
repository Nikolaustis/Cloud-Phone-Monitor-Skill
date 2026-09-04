"""Exercise both PowerShell readiness functions against venv process identities."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows process identity contract")
@pytest.mark.parametrize("entrypoint", ["VERIFY_V2.ps1", "START_DEMO.ps1"])
def test_readiness_accepts_venv_child_but_rejects_unrelated_process(entrypoint):
    root = Path(__file__).resolve().parents[1]
    code = r'''
$ErrorActionPreference = 'Stop'
$PythonExe = $env:AI_TEST_PYTHON
$tokens = $null; $errors = $null
$tree = [System.Management.Automation.Language.Parser]::ParseFile($env:AI_TEST_SCRIPT, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'PowerShell parse error' }
$function = $tree.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Wait-AiServiceReady' }, $true)
Invoke-Expression $function.Extent.Text
$expectedExe = (& $PythonExe -B -c 'import sys; print(sys._base_executable)').Trim()
$started = Get-Date
$fakeProcess = [pscustomobject]@{Id=4100; HasExited=$false; StartTime=$started}
$fakeProcess | Add-Member ScriptMethod Refresh {}
$script:health = [pscustomobject]@{
    ok=$true; service='cloud-phone-pricing-intelligence-api'; service_pid=4101
    service_launch_token='test-launch'; api_version='2.0.0-beta.1'
    schema_version='ai-context-v2'; data_revision='test-revision'; safe_data_only=$true
}
$script:child = [pscustomobject]@{ParentProcessId=4100; ExecutablePath=$expectedExe; CreationDate=$started}
function Invoke-RestMethod { param($Uri, $TimeoutSec) return $script:health }
function Get-CimInstance { param($ClassName, $Filter, $ErrorAction) return $script:child }
function Assert-Ready([bool]$Expected) {
    $result = Wait-AiServiceReady -Uri 'http://unused.invalid/' -Process $fakeProcess -ExpectedToken 'test-launch' -ExpectedRevision 'test-revision' -TimeoutSeconds 0
    if (($null -ne $result) -ne $Expected) { throw 'Unexpected process identity decision' }
}
Assert-Ready $true
$script:child.ParentProcessId=9999; Assert-Ready $false
$script:child.ParentProcessId=4100
$script:child.ExecutablePath='C:\unrelated\python.exe'; Assert-Ready $false
$script:child.ExecutablePath=$expectedExe
$script:child.CreationDate=$started.AddMinutes(-1); Assert-Ready $false
$script:child.CreationDate=$started
$script:health.service_launch_token='wrong-launch'; Assert-Ready $false
$script:health.service_launch_token='test-launch'
$script:health.service_pid=4100; Assert-Ready $true
Write-Output 'identity cases passed'
'''
    env = os.environ.copy()
    env.update(AI_TEST_SCRIPT=str(root / entrypoint), AI_TEST_PYTHON=sys.executable)
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", code],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "identity cases passed" in result.stdout
