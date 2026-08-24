import pandas as pd

from cloud_phone_monitor.utils.baseline import build_baseline_with_current_overlay


def _row(model: str, price: float) -> dict:
    return {
        "platform": "UgPhone",
        "product_model": model,
        "android_version": "12",
        "cpu": "4C",
        "ram": "4GB",
        "storage": "64GB",
        "duration": "30 day",
        "price": price,
        "currency": "USD",
        "purchase_mode": "subscription",
    }


def test_missing_baseline_row_is_explicitly_diagnostic_only() -> None:
    baseline = pd.DataFrame([_row("GVIP", 8.99)])
    current = pd.DataFrame([_row("UVIP", 10.99)])
    merged = build_baseline_with_current_overlay(baseline, current)
    gvip = merged[merged["product_model"].astype(str).str.upper().eq("GVIP")].iloc[0]
    assert gvip["current_observation_status"] == "missing_current_run"
    assert "current_missing_used_baseline" in str(gvip["notes"])
