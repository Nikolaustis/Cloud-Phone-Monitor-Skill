from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from cloud_phone_monitor.scrapers.ugphone import UGPhoneScraper
from cloud_phone_monitor.utils.dashboard_export import (
    build_duration_price_comparison,
    build_frontend_price_overview,
)
from cloud_phone_monitor.utils.price_quality import subscription_default_quality_rows


def _detail_row(config: str, product: str, days: int, ug_price: float, *, competitor_price: float | None = 10.0, level: str = "strong_match"):
    return {
        "ug_product_model": product,
        "ug_config": config,
        "duration_days": days,
        "ug_effective_price_30d": ug_price,
        "competitor_platform": "VSPhone",
        "competitor_product_model": "Basic",
        "competitor_config": "Basic / Android 10 / 6 cores / 4GB / 32GB",
        "competitor_duration_days": days,
        "competitor_effective_price_30d": competitor_price,
        "comparability_level": level,
        "config_similarity_score": 90,
        "promotion_text": "regular",
        "pairing_source": "test",
    }


def test_gvip_missing_current_run_carries_previous_quality_price() -> None:
    config = "GVIP / Android 10 / 4 cores / 4GB / 64GB"
    details = pd.DataFrame([_detail_row(config, "GVIP", 30, 8.99, competitor_price=9.99)])
    result = build_duration_price_comparison(details, current_snapshot={"rows": []})
    row = result["buckets"]["30"][0]
    assert row["ugphone_current_observed"] is False
    assert row["ugphone_price"] == 8.99
    assert row["ugphone_price_source"] == "carry_forward_last_observed"
    assert row["analysis_status"] == "carry_forward_last_observed"
    assert row["market_position_status"] == "comparable"
    assert row["market_position_label"] != "unknown"


def test_current_non_subscription_only_does_not_resurrect_old_subscription_price() -> None:
    config = "UVIP / Android 10 / 3 cores / 3GB / 30GB"
    details = pd.DataFrame([_detail_row(config, "UVIP", 1, 1.99, competitor_price=1.5)])
    snapshot = {
        "rows": [
            {
                "platform": "UgPhone",
                "product_model": "UVIP",
                "duration_days": 1,
                "purchase_mode": "non_subscription",
                "price": 1.19,
            }
        ]
    }
    result = build_duration_price_comparison(details, current_snapshot=snapshot)
    row = result["buckets"]["1"][0]
    assert row["analysis_status"] == "subscription_mode_unavailable"
    assert row["exclude_from_market_position"] is True
    assert row["ugphone_price"] is None


def test_overview_unknown_counts_only_real_competitor_insufficiency() -> None:
    duration = {
        "buckets": {
            "30": [
                {
                    "ug_config_id": "a",
                    "duration_bucket": 30,
                    "market_position_label": "competitive",
                    "market_position_status": "comparable",
                    "analysis_status": "carry_forward_last_observed",
                    "exclude_from_market_position": False,
                    "ugphone_relative_index": 100,
                },
                {
                    "ug_config_id": "b",
                    "duration_bucket": 30,
                    "market_position_label": "unknown",
                    "market_position_status": "competitor_insufficient",
                    "analysis_status": "current_observed",
                    "exclude_from_market_position": False,
                    "ugphone_relative_index": None,
                },
                {
                    "ug_config_id": "c",
                    "duration_bucket": 30,
                    "market_position_label": "unknown",
                    "market_position_status": "excluded",
                    "analysis_status": "subscription_mode_unavailable",
                    "exclude_from_market_position": True,
                    "ugphone_relative_index": None,
                },
            ]
        }
    }
    overview = build_frontend_price_overview(duration, {"generated_at_utc": "2026-08-26T00:00:00Z"})
    assert overview["rows_total_before_exclusions"] == 3
    assert overview["rows_compared"] == 2
    assert overview["excluded_from_market_position_count"] == 1
    assert overview["market_position_counts"]["unknown"] == 1
    assert overview["market_position_status_counts"]["competitor_insufficient"] == 1


def test_quality_layer_drops_only_ugphone_15_day_rows() -> None:
    frame = pd.DataFrame(
        [
            {"platform": "UgPhone", "duration": "15 day", "purchase_mode": "subscription", "price": 5.99},
            {"platform": "UgPhone", "duration": "30 day", "purchase_mode": "subscription", "price": 8.99},
            {"platform": "LDCloud", "duration": "15 day", "purchase_mode": "standard", "price": 9.99},
        ]
    )
    filtered = subscription_default_quality_rows(frame)
    assert len(filtered) == 2
    assert ((filtered["platform"] == "UgPhone") & (filtered["duration"] == "15 day")).sum() == 0
    assert ((filtered["platform"] == "UgPhone") & (filtered["duration"] == "30 day")).sum() == 1
    assert ((filtered["platform"] == "LDCloud") & (filtered["duration"] == "15 day")).sum() == 1


def test_gvip_api_versions_are_available_before_plan_cards() -> None:
    scraper = object.__new__(UGPhoneScraper)
    scraper._config_index = {
        ("gvip", "android10.0"): {"plan": "GVIP", "version_label": "android10.0", "android_version": "10"},
        ("gvip", "android12.0"): {"plan": "GVIP", "version_label": "android12.0", "android_version": "12"},
        ("gvip", "android13.0"): {"plan": "GVIP", "version_label": "android13.0", "android_version": "13"},
    }
    versions = scraper._api_version_entries_for_plan("GVIP")
    assert [v["name"] for v in versions] == ["android10.0", "android12.0", "android13.0"]


