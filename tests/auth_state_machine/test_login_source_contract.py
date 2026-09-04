from __future__ import annotations

from pathlib import Path

from cloud_phone_monitor.auth_file_transaction import commit_auth_artifacts

ROOT = Path(__file__).resolve().parents[2]


def test_login_uses_post_param_script_root_dedicated_venv_and_launch_probe() -> None:
    text = (ROOT / "LOGIN.ps1").read_text(encoding="utf-8")
    assert '[string]$SkillRoot = ""' in text
    assert "$PSScriptRoot" in text
    assert '".venv\\Scripts\\python.exe"' in text
    assert "Resolve-PlaywrightPython" in text
    assert "skill_venv_only" in text
    assert "WRONG_PYTHON" in text
    assert "LAUNCH_PROBE_OK=true" in text


def test_complete_requires_active_session_and_process_identity() -> None:
    text = (ROOT / "LOGIN.ps1").read_text(encoding="utf-8")
    assert "No active $Platform login session exists" in text
    assert "Status/control session_id mismatch" in text
    assert "process_start_ticks" in text
    assert "Test-ProcessIdentity" in text
    assert "Refusing stale completion" in text


def test_installer_is_fail_fast_and_self_copy_safe() -> None:
    text = (ROOT / "INSTALL.ps1").read_text(encoding="utf-8")
    assert "Validate source package completeness" in text
    assert "Required source package file missing" in text
    assert "$SameRoot" in text
    assert "skipping self-copy" in text
    assert "cloud_phone_monitor\\login_helper_session_entry.py" in text


def test_controller_adapter_contract_is_session_bound() -> None:
    text = (ROOT / "cloud_phone_monitor" / "login_controller.py").read_text(encoding="utf-8")
    assert "cloud_phone_monitor.login_helper_session_entry" in text
    assert '"--session-id"' in text
    assert "helper final status does not belong to the active session" in text
    assert "timeout=450.0" in text

    adapter = (ROOT / "cloud_phone_monitor" / "login_helper_session_entry.py").read_text(encoding="utf-8")
    assert "_helper_capabilities" in adapter
    assert "--help" in adapter
    assert "LOGIN_PROTOCOL_VERSION" in adapter
    assert 'argv += ["--session-id", args.session_id]' in adapter
    assert 'value["session_id"] = session_id' in adapter


def test_controller_uses_pending_transaction_and_rollback(tmp_path: Path) -> None:
    final_a = tmp_path / "state.json"
    final_b = tmp_path / "runtime.json"
    pending_a = tmp_path / "state.json.pending.session-a"
    pending_b = tmp_path / "runtime.json.pending.session-a"
    final_a.write_text("old-state", encoding="utf-8")
    final_b.write_text("old-runtime", encoding="utf-8")
    pending_a.write_text("new-state", encoding="utf-8")
    pending_b.write_text("new-runtime", encoding="utf-8")

    result = commit_auth_artifacts(
        session_id="session-a",
        artifacts=[(pending_a, final_a), (pending_b, final_b)],
    )
    assert final_a.read_text(encoding="utf-8") == "new-state"
    assert final_b.read_text(encoding="utf-8") == "new-runtime"
    assert result["rollback_backups_cleaned"] is True
    assert not list(tmp_path.glob("*.previous.session-a"))



def test_auth_transaction_rolls_back_if_second_commit_fails(tmp_path: Path, monkeypatch) -> None:
    final_a = tmp_path / "state.json"
    final_b = tmp_path / "runtime.json"
    pending_a = tmp_path / "state.json.pending.session-b"
    pending_b = tmp_path / "runtime.json.pending.session-b"
    final_a.write_text("old-state", encoding="utf-8")
    final_b.write_text("old-runtime", encoding="utf-8")
    pending_a.write_text("new-state", encoding="utf-8")
    pending_b.write_text("new-runtime", encoding="utf-8")

    original_replace = Path.replace

    def failing_replace(self: Path, target):
        if self == pending_b and Path(target) == final_b:
            raise OSError("simulated second-artifact commit failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", failing_replace)
    try:
        commit_auth_artifacts(
            session_id="session-b",
            artifacts=[(pending_a, final_a), (pending_b, final_b)],
        )
    except OSError as exc:
        assert "simulated" in str(exc)
    else:
        raise AssertionError("simulated transaction failure should propagate")

    assert final_a.read_text(encoding="utf-8") == "old-state"
    assert final_b.read_text(encoding="utf-8") == "old-runtime"


def test_dependency_installer_creates_dedicated_venv_and_separates_dashboard() -> None:
    text = (ROOT / "install_dependencies_windows.ps1").read_text(encoding="utf-8")
    assert '".venv"' in text
    assert '"Scripts\\python.exe"' in text
    assert '"-m", "venv"' in text
    assert "InstallDashboardDependencies" in text
    assert "InstallDevDependencies" in text
    assert "launch(headless=True)" in text
    assert "return $items.ToArray()" in text
    assert "constraints-runtime.txt" in text
    assert "1.62.0" in text


def test_login_runtime_never_falls_back_from_skill_venv() -> None:
    text = (ROOT / "LOGIN.ps1").read_text(encoding="utf-8")
    assert "C:\\Python314\\python.exe" not in text
    assert "Get-Command python" not in text
    assert "Dedicated Skill runtime is missing" in text
    assert "runtime_authority = \"skill_venv_only\"" in text


def test_release_uses_explicit_policy_staging_and_deterministic_zip() -> None:
    prepare = (ROOT / "PREPARE_RELEASE.ps1").read_text(encoding="utf-8")
    builder = (ROOT / "tools" / "build_release_staging.py").read_text(encoding="utf-8")
    policy = (ROOT / "tools" / "public_release_policy.py").read_text(encoding="utf-8")
    assert "explicit-allowlist public staging tree" in prepare
    assert "validate_public_release.py" in prepare
    assert "build_release_zip.py" in prepare
    assert "is_public_source_path" in builder
    assert "write_sanitized_deployment_contract" in builder
    assert "PUBLIC_TOOL_FILES" in policy
    assert "PUBLIC_DEPLOYMENT_CONTRACT_KEYS" in policy
    assert 'PYTHONDONTWRITEBYTECODE = "1"' in prepare
    assert " -B " in prepare or "-B (Join-Path" in prepare
    assert "before mutating working tree" in prepare


def test_controller_and_runner_share_ugphone_profile_lock() -> None:
    controller = (ROOT / "cloud_phone_monitor" / "login_controller.py").read_text(encoding="utf-8")
    runner = (ROOT / "run.py").read_text(encoding="utf-8")
    assert "acquire_profile_lock" in controller
    assert 'owner_kind="login_controller"' in controller
    assert "locked_profile" in runner
    assert 'owner_kind="collector"' in runner
