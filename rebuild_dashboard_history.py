from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from cloud_phone_monitor.utils.dashboard_export import (
    PRICE_TRENDS_FILE,
    export_dashboard_data,
    output_run_date,
    read_json_asset,
)
from cloud_phone_monitor.utils.price_quality import write_quality_price_report


def _parse_run_timestamp(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _run_timestamp(path: Path) -> float:
    """Return the collection timestamp without using directory mtime.

    Rebuilding a historical run creates/updates ``dashboard_data`` and changes the
    directory mtime.  Directory mtime therefore cannot be used to decide which
    collection is newest.  Prefer the run summary, then the timestamp encoded in
    a real run directory, and only then the products file mtime.
    """
    summary_path = path / "run_summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        summary = {}
    for key in (
        "end_time_utc",
        "end_time_local",
        "start_time_utc",
        "start_time_local",
        "generated_at_utc",
        "generated_at_local",
    ):
        stamp = _parse_run_timestamp(summary.get(key))
        if stamp is not None:
            return stamp

    match = re.fullmatch(r"cloud_phone_monitor_(\d{8})_(\d{6})(?:_.*)?", path.name)
    if match:
        try:
            parsed = datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
            return parsed.replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            pass

    for name in ("products.csv", "products.xlsx", "run_summary.json"):
        source = path / name
        if source.exists():
            try:
                return source.stat().st_mtime
            except OSError:
                continue
    return 0.0


def _normalize_platform(value: object) -> str:
    text = str(value or "").strip()
    return "UgPhone" if text.lower() == "ugphone" else text


def _source_platforms(path: Path) -> set[str]:
    summary_path = path / "run_summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        counts = summary.get("records_by_platform") or {}
        platforms = {
            _normalize_platform(name)
            for name, count in counts.items()
            if int(count or 0) > 0
        }
        if platforms:
            return platforms
    except Exception:
        pass

    csv_path = path / "products.csv"
    try:
        if csv_path.exists():
            frame = pd.read_csv(csv_path, usecols=["platform"], dtype=object)
            return {_normalize_platform(value) for value in frame["platform"].dropna().unique()}
    except Exception:
        pass
    return set()


def _is_complete_current_source(path: Path) -> bool:
    required = {"UgPhone", "VSPhone", "Redfinger", "LDCloud"}
    return required.issubset(_source_platforms(path))


def _candidate_sort_key(path: Path) -> tuple[float, int]:
    # If exact collection timestamps tie, output/latest wins because it is the
    # explicitly promoted complete dataset.  Never use directory mtime here.
    return (_run_timestamp(path), 1 if path.name == "latest" else 0)


def _has_dashboard_source(path: Path) -> bool:
    return (path / "products.csv").exists() or (path / "products.xlsx").exists()


def candidate_output_dirs() -> list[Path]:
    root = Path("output")
    candidates: list[Path] = []
    latest = root / "latest"
    if latest.exists() and _has_dashboard_source(latest) and _is_complete_current_source(latest):
        candidates.append(latest)
    if root.exists():
        for item in root.glob("cloud_phone_monitor_*"):
            if (
                item.is_dir()
                and _has_dashboard_source(item)
                and _is_complete_current_source(item)
            ):
                candidates.append(item)
    return sorted(candidates, key=_candidate_sort_key, reverse=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild dashboard history from the newest complete four-platform output."
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Explicit complete output directory, for example output/latest.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--incremental",
        action="store_true",
        help="Use the schema-9 per-day history cache; only new/changed days are reparsed (default).",
    )
    mode.add_argument(
        "--full",
        action="store_true",
        help="Ignore history cache and rebuild every historical collection day.",
    )
    return parser.parse_args()


def resolve_output_dir(explicit: str | None) -> tuple[Path, list[Path]]:
    candidates = candidate_output_dirs()
    if explicit:
        selected = Path(explicit)
        if not selected.exists() or not _has_dashboard_source(selected):
            raise SystemExit(f"指定的输出目录不可用: {selected}")
        if not _is_complete_current_source(selected):
            platforms = sorted(_source_platforms(selected))
            raise SystemExit(
                f"指定目录不是完整四平台数据: {selected}; detected={platforms}"
            )
        return selected, [selected, *[item for item in candidates if item.resolve() != selected.resolve()]]
    if not candidates:
        raise SystemExit(
            "没有找到完整四平台 output。需要 output/latest 或 "
            "output/cloud_phone_monitor_* 中同时包含 UgPhone、VSPhone、Redfinger、LDCloud。"
        )
    return candidates[0], candidates


def read_products_for_quality(path: Path) -> pd.DataFrame:
    csv_path = path / "products.csv"
    xlsx_path = path / "products.xlsx"
    if csv_path.exists():
        return pd.read_csv(csv_path, dtype=object, low_memory=False)
    if xlsx_path.exists():
        frames: list[pd.DataFrame] = []
        workbook = pd.ExcelFile(xlsx_path)
        for sheet in workbook.sheet_names:
            try:
                frame = pd.read_excel(xlsx_path, sheet_name=sheet, dtype=object)
                if not frame.empty:
                    frames.append(frame)
            except Exception:
                continue
        if frames:
            return pd.concat(frames, ignore_index=True)
    return pd.DataFrame()


def refresh_quality_report_if_possible(output_dir: Path) -> None:
    # Do not overwrite a complete existing workbook during dashboard rebuild.
    # A previous version regenerated quality_price_report.xlsx from products only;
    # when baseline comparison was unavailable, it produced a one-row diagnostic
    # rationality sheet, which broke the frontend price-change page.
    if (output_dir / "quality_price_report.xlsx").exists():
        print("已存在 quality_price_report.xlsx，跳过重建以避免覆盖完整变价数据。")
        return
    products = read_products_for_quality(output_dir)
    if products.empty:
        print("未找到 products.csv/products.xlsx，跳过质量价格报告重建。")
        return
    try:
        write_quality_price_report(output_dir, products)
        print("已基于当前 products 重建 quality_price_report.xlsx。")
    except Exception as exc:
        print(f"重建 quality_price_report.xlsx 失败，将继续使用既有报告：{exc}")


def main() -> None:
    args = parse_args()
    output_dir, candidates = resolve_output_dir(args.output)
    print(f"使用输出目录重建看板数据: {output_dir}")
    print(f"识别到的本次数据日期: {output_run_date(output_dir)}")
    if len(candidates) > 1:
        print("候选输出目录（按本地采集日期从新到旧排序）:")
        for item in candidates[:8]:
            print(f"- {output_run_date(item) or 'unknown'}  {item}")
    refresh_quality_report_if_possible(output_dir)
    history_cache_mode = "full" if args.full else "incremental"
    print("历史重建模式:", history_cache_mode)
    dashboard_dir = export_dashboard_data(
        output_dir,
        mirror_dirs=[Path("dashboard/public/dashboard_data"), Path("dashboard/dist/dashboard_data")],
        history_cache_mode=history_cache_mode,
    )
    meta_path = dashboard_dir / "meta.json"
    snapshot_path = dashboard_dir / "current_price_snapshot.json"
    if not meta_path.exists() or not snapshot_path.exists():
        raise RuntimeError("Dashboard current-price authority files were not generated.")
    meta_payload = json.loads(meta_path.read_text(encoding="utf-8"))
    snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if meta_payload.get("current_price_authority") != "current_run_products_table":
        raise RuntimeError("Dashboard current prices are not anchored to the current products table.")
    print("当前价格权威来源:", meta_payload.get("current_price_authority"))
    print("当前价格数据版本:", meta_payload.get("current_price_data_revision"))
    print("当前价格来源目录:", snapshot_payload.get("source_output_dir"))
    print("当前价格快照行数:", len(snapshot_payload.get("rows") or []))
    vs_vip_30 = sorted({
        row.get("price")
        for row in (snapshot_payload.get("rows") or [])
        if row.get("platform") == "VSPhone"
        and str(row.get("product_model") or "").upper() == "VIP"
        and float(row.get("duration_days") or 0) == 30
        and row.get("purchase_mode") == "subscription"
    })
    if vs_vip_30:
        print("VSPhone VIP 30天订阅价（本次 products.csv）:", vs_vip_30)

    trends_path = dashboard_dir / PRICE_TRENDS_FILE
    if not trends_path.exists():
        trends_path = dashboard_dir / "price_trends.json"
    if trends_path.exists():
        payload = read_json_asset(trends_path)
        print("价格趋势自然日:", payload.get("history_dates"))
        print("原始采集日期:", payload.get("raw_collection_dates"))
        print("补齐自然日:", payload.get("filled_dates"))
        print("日期补齐模式:", payload.get("date_fill_mode"))
        print("历史日期数量:", payload.get("history_date_count"))
        print("历史点数量:", payload.get("history_point_count"))
        print("carry_forward 点数量:", payload.get("carry_forward_point_count"))
        print("历史运行目录数量:", payload.get("history_run_dir_count"))
        cache = payload.get("history_cache") or {}
        if cache:
            print("历史缓存命中:", cache.get("cache_hits"), "/", cache.get("total_days"))
            print("本轮重算历史日期数:", cache.get("rebuilt_day_count"))

    storage_path = dashboard_dir / "history_storage.json"
    if storage_path.exists():
        storage = json.loads(storage_path.read_text(encoding="utf-8"))
        raw_mb = float(storage.get("raw_history_bytes") or 0) / (1024 * 1024)
        stored_mb = float(storage.get("stored_history_bytes") or 0) / (1024 * 1024)
        print("GitHub Pages 历史存储格式:", storage.get("codec"))
        print("历史静态资源原始 JSON 体积估算: %.2f MB" % raw_mb)
        print("历史静态资源压缩后体积: %.2f MB" % stored_mb)
        print("历史静态资源节省空间: %s%%" % storage.get("space_saving_pct"))
        print("历史压缩资源文件数:", storage.get("compressed_asset_count"))
    print("看板数据已重建，并已同步到 dashboard/public/dashboard_data 与 dashboard/dist/dashboard_data。")


if __name__ == "__main__":
    main()
