from cloud_phone_monitor.utils.dashboard_export import merge_equivalent_android_price_series


def _row(series_id: str, android: str, ug_product_model: str) -> dict:
    return {
        "platform": "Redfinger",
        "product_model": "VIP",
        "duration_bucket": 30,
        "duration_display": "30天",
        "purchase_mode": "standard",
        "points": [{"date": "2026-07-14", "price": 9.99}],
        "current_price": 9.99,
        "comparability_level": "weak_match",
        "series_id": series_id,
        "config": f"Android {android} / 8C / 4GB / 64GB",
        "ug_product_model": ug_product_model,
        "ug_config_id": f"ug_product_model::{ug_product_model}",
    }


def test_android_deduplication_does_not_cross_ugphone_pairing_groups() -> None:
    merged = merge_equivalent_android_price_series([
        _row("uvip-a10", "10", "UVIP"),
        _row("uvip-a12", "12", "UVIP"),
        _row("gvip-a10", "10", "GVIP"),
    ])

    assert len(merged) == 2
    by_pairing = {item["ug_product_model"]: item for item in merged}
    assert by_pairing["UVIP"]["merged_series_count"] == 2
    assert by_pairing["UVIP"]["ug_config_ids"] == ["ug_product_model::UVIP"]
    assert by_pairing["GVIP"]["merged_series_count"] == 1
    assert by_pairing["GVIP"]["ug_config_ids"] == ["ug_product_model::GVIP"]
