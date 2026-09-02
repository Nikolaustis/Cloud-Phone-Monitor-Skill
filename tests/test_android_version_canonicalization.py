import pandas as pd

from cloud_phone_monitor.utils.normalize import canonical_android_version
from cloud_phone_monitor.utils.baseline import build_baseline_with_current_overlay
from cloud_phone_monitor.utils.price_quality import add_standardized_price_fields
from cloud_phone_monitor.utils.dashboard_export import (
    canonicalize_android_fields,
    canonicalize_android_in_config_text,
)


def _row(android, price, duration="30 day"):
    return {
        "platform": "UgPhone",
        "product_category": "cloud_phone",
        "product_name": "MVIP",
        "product_model": "MVIP",
        "device_model": None,
        "android_version": android,
        "cpu": "8 cores",
        "ram": "8GB",
        "storage": "128GB",
        "billing_period": "day",
        "duration": duration,
        "price": price,
        "original_price": price,
        "discount_price": None,
        "supported_server_regions": "Hong Kong",
        "promotion_text": None,
        "raw_text": "",
        "stock_status": "available",
        "notes": "",
    }


def test_canonical_android_version_preserves_meaningful_decimal():
    assert canonical_android_version("10") == "10"
    assert canonical_android_version("10.0") == "10"
    assert canonical_android_version(10.0) == "10"
    assert canonical_android_version("Android 13.00") == "13"
    assert canonical_android_version("8.1") == "8.1"
    assert canonical_android_version("Android 8.10") == "8.1"


def test_baseline_overlay_matches_android_10_and_10_point_0_as_one_identity():
    baseline = pd.DataFrame([_row("10", "17.99")])
    current = pd.DataFrame([_row("10.0", "15.99")])
    merged = build_baseline_with_current_overlay(baseline, current)
    assert len(merged) == 1
    assert merged.iloc[0]["android_version"] == "10"
    assert float(merged.iloc[0]["price"]) == 15.99
    assert merged.iloc[0]["current_observation_status"] == "observed_current_run"


def test_quality_standardization_uses_canonical_android_version():
    frame = add_standardized_price_fields(pd.DataFrame([_row("13.0", "17.99")]))
    assert frame.iloc[0]["android_version"] == "13"
    assert frame.iloc[0]["_android_num"] == 13.0


def test_dashboard_migrates_old_config_labels_and_columns():
    frame = pd.DataFrame(
        [
            {
                "ug_android_version": "10.0",
                "competitor_android_version": "13.0",
                "ug_config": "MVIP / Android 10.0 / 8 cores / 8GB / 128GB",
                "competitor_config": "XVIP / Android 13.0 / 8 cores / 8GB / 128GB",
            }
        ]
    )
    migrated = canonicalize_android_fields(frame)
    assert migrated.iloc[0]["ug_android_version"] == "10"
    assert migrated.iloc[0]["competitor_android_version"] == "13"
    assert "Android 10 /" in migrated.iloc[0]["ug_config"]
    assert "Android 13 /" in migrated.iloc[0]["competitor_config"]
    assert canonicalize_android_in_config_text("A10.0 / 8 cores") == "A10 / 8 cores"
