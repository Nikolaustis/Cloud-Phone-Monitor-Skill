import argparse
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Type

import pandas as pd

from cloud_phone_monitor.config import MonitorConfig
from cloud_phone_monitor.schemas import ProductRecord
from cloud_phone_monitor.scrapers.ldcloud import LDCloudScraper
from cloud_phone_monitor.scrapers.redfinger import RedfingerScraper
from cloud_phone_monitor.scrapers.ugphone import UGPhoneScraper
from cloud_phone_monitor.scrapers.vsphone import VSPhoneScraper
from cloud_phone_monitor.utils.browser import launch_browser, new_browser_context
from cloud_phone_monitor.utils.baseline import (
    build_baseline_with_current_overlay,
    load_products_table,
    write_current_products_workbook,
    write_baseline_monitor_outputs,
)
from cloud_phone_monitor.utils.dashboard_export import export_dashboard_data
from cloud_phone_monitor.utils.logger import setup_logger
from cloud_phone_monitor.utils.price_quality import write_quality_price_report


LEGACY_UG_PLATFORM = "UG" + "Phone"

SCRAPER_CLASSES: Dict[str, Type] = {
    "VSPhone": VSPhoneScraper,
    "Redfinger": RedfingerScraper,
    "LDCloud": LDCloudScraper,
    "UgPhone": UGPhoneScraper,
    LEGACY_UG_PLATFORM: UGPhoneScraper,
}
PLATFORM_SHEETS = ("UgPhone", "VSPhone", "Redfinger", "LDCloud")
PLATFORM_SHEETS_CN = {
    "UgPhone": "UgPhone采集",
    "VSPhone": "VSPhone采集",
    "Redfinger": "红手指采集",
    "LDCloud": "雷电云手机采集",
}
DEFAULT_BASELINE_PATH = "baselines/products_baseline.xlsx"
ROLLING_BASELINE_PATH = Path("output") / "latest" / "baseline_products_updated.xlsx"
PLATFORM_AUTH_STATES = {
    "VSPhone": Path("output") / "auth" / "vsphone_state.json",
    "Redfinger": Path("output") / "auth" / "redfinger_state.json",
    "LDCloud": Path("output") / "auth" / "ldcloud_state.json",
    "UgPhone": Path("output") / "auth" / "ugphone_state.json",
    LEGACY_UG_PLATFORM: Path("output") / "auth" / "ugphone_state.json",
}
EXPORT_COLUMNS = [
    "platform",
    "source_url",
    "crawl_time_utc",
    "crawl_time_local",
    "supported_server_regions",
    "currency",
    "product_category",
    "product_name",
    "product_model",
    "device_model",
    "android_version",
    "cpu",
    "ram",
    "storage",
    "price",
    "original_price",
    "discount_price",
    "billing_period",
    "duration",
    "stock_status",
    "promotion_text",
    "promotion_start_time",
    "promotion_end_time",
    "raw_text",
    "extraction_method",
    "confidence",
    "screenshot_path",
    "html_path",
    "api_response_path",
    "notes",
    "record_hash",
]
EVIDENCE_COLUMNS = {
    "raw_text",
    "screenshot_path",
    "html_path",
    "api_response_path",
    "notes",
    "record_hash",
}


def normalize_platform_name(value) -> str:
    text = str(value or "").strip()
    if text.lower() == "ugphone":
        return "UgPhone"
    return text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor cloud phone competitor products against a baseline price file.")
    parser.add_argument("--headed", action="store_true", help="Run Chromium in visible headed mode.")
    parser.add_argument("--output", type=str, default=None, help="Custom output directory.")
    parser.add_argument("--platform", action="append", default=None, help="Run one or more platforms, e.g. --platform VSPhone.")
    parser.add_argument("--no-safe-click", action="store_true", help="Disable conservative filter/tab clicking.")
    parser.add_argument("--storage-state", type=str, default=None, help="Load Playwright login/session state from this JSON file.")
    parser.add_argument("--save-storage-state", type=str, default=None, help="Save Playwright login/session state to this JSON file after the run.")
    parser.add_argument("--login-wait-seconds", type=int, default=0, help="Keep headed browser open before scraping so a human can sign in.")
    parser.add_argument(
        "--baseline",
        type=str,
        default=DEFAULT_BASELINE_PATH,
        help="Baseline products workbook/CSV/JSONL used for price monitoring.",
    )
    parser.add_argument(
        "--init-baseline",
        action="store_true",
        help="Save the current aggregated products as the baseline after scraping.",
    )
    parser.add_argument(
        "--skip-baseline-monitor",
        action="store_true",
        help="Only collect products; do not compare against the baseline file.",
    )
    parser.add_argument(
        "--skip-quality-price-monitor",
        action="store_true",
        help="Skip UgPhone-based comparable configuration and quality-adjusted price monitoring.",
    )
    parser.add_argument(
        "--quality-price-config",
        type=str,
        default=None,
        help="Optional JSON config overriding quality price monitor weights, mappings, and thresholds.",
    )
    return parser.parse_args()


