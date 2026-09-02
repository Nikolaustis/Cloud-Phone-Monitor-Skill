from pathlib import Path

import pandas as pd

from cloud_phone_monitor.utils.dashboard_export import collect_historical_trend_points


def _write_run(root: Path, stamp: str, date: str, price: float) -> Path:
    run = root / f"cloud_phone_monitor_{stamp}"
    run.mkdir(parents=True)
    pd.DataFrame([{
        "platform": "UgPhone",
        "crawl_time_local": f"{date}T09:00:00+08:00",
        "product_model": "GVIP",
        "android_version": "10.0",
        "cpu": "4 cores",
        "ram": "4GB",
        "storage": "64GB",
        "server_region": "Singapore",
        "duration": "30 day",
        "purchase_mode": "subscription",
        "price": str(price),
        "stock_status": "available",
        "promotion_text": "Auto-Renew Deal",
    }]).to_csv(run / "products.csv", index=False)
    return run


def test_incremental_history_reuses_unchanged_daily_cache(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    first = _write_run(output, "20260825_010000", "2026-08-25", 8.99)
    _write_run(output, "20260826_010000", "2026-08-26", 9.49)

    first_result = collect_historical_trend_points(first, cache_mode="incremental")
    first_stats = first_result[-1]
    assert first_stats["cache_misses"] == 2
    assert first_stats["cache_hits"] == 0

    second_result = collect_historical_trend_points(first, cache_mode="incremental")
    second_stats = second_result[-1]
    assert second_stats["cache_hits"] == 2
    assert second_stats["cache_misses"] == 0
    assert second_stats["rebuilt_day_count"] == 0


def test_full_history_rebuild_ignores_cache(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    run = _write_run(output, "20260826_010000", "2026-08-26", 9.49)
    collect_historical_trend_points(run, cache_mode="incremental")
    full_result = collect_historical_trend_points(run, cache_mode="full")
    stats = full_result[-1]
    assert stats["mode"] == "full"
    assert stats["cache_hits"] == 0
    assert stats["cache_misses"] == 1
