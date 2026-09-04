from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

from cloud_phone_monitor.data_contracts import SCHEMA_VERSION, SKILL_RELEASE
from tools.build_release_staging import build as build_release_stage

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "deployment" / "windows" / "validate_cloud_phone_dashboard.py"


def _load_validator_module():
    spec = importlib.util.spec_from_file_location("deployment_validator", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_public_deployment_contract_and_files(tmp_path: Path) -> None:
    assert SKILL_RELEASE == "current"
    assert SCHEMA_VERSION == 9

    stage = tmp_path / "public-stage"
    build_release_stage(ROOT, stage)
    contract = json.loads((stage / "deployment_contract.json").read_text(encoding="utf-8"))
    assert contract == {
        "schema_version": 9,
        "history_storage": "gzip-json-v1",
        "publisher_capability": "gzip-history-pages",
    }

    assert (stage / ".gitignore").is_file()
    assert (stage / ".gitattributes").is_file()
    assert (stage / "publisher.local.example.json").is_file()
    assert not (stage / "publisher.local.json").exists()
    assert not (stage / "PUBLISH_SOURCE_TO_GITHUB.ps1").exists()
    assert not (stage / "install_windows.ps1").exists()
    assert (stage / "install_dependencies_windows.ps1").is_file()
    assert (stage / "LOGIN.ps1").is_file()
    assert (stage / "cloud_phone_monitor" / "login_controller.py").is_file()
    assert (stage / "cloud_phone_monitor" / "auth_session_contract.py").is_file()
    assert (stage / "cloud_phone_monitor" / "login_helper_session_entry.py").is_file()
    assert (stage / "cloud_phone_monitor" / "profile_lock.py").is_file()
    assert (stage / "PREPARE_RELEASE.ps1").is_file()
    assert (stage / "tools" / "generate_manifest.py").is_file()
    assert (stage / "tools" / "validate_manifest.py").is_file()
    assert (stage / "tools" / "public_release_policy.py").is_file()
    assert (stage / ".github" / "workflows" / "ci.yml").is_file()


def test_public_publisher_has_no_bound_remote(tmp_path: Path) -> None:
    stage = tmp_path / "public-stage"
    build_release_stage(ROOT, stage)
    for rel in (
        "deployment_contract.json",
        "deployment/windows/publish_dashboard.ps1",
        "deployment/windows/update_cloud_phone_dashboard.ps1",
        "INSTALL.ps1",
        "publisher.local.example.json",
    ):
        text = (stage / rel).read_text(encoding="utf-8")
        assert "github.com/YOUR_ACCOUNT/YOUR_DASHBOARD_REPO.git" in text or "https://github.com/" not in text

    publisher = (stage / "deployment/windows/publish_dashboard.ps1").read_text(encoding="utf-8")
    assert "publisher.local.json" in publisher
    assert "GitHub Pages publishing is not configured" in publisher

def test_installer_and_login_controller_contract() -> None:
    installer = (ROOT / "INSTALL.ps1").read_text(encoding="utf-8")
    assert "PUBLISH_SOURCE_TO_GITHUB.ps1" not in installer
    assert "PATCH_NOTES" not in installer
    assert "release_contract.json" not in installer
    assert "test_v*.py" not in installer
    assert '"LOGIN.ps1"' in installer
    assert "Validate source package completeness" in installer
    assert "Validate installed Skill completeness" in installer
    assert "cloud_phone_monitor\\login_controller.py" in installer

    login_script = (ROOT / "LOGIN.ps1").read_text(encoding="utf-8")
    assert "cloud_phone_monitor.login_controller" in login_script
    assert "Resolve-PlaywrightPython" in login_script
    assert ".venv\\Scripts\\python.exe" in login_script
    assert "skill_venv_only" in login_script
    assert "Google Chrome is not required" in login_script
    assert "--persistent-profile" in login_script
    assert "ugphone_runtime_context.json" in login_script
    assert "[switch]$Start" in login_script
    assert "[switch]$Complete" in login_script
    assert "[switch]$Status" in login_script
    assert "[switch]$Cancel" in login_script
    assert "LOGIN_AGENT_STATE=WAITING_FOR_USER" in login_script
    assert "LOGIN_AGENT_STATE=SAVED_AND_VERIFIED" in login_script
    assert "login_agent_session.json" in login_script
    assert "process_start_ticks" in login_script
    assert "Status/control session_id mismatch" in login_script

    controller = (ROOT / "cloud_phone_monitor" / "login_controller.py").read_text(encoding="utf-8")
    assert "cloud_phone_monitor.login_helper_session_entry" in controller
    assert '"--session-id"' in controller
    assert "verify_saved_auth_state" in controller
    assert ".pending." in controller
    assert "signal_matches_session" in controller
    assert "commit_auth_artifacts" in controller
    assert "timeout=450.0" in controller
    adapter = (ROOT / "cloud_phone_monitor" / "login_helper_session_entry.py").read_text(encoding="utf-8")
    assert "_helper_capabilities" in adapter
    assert "LOGIN_PROTOCOL_VERSION" in adapter
    assert 'value["session_id"] = session_id' in adapter
    auth_contract = (ROOT / "cloud_phone_monitor" / "auth_session_contract.py").read_text(encoding="utf-8")
    assert "no_server_acknowledged_auth_evidence" in auth_contract
    assert "server_authenticated" in auth_contract
    assert "verify_vsphone_auth" in auth_contract
    assert "verify_redfinger_auth" in auth_contract
    assert "verify_ldcloud_auth" in auth_contract

    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "Authentication execution routing (hard rule)" in skill_text
    assert "LOGIN.ps1 <Platform> -Start" in skill_text
    assert "LOGIN.ps1 <Platform> -Complete" in skill_text
    assert "NEVER" in skill_text and "Cloud Browser" in skill_text

    deployment_installer = (ROOT / "deployment/windows/install_deployment.ps1").read_text(encoding="utf-8")
    assert "obsolete release-branded" not in deployment_installer
    assert "verify_v*" not in deployment_installer
    assert "Canonical deployment" not in deployment_installer


def test_validator_accepts_gzip_and_partial_coverage(tmp_path: Path) -> None:
    module = _load_validator_module()
    dist = tmp_path / "dist"
    data = dist / "dashboard_data"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    data.mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (assets / "index-test.js").write_text("console.log('ok')", encoding="utf-8")

    for name in (
        "frontend_price_overview.json",
        "pairing_matrix.json",
        "duration_price_comparison.json",
        "price_change_tracking.json",
        "product_text_changes.json",
        "metric_definitions.json",
        "schedule_status.json",
        "meta.json",
        "current_price_snapshot.json",
    ):
        _write_json(data / name, {})

    _write_json(
        data / "platform_status.json",
        [
            {"platform": "UgPhone", "raw_records": 10, "status": "warning", "coverage_status": "partial"},
            {"platform": "VSPhone", "raw_records": 10, "status": "ok"},
            {"platform": "Redfinger", "raw_records": 10, "status": "ok"},
            {"platform": "LDCloud", "raw_records": 10, "status": "ok"},
        ],
    )
    _write_json(data / "collection_contract.json", {"status": "warning", "schema_version": 9})
    _write_json(data / "run_manifest.json", {"skill_release": "current", "schema_version": 9})
    _write_json(data / "history_storage.json", {"codec": "gzip-json-v1", "price_trends_file": "price_trends.json.gz"})

    trend = {"history_end_date": "2026-09-01", "trend_detail_files": [], "series": []}
    (data / "price_trends.json.gz").write_bytes(
        gzip.compress(json.dumps(trend).encode("utf-8"), compresslevel=9, mtime=0)
    )

    result = module.validate(dist)
    assert result["history_asset"] == "price_trends.json.gz"
    assert result["history_codec"] == "gzip-json-v1"
    assert result["warnings"] == ["collection_contract status=warning"]


def test_public_release_policy_and_profile_lock_are_wired() -> None:
    policy = (ROOT / "tools/public_release_policy.py").read_text(encoding="utf-8")
    builder = (ROOT / "tools/build_release_staging.py").read_text(encoding="utf-8")
    controller = (ROOT / "cloud_phone_monitor/login_controller.py").read_text(encoding="utf-8")
    runner = (ROOT / "run.py").read_text(encoding="utf-8")
    preflight = (ROOT / "deployment/windows/check_skill_login_state.py").read_text(encoding="utf-8")

    assert "PUBLIC_TOOL_FILES" in policy
    assert "PUBLIC_DEPLOYMENT_CONTRACT_KEYS" in policy
    assert "write_sanitized_deployment_contract" in builder
    assert "acquire_profile_lock" in controller
    assert 'owner_kind="login_controller"' in controller
    assert "locked_profile" in runner
    assert 'owner_kind="collector"' in runner
    assert "locked_profile" in preflight
    assert 'owner_kind="login_preflight"' in preflight