class _FakePage:
    def wait_for_timeout(self, _ms: int) -> None:
        return None


def test_plan_activation_can_stabilize_without_price_cards() -> None:
    scraper = object.__new__(UGPhoneScraper)
    states = [
        {
            "active_plan": "GVIP",
            "active_version": None,
            "active_region": "Indonesia",
            "cards": [],
            "versions": [
                {"index": 0, "name": "android10.0", "active": True},
                {"index": 1, "name": "android12.0", "active": False},
                {"index": 2, "name": "android13.0", "active": False},
            ],
            "regions": [],
            "purchase_mode": "subscription",
        }
    ]
    scraper._current_purchase_state = lambda page: states[0]
    result = scraper._wait_for_rendered_state(
        _FakePage(), expected_plan="GVIP", timeout_ms=1000, allow_empty_cards=True, stable_frames_required=2
    )
    assert result["active_plan"] == "GVIP"
    assert result["cards"] == []


def test_version_and_region_discovery_do_not_require_plan_level_cards() -> None:
    scraper = object.__new__(UGPhoneScraper)
    scraper._config_index = {
        ("gvip", "android10.0"): {"plan": "GVIP", "version_label": "android10.0", "android_version": "10"},
        ("gvip", "android12.0"): {"plan": "GVIP", "version_label": "android12.0", "android_version": "12"},
        ("gvip", "android13.0"): {"plan": "GVIP", "version_label": "android13.0", "android_version": "13"},
    }
    state = {
        "active_plan": "GVIP",
        "active_version": "android10.0",
        "active_region": "Indonesia",
        "cards": [],
        "versions": [
            {"index": 0, "name": "android10.0", "active": True},
            {"index": 1, "name": "android12.0", "active": False},
            {"index": 2, "name": "android13.0", "active": False},
        ],
        "regions": [
            {"index": 0, "name": "America", "active": False},
            {"index": 1, "name": "Germany", "active": False},
        ],
    }
    scraper._current_purchase_state = lambda page: state
    scraper._version_entries = lambda page: state["versions"]
    api_versions = scraper._api_version_entries_for_plan("GVIP")
    versions, resolved_state = scraper._resolve_plan_versions(
        _FakePage(), target_plan="GVIP", initial_state=state, api_versions=api_versions, timeout_ms=1000
    )
    assert [row["name"] for row in versions] == ["android10.0", "android12.0", "android13.0"]
    region_state = scraper._wait_for_regions_for_selection(
        _FakePage(), expected_plan="GVIP", expected_version="android10.0", timeout_ms=1000
    )
    assert [row["name"] for row in region_state["regions"]] == ["America", "Germany"]
    assert resolved_state["cards"] == []


def test_trend_carry_forward_prefers_last_raw_history_over_stale_baseline(tmp_path) -> None:
    from cloud_phone_monitor.utils.dashboard_export import build_price_trends

    output_root = tmp_path / "output"
    output_root.mkdir()
    prior = output_root / "cloud_phone_monitor_20260821_010000"
    prior.mkdir()
    pd.DataFrame(
        [
            {
                "platform": "UgPhone",
                "currency": "$",
                "product_model": "GVIP",
                "device_model": "GVIP",
                "android_version": "10",
                "cpu": "4 cores",
                "ram": "4GB",
                "storage": "64GB",
                "duration": "30 day",
                "billing_period": "day",
                "purchase_mode": "subscription",
                "price": 8.99,
                "original_price": 14.99,
                "promotion_text": "Auto-Renew Deal",
                "supported_server_regions": "Hong Kong; Singapore",
                "server_region": "Hong Kong; Singapore",
                "stock_status": "available",
                "notes": "",
            }
        ]
    ).to_csv(prior / "products.csv", index=False)
    latest = output_root / "latest"
    latest.mkdir()

    comparison = {
        "buckets": {
            "30": [
                {
                    "ug_config_id": "gvip",
                    "ug_config": "GVIP / Android 10 / 4 cores / 4GB / 64GB",
                    "ug_product_model": "GVIP",
                    "duration_bucket": 30,
                    "duration_display": "30天",
                    # Simulate a stale rolling-baseline value. The trend builder
                    # must ignore it in favor of the raw 8/21 products history.
                    "ugphone_price": 7.99,
                    "ugphone_price_source": "carry_forward_last_observed",
                    "competitors": {},
                },
                {
                    "ug_config_id": "uvip",
                    "ug_config": "UVIP / Android 10 / 3 cores / 3GB / 30GB",
                    "ug_product_model": "UVIP",
                    "duration_bucket": 30,
                    "duration_display": "30天",
                    "ugphone_price": 6.99,
                    "ugphone_price_source": "current_products",
                    "competitors": {},
                },
            ]
        },
        "other_rows": [],
    }
    payload = build_price_trends(
        [],
        comparison,
        {
            "source_output_dir": str(latest),
            "last_run_date": "2026-08-26",
            "generated_at_utc": "2026-08-26T00:00:00Z",
        },
    )
    gvip = next(
        row for row in payload["series"]
        if row.get("platform") == "UgPhone" and row.get("product_model") == "GVIP"
    )
    assert gvip["current_price"] == 8.99
    assert gvip["price_source"] == "carry_forward"
    assert gvip["points"][-1]["date"] == "2026-08-26"
    assert gvip["points"][-1]["source_collection_date"] == "2026-08-21"