def default_output_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path("output") / f"cloud_phone_monitor_{stamp}"


def write_jsonl(path: Path, rows: List[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def is_missing(value) -> bool:
    try:
        return pd.isna(value)
    except Exception:
        return value in [None, ""]


def unique_join(values, sep: str = "; ") -> str | None:
    out = []
    for value in values:
        if is_missing(value):
            continue
        text = str(value).strip()
        if not text:
            continue
        for part in text.split(sep):
            part = part.strip()
            if part and part not in out:
                out.append(part)
    return sep.join(out) if out else None


def compact_join(values, max_len: int = 32000) -> str | None:
    joined = unique_join(values)
    if joined and len(joined) > max_len:
        return joined[: max_len - 20] + "...[truncated]"
    return joined


def aggregate_supported_servers(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        out = df.copy()
        for col in EXPORT_COLUMNS:
            if col not in out.columns:
                out[col] = None
        return out[EXPORT_COLUMNS]

    working = df.copy()
    if "server_region" not in working.columns:
        working["server_region"] = None
    for col in EXPORT_COLUMNS:
        if col not in working.columns:
            working[col] = None

    group_columns = [
        col
        for col in EXPORT_COLUMNS
        if col not in EVIDENCE_COLUMNS and col != "supported_server_regions"
    ]
    grouped_rows = []
    for _, group in working.groupby(group_columns, dropna=False, sort=False):
        row = group.iloc[0].to_dict()
        row["supported_server_regions"] = unique_join(group.get("server_region", []))
        for col in EVIDENCE_COLUMNS:
            if col == "record_hash":
                continue
            row[col] = compact_join(group[col]) if col in group.columns else None
        hash_material = {
            col: row.get(col)
            for col in group_columns
            if col not in {"crawl_time_utc", "crawl_time_local"}
        }
        hash_material["supported_server_regions"] = row.get("supported_server_regions")
        row["record_hash"] = hashlib.sha256(
            json.dumps(hash_material, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        ).hexdigest()[:24]
        grouped_rows.append({col: row.get(col) for col in EXPORT_COLUMNS})

    return pd.DataFrame(grouped_rows, columns=EXPORT_COLUMNS)


def make_missing_field_stats(rows: List[dict]) -> dict:
    stats = {}
    for col in EXPORT_COLUMNS:
        missing = sum(1 for r in rows if r.get(col) in [None, ""])
        stats[col] = missing
    return stats


def clean_values(series: pd.Series) -> list[str]:
    values = []
    for value in series.dropna().drop_duplicates().tolist():
        text = str(value).strip()
        if text and text not in values:
            values.append(text)
    return values


def join_values(values: list[str], limit: int | None = None) -> str:
    values = list(dict.fromkeys(values))
    if limit and len(values) > limit:
        return "、".join(values[:limit]) + f" 等 {len(values)} 项"
    return "、".join(values) if values else "无"


def sort_versions(values: list[str]) -> list[str]:
    def key(value: str):
        try:
            return (0, float(value))
        except Exception:
            return (1, value)

    return sorted(values, key=key)


def sort_durations(values: list[str]) -> list[str]:
    unit_order = {"hour": 0, "day": 1, "week": 2, "month": 3, "year": 4}

    def key(value: str):
        parts = value.split()
        try:
            number = float(parts[0])
        except Exception:
            number = 0
        unit = parts[1] if len(parts) > 1 else ""
        return (unit_order.get(unit, 99), number, value)

    return sorted(values, key=key)


def price_range(df: pd.DataFrame) -> str:
    nums = pd.to_numeric(df.get("price"), errors="coerce").dropna()
    if nums.empty:
        return "暂无价格"
    return f"US${nums.min():g} - US${nums.max():g}"


def write_product_brief(path: Path, df: pd.DataFrame) -> None:
    lines = [
        "云手机竞品价格采集简报",
        f"生成时间 UTC: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "口径: Excel 已按除服务器外的业务字段聚合，supported_server_regions 列列出该行支持的全部服务器地址。",
        "",
    ]
    for platform in PLATFORM_SHEETS:
        sheet = df[df["platform"] == platform].copy()
        lines.append(f"[{platform}]")
        lines.append(f"- 聚合后记录数: {len(sheet)}")
        lines.append(f"- 产品/套餐: {join_values(sorted(clean_values(sheet['product_model'])), 20)}")
        device_models = clean_values(sheet["device_model"]) if "device_model" in sheet else []
        if device_models:
            lines.append(f"- 设备机型: {join_values(sorted(device_models), 20)}")
        androids = sort_versions(clean_values(sheet["android_version"]))
        lines.append(f"- 安卓版本: {join_values(androids, 20)}")

        server_tokens = []
        for cell in clean_values(sheet["supported_server_regions"]):
            for part in cell.split(";"):
                part = part.strip()
                if part and part not in server_tokens:
                    server_tokens.append(part)
        lines.append(f"- 支持服务器: {join_values(server_tokens, 40)}")

        durations = sort_durations(clean_values(sheet["duration"]))
        lines.append(f"- 购买天数/时长: {join_values(durations, 40)}")
        lines.append(f"- 价格区间: {price_range(sheet)}")
        lines.append(f"- 库存状态: {sheet['stock_status'].value_counts(dropna=False).to_dict()}")
        lines.append("- 低价样例:")
        samples = sheet.assign(_price_num=pd.to_numeric(sheet["price"], errors="coerce")).sort_values("_price_num").head(5)
        for _, row in samples.iterrows():
            device_model = row.get("device_model")
            android = row.get("android_version")
            lines.append(
                f"  * {row.get('product_model') or ''} / "
                f"{'' if is_missing(device_model) else device_model} / "
                f"Android {'不区分' if is_missing(android) else android} / "
                f"{row.get('duration')}: US${row.get('price')}；"
                f"服务器: {row.get('supported_server_regions') or '无'}"
            )
        if platform == "VSPhone":
            blank_android = int(sheet["android_version"].isna().sum())
            if blank_android:
                lines.append(
                    f"- VSPhone 游戏挂机专用机: {blank_android} 行 android_version 留空，表示该类产品不按安卓版本区分。"
                )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def platform_storage_state(platform: str) -> Path | None:
    path = PLATFORM_AUTH_STATES.get(platform)
    if path and path.exists():
        return path
    return None


def write_outputs(
    output_dir: Path,
    records: List[ProductRecord],
    api_candidates: List[dict],
    run_summary: dict,
    baseline_path: Path | None = None,
    init_baseline: bool = False,
    skip_baseline_monitor: bool = False,
    skip_quality_price_monitor: bool = False,
    quality_price_config_path: Path | None = None,
) -> None:
    rows = []
    for record in records:
        raw_row = record.finalize().as_dict()
        raw_row["platform"] = normalize_platform_name(raw_row.get("platform"))
        raw_row["supported_server_regions"] = raw_row.get("server_region")
        rows.append(raw_row)
    for row in rows:
        for col in [*EXPORT_COLUMNS, "server_region"]:
            row.setdefault(col, None)

    df = aggregate_supported_servers(pd.DataFrame(rows))
    df.to_csv(output_dir / "products.csv", index=False, encoding="utf-8-sig")
    write_current_products_workbook(output_dir / "products.xlsx", df, PLATFORM_SHEETS, PLATFORM_SHEETS_CN)
    write_product_brief(output_dir / "product_brief.txt", df)
    write_jsonl(output_dir / "products.jsonl", rows)

    baseline_result = None
    if baseline_path is not None and init_baseline:
        write_current_products_workbook(baseline_path, df, PLATFORM_SHEETS)
        run_summary["baseline_initialized"] = str(baseline_path)
    baseline_df = pd.DataFrame()
    if baseline_path is not None and baseline_path.exists():
        baseline_df = load_products_table(baseline_path)

    ug_near_config_comparison = None
    if skip_quality_price_monitor:
        run_summary["quality_price_monitor"] = {"enabled": False, "reason": "skipped_by_cli"}
    else:
        quality_input_df = (
            build_baseline_with_current_overlay(baseline_df, df)
            if baseline_path is not None and not baseline_df.empty
            else df
        )
        quality_result, ug_near_config_comparison = write_quality_price_report(
            output_dir,
            quality_input_df,
            baseline_df=baseline_df,
            config_path=quality_price_config_path,
        )
        if baseline_path is not None and not baseline_df.empty:
            quality_result["input_basis"] = "baseline_with_current_overlay"
            quality_result["fallback_baseline_rows"] = int(
                quality_input_df["notes"].astype(str).str.contains("current_missing_used_baseline", regex=False).sum()
            ) if "notes" in quality_input_df.columns else 0
        run_summary["quality_price_monitor"] = quality_result

    if baseline_path is not None and not skip_baseline_monitor:
        baseline_result = write_baseline_monitor_outputs(
            output_dir,
            df,
            baseline_path,
            PLATFORM_SHEETS,
            ug_near_config_comparison=ug_near_config_comparison,
        )
        run_summary["baseline_monitor"] = baseline_result

    (output_dir / "api_candidates.json").write_text(
        json.dumps(api_candidates, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    run_summary["total_records"] = len(rows)
    run_summary["records_by_platform"] = dict(Counter(normalize_platform_name(r.get("platform")) for r in rows))
    run_summary["missing_field_stats"] = make_missing_field_stats(rows)
    (output_dir / "run_summary.json").write_text(
        json.dumps(run_summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    export_dashboard_data(output_dir)

    latest_dir = Path("output") / "latest"
    latest_jsonl = latest_dir / "products.jsonl"

    latest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output_dir / "products.jsonl", latest_jsonl)
    shutil.copy2(output_dir / "products.csv", latest_dir / "products.csv")
    shutil.copy2(output_dir / "product_brief.txt", latest_dir / "product_brief.txt")
    shutil.copy2(output_dir / "products.xlsx", latest_dir / "products.xlsx")
    shutil.copy2(output_dir / "run_summary.json", latest_dir / "run_summary.json")
    keep_latest_xlsx = {
        "products.xlsx",
        "daily_changes.xlsx",
        "baseline_products_updated.xlsx",
        "quality_price_report.xlsx",
    }
    for old_xlsx in latest_dir.glob("*.xlsx"):
        if old_xlsx.name not in keep_latest_xlsx:
            old_xlsx.unlink()
    quality_path = output_dir / "quality_price_report.xlsx"
    if quality_path.exists():
        shutil.copy2(quality_path, latest_dir / "quality_price_report.xlsx")
        print(f"Quality price report: {quality_path}")
    if baseline_result:
        for name in ["daily_changes.xlsx", "baseline_products_updated.xlsx"]:
            source = output_dir / name
            if source.exists():
                shutil.copy2(source, latest_dir / name)
        print(f"Daily changes: {output_dir / 'daily_changes.xlsx'}")
        print(f"Updated baseline: {output_dir / 'baseline_products_updated.xlsx'}")

    # Keep both the Vite dev/public data directory and the built static
    # dashboard data directory fresh after every collection run.
    # Previously only dashboard/public/dashboard_data was updated here, so
    # users who opened dashboard/dist/index.html could still see stale data
    # even though output/latest already contained the newest run.
    export_dashboard_data(
        latest_dir,
        mirror_dirs=[
            Path("dashboard") / "public" / "dashboard_data",
            Path("dashboard") / "dist" / "dashboard_data",
        ],
    )


def main() -> None:
    args = parse_args()
    config = MonitorConfig.default()
    config.headless = not args.headed
    config.output_dir = Path(args.output) if args.output else default_output_dir()
    config.platforms = args.platform
    config.safe_interactions = not args.no_safe_click
    config.storage_state = Path(args.storage_state) if args.storage_state else None
    config.save_storage_state = Path(args.save_storage_state) if args.save_storage_state else None
    config.login_wait_seconds = args.login_wait_seconds
    quality_price_config_path = Path(args.quality_price_config) if args.quality_price_config else None
    baseline_path = Path(args.baseline) if args.baseline else None
    if args.baseline == DEFAULT_BASELINE_PATH and ROLLING_BASELINE_PATH.exists() and not args.init_baseline:
        baseline_path = ROLLING_BASELINE_PATH
    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logger(output_dir)
    run_summary = {
        "start_time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "end_time_utc": None,
        "targets": {name: target.url for name, target in config.selected_targets().items()},
        "blocked_pages": {},
        "failed_pages": {},
        "warnings": [],
        "api_candidate_count": 0,
    }

    all_records: List[ProductRecord] = []
    all_api_candidates: List[dict] = []

    logger.info("Output directory: %s", output_dir)
    logger.info("Headless: %s", config.headless)

    with launch_browser(headless=config.headless, storage_state=config.storage_state) as (_, browser, context):
        if config.login_wait_seconds > 0:
            login_pages = []
            for name, target in config.selected_targets().items():
                login_page = context.new_page()
                login_page.set_default_timeout(config.browser_timeout_ms)
                login_pages.append(login_page)
                logger.info(
                    "Opening login page for %s (%s seconds): %s",
                    name,
                    config.login_wait_seconds,
                    target.url,
                )
                try:
                    login_page.goto(target.url, wait_until="domcontentloaded", timeout=config.browser_timeout_ms)
                except Exception as exc:
                    logger.warning("[%s] login page navigation failed: %s", name, exc)
            if login_pages:
                try:
                    login_pages[0].bring_to_front()
                except Exception:
                    pass
                login_pages[0].wait_for_timeout(config.login_wait_seconds * 1000)
            for login_page in login_pages:
                try:
                    login_page.close()
                except Exception:
                    pass

        for name, target in config.selected_targets().items():
            scraper_cls = SCRAPER_CLASSES.get(name)
            if not scraper_cls:
                run_summary["warnings"].append(f"No scraper class for {name}")
                continue
            scraper_context = context
            close_scraper_context = False
            state_path = None
            if config.storage_state is None:
                state_path = platform_storage_state(name)
                if state_path is not None:
                    scraper_context = new_browser_context(browser, state_path)
                    close_scraper_context = True
                    run_summary.setdefault("platform_storage_states", {})[name] = str(state_path)
                    logger.info("[%s] using platform storage state: %s", name, state_path)
            scraper = scraper_cls(scraper_context, target, config, output_dir, logger)
            try:
                records = scraper.scrape()
                all_records.extend(records)
                all_api_candidates.extend(scraper.api_candidates)
                if scraper.blocked_reason:
                    run_summary["blocked_pages"][name] = scraper.blocked_reason
                if not records:
                    run_summary["warnings"].append(f"{name}: no product records extracted; inspect artifacts")
                logger.info("[%s] extracted records: %s", name, len(records))
            except Exception as exc:
                logger.exception("[%s] failed", name)
                run_summary["failed_pages"][name] = f"{type(exc).__name__}: {exc}"
            finally:
                if close_scraper_context:
                    try:
                        scraper_context.close()
                    except Exception:
                        pass

        if config.save_storage_state:
            config.save_storage_state.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(config.save_storage_state))
            run_summary["saved_storage_state"] = str(config.save_storage_state)

    run_summary["api_candidate_count"] = len(all_api_candidates)
    run_summary["end_time_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_outputs(
        output_dir,
        all_records,
        all_api_candidates,
        run_summary,
        baseline_path=baseline_path,
        init_baseline=args.init_baseline,
        skip_baseline_monitor=args.skip_baseline_monitor,
        skip_quality_price_monitor=args.skip_quality_price_monitor,
        quality_price_config_path=quality_price_config_path,
    )

    logger.info("Done. output directory: %s", output_dir)
    print(f"Done: {output_dir}")
    if not args.skip_baseline_monitor:
        print(f"Daily changes: {output_dir / 'daily_changes.xlsx'}")
        print(f"Updated baseline: {output_dir / 'baseline_products_updated.xlsx'}")
    if not args.skip_quality_price_monitor:
        print(f"Quality price report: {output_dir / 'quality_price_report.xlsx'}")
    print(f"Summary: {output_dir / 'run_summary.json'}")


if __name__ == "__main__":
    main()
