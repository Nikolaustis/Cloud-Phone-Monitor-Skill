from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

from cloud_phone_monitor.data_contracts import SCHEMA_VERSION, SKILL_RELEASE

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


def test_deployment_contract_and_deployment_files_exist() -> None:
    assert SKILL_RELEASE == "current"
    assert SCHEMA_VERSION == 9
    contract = json.loads((ROOT / "deployment_contract.json").read_text(encoding="utf-8"))
    assert contract["publisher_capability"] == "gzip-history-pages"
    assert contract["history_storage"] == "gzip-json-v1"
    for rel in (
        "deployment/windows/update_cloud_phone_dashboard.ps1",
        "deployment/windows/publish_dashboard.ps1",
        "deployment/windows/resume_dashboard_publish.ps1",
        "deployment/windows/validate_cloud_phone_dashboard.py",
        "deployment/windows/check_skill_login_state.py",
        "deployment/windows/install_deployment.ps1",
        "deployment/windows/verify_deployment.ps1",
    ):
        assert (ROOT / rel).is_file(), rel


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
    _write_json(
        data / "history_storage.json",
        {"codec": "gzip-json-v1", "price_trends_file": "price_trends.json.gz"},
    )
    trend = {"history_end_date": "2026-09-01", "trend_detail_files": [], "series": []}
    (data / "price_trends.json.gz").write_bytes(
        gzip.compress(json.dumps(trend).encode("utf-8"), compresslevel=9, mtime=0)
    )

    result = module.validate(dist)
    assert result["history_asset"] == "price_trends.json.gz"
    assert result["history_codec"] == "gzip-json-v1"
    assert result["warnings"] == ["collection_contract status=warning"]
