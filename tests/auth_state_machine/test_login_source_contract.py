from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_login_uses_post_param_script_root_and_capability_probe() -> None:
    text = (ROOT / "LOGIN.ps1").read_text(encoding="utf-8")
    assert '[string]$SkillRoot = ""' in text
    assert "$PSScriptRoot" in text
    assert "Resolve-PlaywrightPython" in text
    assert "PLAYWRIGHT_IMPORT_ERROR" in text
    assert "CHROMIUM=" in text


def test_complete_requires_active_session_and_process_identity() -> None:
    text = (ROOT / "LOGIN.ps1").read_text(encoding="utf-8")
    assert "No active $Platform login session exists" in text
    assert "Status/control session_id mismatch" in text
    assert "process_start_ticks" in text
    assert "Test-ProcessIdentity" in text
    assert "Refusing stale completion" in text


def test_installer_is_fail_fast_for_required_files() -> None:
    text = (ROOT / "INSTALL.ps1").read_text(encoding="utf-8")
    assert "Validate source package completeness" in text
    assert "Required source package file missing" in text
    assert "Validate installed Skill completeness" in text
    assert "cloud_phone_monitor\\login_controller.py" in text


def test_controller_uses_pending_auth_commit() -> None:
    text = (ROOT / "cloud_phone_monitor" / "login_controller.py").read_text(encoding="utf-8")
    assert ".pending." in text
    assert "post_save_verification" in text
    assert "_replace_file(pending_state, final_state)" in text
    assert "verify_saved_auth_state" in text
