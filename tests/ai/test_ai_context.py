from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from cloud_phone_monitor.ai_context import AI_CONTEXT_SCHEMA_VERSION, build_ai_context


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_ai_context_normalizes_market_and_preserves_origin(tmp_path: Path) -> None:
    data = tmp_path / "dashboard_data"
    _write(data / "meta.json", {"last_run_date":"2026-09-03","current_price_data_revision":"abc123","safe_data_only":True})
    _write(data / "frontend_price_overview.json", {
        "rows_compared":1,"market_position_counts":{"high":1},"attention_items":[{
            "ug_config_id":"k1","ug_config":"KVIP demo","ug_product_model":"KVIP","duration_days":30,
            "ugphone_price":15,"analysis_status":"carry_forward_last_observed","data_origin":"carry_forward",
            "competitors":{
                "VSPhone":{"platform":"VSPhone","current_price":10,"included_in_core_median":True,"comparability_level":"strong_match"},
                "Redfinger":{"platform":"Redfinger","current_price":14,"included_in_core_median":True,"comparability_level":"adjusted_match"}
            }
        }]
    })
    _write(data / "price_change_tracking.json", [])
    _write(data / "pairing_matrix.json", [])
    _write(data / "metric_definitions.json", [])
    result = build_ai_context(data)
    manifest = json.loads((result.output_dir / "manifest.json").read_text(encoding="utf-8"))
    configs = json.loads((result.output_dir / "config_index.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == AI_CONTEXT_SCHEMA_VERSION
    assert manifest["contract_version"] == 2
    assert manifest["data_revision"] == "abc123"
    assert configs[0]["competitor_median_price"] == 12
    assert configs[0]["relative_index"] == 125
    assert configs[0]["market_position"] == "high"
    assert configs[0]["data_origin"] == "carry_forward"
    assert configs[0]["fact_id"].startswith("config_")


def test_fact_ids_are_stable_for_identical_input(tmp_path: Path) -> None:
    data = tmp_path / "dashboard_data"
    _write(data / "meta.json", {"safe_data_only": True})
    payload = {"attention_items":[{"ug_config_id":"same","ug_config":"KVIP","duration_days":30,"ugphone_price":10,"competitor_median_price":10}]}
    _write(data / "frontend_price_overview.json", payload)
    _write(data / "price_change_tracking.json", [])
    _write(data / "pairing_matrix.json", [])
    _write(data / "metric_definitions.json", [])
    first = build_ai_context(data, tmp_path / "one")
    second = build_ai_context(data, tmp_path / "two")
    a = json.loads((first.output_dir / "config_index.json").read_text(encoding="utf-8"))[0]["fact_id"]
    b = json.loads((second.output_dir / "config_index.json").read_text(encoding="utf-8"))[0]["fact_id"]
    assert a == b


def test_duration_comparison_is_canonical_selector_inventory(tmp_path: Path) -> None:
    data = tmp_path / "dashboard_data"
    _write(data / "meta.json", {"last_run_date": "2026-09-04", "current_price_data_revision": "durations", "safe_data_only": True})
    # Attention is deliberately sparse: only 180d.  The duration comparison file
    # carries the complete set that Explain/What-if must expose.
    _write(data / "frontend_price_overview.json", {
        "rows_compared": 1,
        "market_position_counts": {"high": 1},
        "attention_items": [{
            "ug_config_id": "kvip-a10",
            "ug_config": "KVIP / Android 10 / 6 cores / 5.3GB / 64GB",
            "ug_product_model": "KVIP",
            "ug_android_version": "10",
            "ug_cpu": "6 cores",
            "ug_ram": "5.3GB",
            "ug_storage": "64GB",
            "duration_days": 180,
            "ugphone_price": 52.99,
            "competitor_median_price": 40,
        }],
    })
    rows = []
    for days, price in ((1, 1.69), (30, 16.99), (90, 32.99), (180, 52.99), (365, 89.99)):
        rows.append({
            "ug_config_id": "kvip-a10",
            "ug_config": "KVIP / Android 10 / 6 cores / 5.3GB / 64GB",
            "ug_product_model": "KVIP",
            "ug_android_version": "10",
            "ug_cpu": "6 cores",
            "ug_ram": "5.3GB",
            "ug_storage": "64GB",
            "duration_days": days,
            "ugphone_price": price,
            "competitors": {
                "VSPhone": {
                    "platform": "VSPhone",
                    "current_price": max(price * 0.8, 0.5),
                    "included_in_core_median": True,
                    "comparability_level": "strong_match",
                }
            },
        })
    _write(data / "duration_price_comparison.json", {
        "core_buckets": [1, 3, 7, 15, 30, 60, 90, 180, 365],
        "buckets": {str(row["duration_days"]): [row] for row in rows},
        "other_rows": [],
    })
    _write(data / "price_change_tracking.json", [])
    _write(data / "pairing_matrix.json", [])
    _write(data / "metric_definitions.json", [])

    result = build_ai_context(data)
    configs = json.loads((result.output_dir / "config_index.json").read_text(encoding="utf-8"))
    manifest = json.loads((result.output_dir / "manifest.json").read_text(encoding="utf-8"))
    durations = sorted({int(row["duration_days"]) for row in configs if row.get("config_id") == "kvip-a10" and row.get("duration_days")})
    assert durations == [1, 30, 90, 180, 365]
    assert manifest["core_duration_buckets"] == [1, 3, 7, 15, 30, 60, 90, 180, 365]
    assert manifest["selector_inventory_count"] == 5
    verifier = Path(__file__).resolve().parents[2] / "tools" / "verify_ai_selector_inventory.py"
    completed = subprocess.run([sys.executable, str(verifier), "--data-dir", str(data)], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_config_index_excludes_rows_without_purchase_period(tmp_path: Path) -> None:
    data = tmp_path / "dashboard_data"

    _write(
        data / "meta.json",
        {
            "last_run_date": "2026-09-04",
            "current_price_data_revision": "no-blank-duration",
            "safe_data_only": True,
        },
    )

    _write(
        data / "frontend_price_overview.json",
        {
            "rows_compared": 1,
            "market_position_counts": {},
            "attention_items": [],
        },
    )

    _write(
        data / "duration_price_comparison.json",
        {
            "core_buckets": [30],
            "buckets": {
                "30": [
                    {
                        "ug_config_id": "kvip-a10",
                        "ug_config": "KVIP / Android 10 / 6 cores / 5.3GB / 64GB",
                        "ug_product_model": "KVIP",
                        "ug_android_version": "10",
                        "ug_cpu": "6 cores",
                        "ug_ram": "5.3GB",
                        "ug_storage": "64GB",
                        "duration_days": 30,
                        "ugphone_price": 16.99,
                    }
                ]
            },
            "other_rows": [],
        },
    )

    # This analysis row deliberately has no purchase period.
    # It may remain useful to other analysis layers, but it must never become
    # a selectable Explain / What-if configuration.
    _write(
        data / "pairing_matrix.json",
        [
            {
                "ug_config_id": "orphan-without-duration",
                "ug_config": "KVIP analysis-only row",
                "ug_product_model": "KVIP",
                "ugphone_price": 10,
                "competitor_median_price": 9,
            }
        ],
    )

    _write(data / "price_change_tracking.json", [])
    _write(data / "metric_definitions.json", [])

    result = build_ai_context(data)

    configs = json.loads(
        (result.output_dir / "config_index.json").read_text(encoding="utf-8")
    )

    assert len(configs) == 1
    assert configs[0]["config_id"] == "kvip-a10"
    assert configs[0]["duration_days"] == 30
    assert all(
        row.get("duration_days") not in (None, "", 0)
        for row in configs
    )
