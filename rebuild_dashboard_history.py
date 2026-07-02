from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from cloud_phone_monitor.utils.dashboard_export import export_dashboard_data, output_run_date
from cloud_phone_monitor.utils.price_quality import write_quality_price_report


def _candidate_sort_key(path: Path) -> tuple[str, float, int]:
    """Sort output candidates by the local/display collection day, not UTC.

    output/latest can be stale after a manual run, while a newer
    output/cloud_phone_monitor_YYYYMMDD_* directory already exists.  Picking
    output/latest first is why rebuilt dashboard data could remain stuck on the
    previous day.
    """
    date_label = output_run_date(path) or "0000-00-00"
    # Directory names include HHMMSS and sort correctly within one date; use mtime
    # as an additional fallback for output/latest.
    try:
        mtime = path.stat().st_mtime
    except Exception:
        mtime = 0.0
    # Prefer real timestamped run directories over output/latest when dates tie,
    # because latest may be a stale copy.
    real_run = 1 if path.name.startswith("cloud_phone_monitor_") else 0
    return (date_label, mtime, real_run)


def _has_dashboard_source(path: Path) -> bool:
    return any((path / name).exists() for name in [
        "quality_price_report.xlsx",
        "products.csv",
        "products.xlsx",
    ])


def candidate_output_dirs() -> list[Path]:
    root = Path("output")
    candidates: list[Path] = []
    latest = root / "latest"
    if latest.exists() and _has_dashboard_source(latest):
        candidates.append(latest)
    if root.exists():
        for item in root.glob("cloud_phone_monitor_*"):
            if item.is_dir() and _has_dashboard_source(item):
                candidates.append(item)
    # Newest UTC+8 business collection date first.  This allows a May 8 run
    # directory to be selected even if its run_summary UTC date is still May 7
    # or output/latest points to the previous run.
    return sorted(candidates, key=_candidate_sort_key, reverse=True)


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
    candidates = candidate_output_dirs()
    if not candidates:
        raise SystemExit(
            "没有找到可用于重建看板的 output 目录。需要 output/latest/quality_price_report.xlsx "
            "或 output/cloud_phone_monitor_*/quality_price_report.xlsx。"
        )
    output_dir = candidates[0]
    print(f"使用输出目录重建看板数据: {output_dir}")
    print(f"识别到的本次数据日期: {output_run_date(output_dir)}")
    if len(candidates) > 1:
        print("候选输出目录（按本地采集日期从新到旧排序）:")
        for item in candidates[:8]:
            print(f"- {output_run_date(item) or 'unknown'}  {item}")
    refresh_quality_report_if_possible(output_dir)
    dashboard_dir = export_dashboard_data(
        output_dir,
        mirror_dirs=[Path("dashboard/public/dashboard_data"), Path("dashboard/dist/dashboard_data")],
    )
    trends_path = dashboard_dir / "price_trends.json"
    if trends_path.exists():
        payload = json.loads(trends_path.read_text(encoding="utf-8"))
        print("价格趋势自然日:", payload.get("history_dates"))
        print("原始采集日期:", payload.get("raw_collection_dates"))
        print("补齐自然日:", payload.get("filled_dates"))
        print("日期补齐模式:", payload.get("date_fill_mode"))
        print("历史日期数量:", payload.get("history_date_count"))
        print("历史点数量:", payload.get("history_point_count"))
        print("carry_forward 点数量:", payload.get("carry_forward_point_count"))
        print("历史运行目录数量:", payload.get("history_run_dir_count"))
    print("看板数据已重建，并已同步到 dashboard/public/dashboard_data 与 dashboard/dist/dashboard_data。")


if __name__ == "__main__":
    main()
