import json
from pathlib import Path

import pandas as pd

from cloud_phone_monitor.utils.collection_contract import build_collection_contract


def _current_rows() -> pd.DataFrame:
    rows = []
    for platform in ["UgPhone", "VSPhone", "Redfinger", "LDCloud"]:
        rows.append({"platform": platform, "product_model": "VIP", "price": "1.00"})
    return pd.DataFrame(rows)


def test_ugphone_partial_matrix_is_warning_not_silent_ok(tmp_path: Path) -> None:
    artifacts = tmp_path / "page_artifacts"
    artifacts.mkdir()
    (artifacts / "ugphone_collection_summary.json").write_text(json.dumps({
        "platform": "UGPhone",
        "collection_status": "warning",
        "dom_matrix_plan_targets": 5,
        "dom_matrix_plan_successes": 4,
        "dom_matrix_variant_targets": 10,
        "dom_matrix_variant_successes": 10,
        "dom_matrix_region_targets": 40,
        "dom_matrix_region_resolved": 40,
        "dom_matrix_skipped": [{"plan": "GVIP", "reason": "plan_activation_failed"}],
    }), encoding="utf-8")
    contract = build_collection_contract(tmp_path, _current_rows(), pd.DataFrame())
    ug = next(row for row in contract["platforms"] if row["platform"] == "UgPhone")
    assert ug["status"] == "warning"
    assert ug["coverage_ratio"] == 0.8
    assert ug["missing_cells"][0]["plan"] == "GVIP"


def test_baseline_rows_are_reference_only(tmp_path: Path) -> None:
    current = _current_rows()
    baseline = pd.DataFrame([{"platform": "UgPhone", "price": "1"}] * 100)
    contract = build_collection_contract(tmp_path, current, baseline)
    ug = next(row for row in contract["platforms"] if row["platform"] == "UgPhone")
    assert ug["current_rows"] == 1
    assert ug["baseline_reference_rows"] == 100
    assert ug["coverage_ratio"] == 1.0
    assert "reference-only" in contract["contract_rule"]
