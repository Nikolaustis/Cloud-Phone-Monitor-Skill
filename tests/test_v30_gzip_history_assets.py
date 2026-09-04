from pathlib import Path

from cloud_phone_monitor.utils.dashboard_export import (
    PRICE_TRENDS_FILE,
    collect_history_from_price_trends,
    read_json_asset,
    split_price_trends_detail_payloads,
    write_gzip_json,
)


def _trend_payload() -> dict:
    return {
        "history_dates": ["2026-08-27", "2026-08-28"],
        "series": [
            {
                "series_id": "ug_gvip_30",
                "platform": "UgPhone",
                "product_model": "GVIP",
                "config": "GVIP / Android 13 / 4 cores / 4GB / 64GB",
                "duration_bucket": 30,
                "duration_display": "30天",
                "purchase_mode": "subscription",
                "points": [
                    {"date": "2026-08-27", "price": 8.99, "price_source": "current"},
                    {"date": "2026-08-28", "price": 8.99, "price_source": "carry_forward"},
                ],
                "regional_points": {
                    "Singapore": [
                        {"date": "2026-08-27", "price": 8.99, "price_source": "current"}
                    ]
                },
                "android_breakdown_series": [
                    {
                        "series_id": "ug_gvip_30_android13",
                        "android_version": "13",
                        "points": [
                            {"date": "2026-08-27", "price": 8.99, "price_source": "current"}
                        ],
                    }
                ],
            }
        ],
    }


def test_gzip_json_is_deterministic_and_round_trips(tmp_path: Path) -> None:
    payload = _trend_payload()
    first = tmp_path / PRICE_TRENDS_FILE
    second = tmp_path / "second.json.gz"
    stats = write_gzip_json(first, payload)
    write_gzip_json(second, payload)

    assert first.read_bytes()[:2] == b"\x1f\x8b"
    assert first.read_bytes() == second.read_bytes()
    assert stats["stored_bytes"] < stats["raw_bytes"]
    assert read_json_asset(first) == payload


def test_price_trend_detail_chunks_use_compressed_asset_names() -> None:
    light, chunks = split_price_trends_detail_payloads(_trend_payload())
    assert light["split_detail_mode"] is True
    assert light["series"][0]["trend_detail_chunk"].endswith(".json.gz")
    assert all(name.endswith(".json.gz") for name in chunks)
    assert "regional_points" not in light["series"][0]
    assert "android_breakdown_series" not in light["series"][0]


def test_legacy_history_reader_accepts_v30_gzip_trends(tmp_path: Path) -> None:
    run = tmp_path / "cloud_phone_monitor_20260828_010000"
    dashboard = run / "dashboard_data"
    dashboard.mkdir(parents=True)
    write_gzip_json(dashboard / PRICE_TRENDS_FILE, _trend_payload())

    history = {}
    loose_history = {}
    collect_history_from_price_trends(run, history, loose_history)

    assert history
    points = next(iter(history.values()))
    assert "2026-08-27" in points
    assert points["2026-08-27"]["price"] == 8.99
