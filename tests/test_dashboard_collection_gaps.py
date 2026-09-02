from cloud_phone_monitor.utils.dashboard_export import (
    _snapshot_has_product_duration,
    apply_collection_gap_markers,
    fill_points_by_natural_days,
    update_series_stats_from_points,
)


def _coverage():
    return {
        "platform_dates": {"UgPhone": {"2026-08-20", "2026-08-21"}},
        "product_dates": {
            ("UgPhone", "gvip", "subscription"): {"2026-08-20"},
        },
        "bucket_dates": {
            ("UgPhone", "gvip", "30", "subscription"): {"2026-08-20"},
        },
    }


def test_missing_product_on_collection_day_keeps_last_observation() -> None:
    series = {
        "platform": "UgPhone",
        "product_model": "GVIP",
        "duration_bucket": "30",
        "purchase_mode": "subscription",
    }
    dates = ["2026-08-20", "2026-08-21", "2026-08-22"]
    marked = apply_collection_gap_markers(
        series,
        [{"date": "2026-08-20", "price": 8.99, "price_source": "historical"}],
        dates,
        _coverage(),
    )
    filled = fill_points_by_natural_days(marked, dates)
    by_date = {row["date"]: row for row in filled}

    assert by_date["2026-08-20"]["price"] == 8.99
    assert by_date["2026-08-21"]["price"] == 8.99
    assert by_date["2026-08-21"]["price_source"] == "carry_forward"
    assert by_date["2026-08-22"]["price"] == 8.99

    series["points"] = filled
    update_series_stats_from_points(series)
    assert series["current_price"] == 8.99
    assert series["price_source"] == "carry_forward"


def test_missing_current_placeholder_is_replaced_by_carry_forward() -> None:
    dates = ["2026-08-20", "2026-08-21"]
    points = [
        {"date": "2026-08-20", "price": 8.99, "price_source": "historical"},
        {"date": "2026-08-21", "price": None, "price_source": "missing_current_products"},
    ]
    filled = fill_points_by_natural_days(points, dates)
    assert filled[-1]["price"] == 8.99
    assert filled[-1]["price_source"] == "carry_forward"
    assert filled[-1]["missing_observation_source"] == "missing_current_products"
    assert filled[-1]["source_collection_date"] == "2026-08-20"


def test_missing_duration_does_not_infer_discontinuation() -> None:
    coverage = _coverage()
    coverage["product_dates"][("UgPhone", "gvip", "subscription")] = {"2026-08-20", "2026-08-21"}
    # The bucket is absent on 8/21, but the current logic must not infer that a single missing
    # duration means the product has been discontinued.
    series = {
        "platform": "UgPhone",
        "product_model": "GVIP",
        "duration_bucket": "30",
        "purchase_mode": "subscription",
    }
    dates = ["2026-08-20", "2026-08-21"]
    marked = apply_collection_gap_markers(
        series,
        [{"date": "2026-08-20", "price": 8.99, "price_source": "historical"}],
        dates,
        coverage,
    )
    filled = fill_points_by_natural_days(marked, dates)
    assert filled[-1]["price"] == 8.99
    assert filled[-1]["price_source"] == "carry_forward"


def test_explicit_block_marker_can_still_break_chain() -> None:
    dates = ["2026-08-20", "2026-08-21", "2026-08-22"]
    points = [
        {"date": "2026-08-20", "price": 5.99, "price_source": "historical"},
        {
            "date": "2026-08-21",
            "price": None,
            "price_source": "explicit_discontinued",
            "carry_forward_blocked": True,
        },
    ]
    filled = fill_points_by_natural_days(points, dates)
    assert filled[1]["price"] is None
    assert filled[2]["price"] is None


def test_current_snapshot_requires_actual_product_duration() -> None:
    snapshot = {
        "rows": [
            {
                "platform": "UgPhone",
                "product_model": "GVIP",
                "duration_days": 30,
                "purchase_mode": "subscription",
                "price": 8.99,
            }
        ]
    }
    assert _snapshot_has_product_duration(
        snapshot,
        platform="UgPhone",
        product_model="GVIP",
        duration_days=30,
        purchase_mode="subscription",
    )
    assert not _snapshot_has_product_duration(
        snapshot,
        platform="UgPhone",
        product_model="GVIP",
        duration_days=15,
        purchase_mode="subscription",
    )
