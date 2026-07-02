from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from cloud_phone_monitor.utils.price_quality import QUALITY_HEADER_CN

BASE_PLATFORM = "UgPhone"

BASELINE_KEY_COLUMNS = [
    "platform",
    "product_category",
    "product_name",
    "product_model",
    "device_model",
    "android_version",
    "cpu",
    "ram",
    "storage",
    "billing_period",
    "duration",
]

PRICE_COLUMNS = ["price", "original_price", "discount_price"]

SUMMARY_COLUMNS = [
    "platform",
    "baseline_products",
    "matched_current_products",
    "unchanged",
    "price_down",
    "price_up",
    "current_price_missing",
    "baseline_price_missing",
    "promotion_keyword",
]

COMPARISON_COLUMNS = [
    "monitor_status",
    "activity_price_detected",
    *BASELINE_KEY_COLUMNS,
    "currency",
    "baseline_min_price",
    "current_min_price",
    "price_delta",
    "price_delta_pct",
    "ug_reference_min_price",
    "vs_ug_price_delta",
    "vs_ug_price_delta_pct",
    "baseline_price_range",
    "current_price_range",
    "current_promotion_text",
    "promotion_keyword_alert",
    "baseline_rows",
    "current_rows",
    "identity_key",
    "notes",
]

PRODUCT_HEADER_CN = {
    "platform": "平台",
    "source_url": "来源链接",
    "crawl_time_utc": "采集时间UTC",
    "crawl_time_local": "采集时间本地",
    "supported_server_regions": "支持服务器地区",
    "currency": "币种",
    "product_category": "产品类别",
    "product_name": "产品名称",
    "product_model": "套餐型号",
    "device_model": "设备型号",
    "android_version": "安卓版本",
    "cpu": "CPU",
    "ram": "内存",
    "storage": "存储",
    "price": "价格",
    "original_price": "原价",
    "discount_price": "折扣价",
    "billing_period": "计费周期",
    "duration": "购买时长",
    "stock_status": "库存状态",
    "promotion_text": "活动文案",
    "promotion_start_time": "活动开始时间",
    "promotion_end_time": "活动结束时间",
    "raw_text": "原始文本",
    "extraction_method": "提取方式",
    "confidence": "置信度",
    "screenshot_path": "截图路径",
    "html_path": "HTML路径",
    "api_response_path": "API响应路径",
    "notes": "备注",
    "record_hash": "记录哈希",
}

REPORT_HEADER_CN = {
    **PRODUCT_HEADER_CN,
    "monitor_status": "监测状态",
    "activity_price_detected": "是否发现活动价",
    "baseline_products": "基准商品数",
    "matched_current_products": "本次匹配商品数",
    "unchanged": "价格未变",
    "price_down": "降价",
    "price_up": "涨价",
    "current_price_missing": "本次价格缺失",
    "baseline_price_missing": "基准价格缺失",
    "promotion_keyword": "促销关键词",
    "baseline_min_price": "基准最低价",
    "current_min_price": "本次最低价",
    "price_delta": "价格变化",
    "price_delta_pct": "价格变化比例",
    "ug_reference_min_price": "UG参考最低价",
    "vs_ug_price_delta": "较UG价格差",
    "vs_ug_price_delta_pct": "较UG价格差比例",
    "baseline_price_range": "基准价格范围",
    "current_price_range": "本次价格范围",
    "current_promotion_text": "本次活动文案",
    "promotion_keyword_alert": "促销关键词提醒",
    "baseline_rows": "基准行数",
    "current_rows": "本次匹配行数",
    "identity_key": "商品身份键",
}

CONFIG_PRICE_HEADER_CN = {
    "cpu": "CPU",
    "ram": "内存",
    "storage": "存储",
    "duration": "购买时长",
    "ugphone_product_models": "UgPhone套餐型号",
    "ugphone_min_price": "UgPhone最低价",
    "ugphone_price_range": "UgPhone价格范围",
    "ugphone_server_regions": "UgPhone服务器地区",
    "ugphone_promotion_text": "UgPhone活动文案",
    "ugphone_rows": "UgPhone匹配行数",
    "vsphone_product_models": "VSPhone套餐型号",
    "vsphone_min_price": "VSPhone最低价",
    "vsphone_price_range": "VSPhone价格范围",
    "vsphone_server_regions": "VSPhone服务器地区",
    "vsphone_promotion_text": "VSPhone活动文案",
    "vsphone_rows": "VSPhone匹配行数",
    "vsphone_vs_ug_delta": "VSPhone较UG价差",
    "vsphone_vs_ug_delta_pct": "VSPhone较UG价差比例",
    "redfinger_product_models": "红手指套餐型号",
    "redfinger_min_price": "红手指最低价",
    "redfinger_price_range": "红手指价格范围",
    "redfinger_server_regions": "红手指服务器地区",
    "redfinger_promotion_text": "红手指活动文案",
    "redfinger_rows": "红手指匹配行数",
    "redfinger_vs_ug_delta": "红手指较UG价差",
    "redfinger_vs_ug_delta_pct": "红手指较UG价差比例",
    "ldcloud_product_models": "雷电云手机套餐型号",
    "ldcloud_min_price": "雷电云手机最低价",
    "ldcloud_price_range": "雷电云手机价格范围",
    "ldcloud_server_regions": "雷电云手机服务器地区",
    "ldcloud_promotion_text": "雷电云手机活动文案",
    "ldcloud_rows": "雷电云手机匹配行数",
    "ldcloud_vs_ug_delta": "雷电云手机较UG价差",
    "ldcloud_vs_ug_delta_pct": "雷电云手机较UG价差比例",
}

CN_TO_EN = {value: key for key, value in {**PRODUCT_HEADER_CN, **REPORT_HEADER_CN, **CONFIG_PRICE_HEADER_CN}.items()}

REPORT_SHEETS_CN = {
    "summary": "汇总",
    "changes": "变化明细",
    "ug_config_prices": "UG同配置价格对比",
    "ug_near_config_prices": "UG相近配置价格对比",
}

PLATFORM_SHEETS_CN = {
    BASE_PLATFORM: "UgPhone价格",
    "VSPhone": "VSPhone价格",
    "Redfinger": "红手指价格",
    "LDCloud": "雷电云手机价格",
}

BASELINE_PLATFORM_SHEETS_CN = {
    BASE_PLATFORM: "UgPhone基准",
    "VSPhone": "VSPhone基准",
    "Redfinger": "红手指基准",
    "LDCloud": "雷电云手机基准",
}

PRICE_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
SERVER_SEPARATORS = re.compile(r"[;；,，、]\s*")
PROMOTION_KEYWORDS = [
    "秒杀",
    "促销",
    "限时",
    "优惠",
    "折",
    "新用户",
    "专享",
    "seckill",
    "flash sale",
    "promotion",
    "promo",
    "limited",
    "discount",
]


def missing(value) -> bool:
    if value is None:
        return True
    try:
        result = pd.isna(value)
    except Exception:
        return False
    return bool(result) if isinstance(result, bool) else False


def as_text(value) -> str:
    if missing(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def normalize_platform_name(value) -> str:
    text = as_text(value)
    if text.lower() == "ugphone":
        return BASE_PLATFORM
    return text


def clean_number(value) -> float | None:
    text = as_text(value).replace(",", "")
    if not text:
        return None
    match = PRICE_PATTERN.search(text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def format_number(value) -> str:
    if value is None or missing(value):
        return ""
    return f"{float(value):g}"


def unique_text(values: Iterable, sep: str = "; ") -> str:
    seen = []
    for value in values:
        text = as_text(value)
        if text and text not in seen:
            seen.append(text)
    return sep.join(seen)


def unique_split_text(values: Iterable, sep: str = "; ") -> str:
    seen = []
    for value in values:
        text = as_text(value)
        if not text:
            continue
        for part in SERVER_SEPARATORS.split(text):
            item = part.strip()
            if item and item not in seen:
                seen.append(item)
    return sep.join(seen)


def identity_key(row: pd.Series | dict) -> str:
    return "|".join(as_text(row.get(col)).lower() for col in BASELINE_KEY_COLUMNS)


def ug_reference_key(row: pd.Series | dict) -> str:
    columns = ["cpu", "ram", "storage", "duration"]
    return "|".join(as_text(row.get(col)).lower() for col in columns)


def config_key(row: pd.Series | dict) -> str:
    return ug_reference_key(row)


def promotion_keyword_alert(text: str) -> str:
    lowered = as_text(text).lower()
    if not lowered:
        return ""
    hits = [kw for kw in PROMOTION_KEYWORDS if kw.lower() in lowered]
    return "; ".join(dict.fromkeys(hits))


def infer_platform_from_sheet(sheet_name: str) -> str:
    name = sheet_name.lower()
    if "ugphone" in name:
        return BASE_PLATFORM
    if "redfinger" in name or "红手指" in sheet_name:
        return "Redfinger"
    if "ldcloud" in name or "ld cloud" in name or "雷电" in sheet_name:
        return "LDCloud"
    if "vsphone" in name:
        return "VSPhone"
    return sheet_name


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={col: CN_TO_EN.get(col, col) for col in df.columns})


def to_chinese_columns(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    return df.rename(columns={col: mapping.get(col, col) for col in df.columns})


def load_products_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        sheets = pd.read_excel(path, sheet_name=None, dtype=object)
        frames = []
        for sheet_name, frame in sheets.items():
            if frame.empty:
                continue
            frame = normalize_columns(frame.dropna(how="all").copy())
            if frame.empty or "price" not in frame.columns:
                continue
            if "platform" not in frame.columns:
                frame["platform"] = infer_platform_from_sheet(sheet_name)
            frames.append(frame)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    if suffix == ".csv":
        return normalize_columns(pd.read_csv(path, dtype=object))

    if suffix == ".jsonl":
        rows = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return normalize_columns(pd.DataFrame(rows))

    raise ValueError(f"Unsupported baseline file format: {path}")


def normalize_products(df: pd.DataFrame) -> pd.DataFrame:
    out = normalize_columns(df.copy())
    for col in BASELINE_KEY_COLUMNS:
        if col not in out.columns:
            out[col] = None
    for col in ["currency", *PRICE_COLUMNS, "supported_server_regions", "server_region"]:
        if col not in out.columns:
            out[col] = None
    if out["supported_server_regions"].map(as_text).eq("").all() and "server_region" in out.columns:
        out["supported_server_regions"] = out["server_region"]
    out["platform"] = out["platform"].map(normalize_platform_name)
    out["_identity_key"] = out.apply(identity_key, axis=1)
    return out


def price_range(values: Iterable) -> str:
    numbers = [number for number in (clean_number(value) for value in values) if number is not None]
    if not numbers:
        return ""
    low = min(numbers)
    high = max(numbers)
    return format_number(low) if low == high else f"{format_number(low)} - {format_number(high)}"


def summarize_products(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[*BASELINE_KEY_COLUMNS, "identity_key"])

    work = normalize_products(df)
    rows = []
    for key, group in work.groupby("_identity_key", dropna=False, sort=False):
        first = group.iloc[0]
        price_numbers = [number for number in (clean_number(value) for value in group["price"]) if number is not None]
        discount_numbers = [
            number for number in (clean_number(value) for value in group["discount_price"]) if number is not None
        ]
        all_numbers = price_numbers or discount_numbers
        row = {col: as_text(first.get(col)) or None for col in BASELINE_KEY_COLUMNS}
        row.update(
            {
                "identity_key": key,
                "currency": unique_text(group["currency"]),
                "min_price": min(all_numbers) if all_numbers else None,
                "max_price": max(all_numbers) if all_numbers else None,
                "price_range": price_range(group["price"]),
                "promotion_text": unique_text(group["promotion_text"]) if "promotion_text" in group else "",
                "source_rows": int(len(group)),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def compare_products(
    current_df: pd.DataFrame, baseline_df: pd.DataFrame, platforms: Iterable[str]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    current = summarize_products(current_df)
    baseline = summarize_products(baseline_df)
    current_by_key = {row["identity_key"]: row for _, row in current.iterrows()}
    ug_by_ref_key = build_ug_reference_lookup(current)

    rows = []
    for _, baseline_row in baseline.iterrows():
        key = baseline_row["identity_key"]
        current_row = current_by_key.get(key)
        flags = []
        notes = []
        baseline_price = baseline_row.get("min_price")
        current_price = current_row.get("min_price") if current_row is not None else None
        price_delta = None
        price_delta_pct = None
        ug_price = None
        vs_ug_delta = None
        vs_ug_delta_pct = None
        if normalize_platform_name(baseline_row.get("platform")) != BASE_PLATFORM:
            ug_price = ug_by_ref_key.get(ug_reference_key(baseline_row))

        if baseline_price is not None and current_price is not None:
            price_delta = current_price - baseline_price
            if baseline_price:
                price_delta_pct = price_delta / baseline_price
            if price_delta < -0.000001:
                flags.append("price_down")
            elif price_delta > 0.000001:
                flags.append("price_up")
        elif baseline_price is not None and current_price is None:
            flags.append("current_price_missing")
            notes.append("本次采集没有匹配到该基准商品的价格，已保留基准结构。")
        elif baseline_price is None and current_price is not None:
            flags.append("baseline_price_missing")
            notes.append("基准商品没有可解析价格，本次采集有价格。")

        if not flags:
            flags.append("unchanged")
        promo_text = as_text(current_row.get("promotion_text")) if current_row is not None else ""
        promo_alert = promotion_keyword_alert(promo_text)
        if promo_alert:
            flags.append("promotion_keyword")
            notes.append(f"本次活动文案命中促销关键词: {promo_alert}")

        if ug_price is not None and current_price is not None:
            vs_ug_delta = current_price - ug_price
            if ug_price:
                vs_ug_delta_pct = vs_ug_delta / ug_price

        row = {
            "monitor_status": "; ".join(flags),
            "activity_price_detected": "yes" if "price_down" in flags else "no",
            "currency": as_text(current_row.get("currency")) if current_row is not None else as_text(baseline_row.get("currency")),
            "baseline_min_price": baseline_price,
            "current_min_price": current_price,
            "price_delta": price_delta,
            "price_delta_pct": price_delta_pct,
            "ug_reference_min_price": ug_price,
            "vs_ug_price_delta": vs_ug_delta,
            "vs_ug_price_delta_pct": vs_ug_delta_pct,
            "baseline_price_range": as_text(baseline_row.get("price_range")),
            "current_price_range": as_text(current_row.get("price_range")) if current_row is not None else "",
            "current_promotion_text": promo_text,
            "promotion_keyword_alert": promo_alert,
            "baseline_rows": int(baseline_row.get("source_rows")),
            "current_rows": int(current_row.get("source_rows")) if current_row is not None else 0,
            "identity_key": key,
            "notes": " ".join(notes),
        }
        for col in BASELINE_KEY_COLUMNS:
            row[col] = as_text(baseline_row.get(col)) or None
        rows.append(row)

    comparison = pd.DataFrame(rows, columns=COMPARISON_COLUMNS)
    summary = build_summary(comparison, baseline, platforms)
    alerts = build_alerts(comparison)
    return comparison, summary, alerts


def build_ug_reference_lookup(current: pd.DataFrame) -> dict[str, float]:
    lookup: dict[str, float] = {}
    if current.empty:
        return lookup
    ug_rows = current[current["platform"].map(normalize_platform_name) == BASE_PLATFORM]
    for _, row in ug_rows.iterrows():
        key = ug_reference_key(row)
        price = row.get("min_price")
        if price is None or missing(price):
            continue
        previous = lookup.get(key)
        lookup[key] = float(price) if previous is None else min(previous, float(price))
    return lookup


def numeric_prices(values: Iterable) -> list[float]:
    return [number for number in (clean_number(value) for value in values) if number is not None]


def summarize_price_group(group: pd.DataFrame, prefix: str) -> dict[str, object]:
    prices = numeric_prices(group.get("price", []))
    min_price = min(prices) if prices else None
    max_price = max(prices) if prices else None
    if min_price is None:
        price_range_text = ""
    elif min_price == max_price:
        price_range_text = format_number(min_price)
    else:
        price_range_text = f"{format_number(min_price)} - {format_number(max_price)}"
    return {
        f"{prefix}_product_models": unique_text(group.get("product_model", [])),
        f"{prefix}_min_price": min_price,
        f"{prefix}_price_range": price_range_text,
        f"{prefix}_server_regions": unique_split_text(group.get("supported_server_regions", [])),
        f"{prefix}_promotion_text": unique_text(group.get("promotion_text", [])),
        f"{prefix}_rows": int(len(group)),
    }


def build_ug_config_price_comparison(current_df: pd.DataFrame, platforms: Iterable[str]) -> pd.DataFrame:
    work = normalize_products(current_df)
    if work.empty:
        return pd.DataFrame()
    for col in ["price", "promotion_text", "supported_server_regions"]:
        if col not in work.columns:
            work[col] = None
    work["_config_key"] = work.apply(config_key, axis=1)

    ug_rows = work[work["platform"].map(normalize_platform_name) == BASE_PLATFORM].copy()
    if ug_rows.empty:
        return pd.DataFrame()

    rows = []
    competitor_platforms = [normalize_platform_name(platform) for platform in platforms if normalize_platform_name(platform) != BASE_PLATFORM]
    for key, ug_group in ug_rows.groupby("_config_key", dropna=False, sort=True):
        first = ug_group.iloc[0]
        row = {
            "cpu": as_text(first.get("cpu")),
            "ram": as_text(first.get("ram")),
            "storage": as_text(first.get("storage")),
            "duration": as_text(first.get("duration")),
            **summarize_price_group(ug_group, "ugphone"),
        }
        ug_min = row.get("ugphone_min_price")
        for platform in competitor_platforms:
            prefix = platform.lower()
            platform_group = work[(work["platform"] == platform) & (work["_config_key"] == key)].copy()
            if platform_group.empty:
                row.update(
                    {
                        f"{prefix}_product_models": "",
                        f"{prefix}_min_price": None,
                        f"{prefix}_price_range": "",
                        f"{prefix}_server_regions": "",
                        f"{prefix}_promotion_text": "",
                        f"{prefix}_rows": 0,
                        f"{prefix}_vs_ug_delta": None,
                        f"{prefix}_vs_ug_delta_pct": None,
                    }
                )
                continue
            summary = summarize_price_group(platform_group, prefix)
            row.update(summary)
            platform_min = summary.get(f"{prefix}_min_price")
            if ug_min is not None and platform_min is not None:
                row[f"{prefix}_vs_ug_delta"] = float(platform_min) - float(ug_min)
                row[f"{prefix}_vs_ug_delta_pct"] = row[f"{prefix}_vs_ug_delta"] / float(ug_min) if ug_min else None
            else:
                row[f"{prefix}_vs_ug_delta"] = None
                row[f"{prefix}_vs_ug_delta_pct"] = None
        rows.append(row)

    columns = [
        "cpu",
        "ram",
        "storage",
        "duration",
        "ugphone_product_models",
        "ugphone_min_price",
        "ugphone_price_range",
        "ugphone_server_regions",
        "ugphone_promotion_text",
        "ugphone_rows",
    ]
    for platform in competitor_platforms:
        prefix = platform.lower()
        columns.extend(
            [
                f"{prefix}_product_models",
                f"{prefix}_min_price",
                f"{prefix}_price_range",
                f"{prefix}_server_regions",
                f"{prefix}_promotion_text",
                f"{prefix}_rows",
                f"{prefix}_vs_ug_delta",
                f"{prefix}_vs_ug_delta_pct",
            ]
        )
    return pd.DataFrame(rows, columns=columns)


def build_summary(comparison: pd.DataFrame, baseline: pd.DataFrame, platforms: Iterable[str]) -> pd.DataFrame:
    rows = []
    for platform in platforms:
        subset = comparison[comparison["platform"] == platform] if not comparison.empty else pd.DataFrame()
        baseline_count = int((baseline["platform"] == platform).sum()) if not baseline.empty else 0
        matched_count = int((subset["current_rows"] > 0).sum()) if not subset.empty else 0
        statuses = subset["monitor_status"].astype(str) if not subset.empty else pd.Series(dtype=str)
        row = {
            "platform": platform,
            "baseline_products": baseline_count,
            "matched_current_products": matched_count,
        }
        for status in SUMMARY_COLUMNS[3:]:
            row[status] = int(statuses.str.contains(status, regex=False).sum()) if not statuses.empty else 0
        rows.append(row)
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def build_alerts(comparison: pd.DataFrame) -> pd.DataFrame:
    if comparison.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)
    alerts = comparison[comparison["monitor_status"] != "unchanged"].copy()
    if alerts.empty:
        return alerts

    priority_order = [
        ("price_down", 0),
        ("promotion_keyword", 1),
        ("price_up", 2),
        ("current_price_missing", 3),
        ("baseline_price_missing", 4),
    ]

    def priority(status: str) -> int:
        for token, score in priority_order:
            if token in status:
                return score
        return 99

    alerts["_priority"] = alerts["monitor_status"].astype(str).map(priority)
    alerts = alerts.sort_values(["_priority", "platform", "product_model", "device_model", "android_version", "duration"])
    return alerts.drop(columns=["_priority"])


def write_daily_changes_workbook(
    path: Path,
    summary: pd.DataFrame,
    alerts: pd.DataFrame,
    ug_config_comparison: pd.DataFrame,
    ug_near_config_comparison: pd.DataFrame | None = None,
) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        to_chinese_columns(summary, REPORT_HEADER_CN).to_excel(writer, sheet_name=REPORT_SHEETS_CN["summary"], index=False)
        to_chinese_columns(alerts, REPORT_HEADER_CN).to_excel(writer, sheet_name=REPORT_SHEETS_CN["changes"], index=False)
        to_chinese_columns(ug_config_comparison, CONFIG_PRICE_HEADER_CN).to_excel(
            writer,
            sheet_name=REPORT_SHEETS_CN["ug_config_prices"],
            index=False,
        )
        if ug_near_config_comparison is not None:
            to_chinese_columns(ug_near_config_comparison, QUALITY_HEADER_CN).to_excel(
                writer,
                sheet_name=REPORT_SHEETS_CN["ug_near_config_prices"],
                index=False,
            )


def write_alerts_json(path: Path, alerts: pd.DataFrame) -> None:
    records = alerts.where(pd.notna(alerts), None).to_dict(orient="records") if not alerts.empty else []
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def format_price(currency: str, value) -> str:
    number = clean_number(value)
    if number is None:
        return "无价格"
    return f"{currency or 'US$'}{number:g}"


def write_brief(
    path: Path,
    baseline_path: Path,
    comparison: pd.DataFrame,
    summary: pd.DataFrame,
    alerts: pd.DataFrame,
    platforms: Iterable[str],
) -> None:
    lines = [
        "基准价监测简报",
        f"生成时间 UTC: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"本次参考基准: {baseline_path}",
        "口径: 只按基准商品结构匹配机型与购买时长；UgPhone 作为同配置价格参照；新增商品、下架、服务器列表和库存变化不进入报告；活动文案仅在命中促销关键词时提醒。",
        "",
    ]

    if comparison.empty:
        lines.append("本次没有可比较的基准商品记录。")
        path.write_text("\n".join(lines), encoding="utf-8")
        return

    for platform in platforms:
        platform_summary = summary[summary["platform"] == platform]
        platform_alerts = alerts[alerts["platform"] == platform] if not alerts.empty else pd.DataFrame(columns=COMPARISON_COLUMNS)
        lines.append(f"[{platform}]")
        if platform_summary.empty:
            lines.append("- 无记录")
            lines.append("")
            continue
        row = platform_summary.iloc[0]
        lines.append(
            "- 概览: "
            f"基准 {int(row['baseline_products'])} 项，本次匹配 {int(row['matched_current_products'])} 项；"
            f"降价 {int(row['price_down'])}，涨价 {int(row['price_up'])}，"
            f"价格缺失 {int(row['current_price_missing'])}，促销提醒 {int(row['promotion_keyword'])}。"
        )

        drops = platform_alerts[platform_alerts["monitor_status"].astype(str).str.contains("price_down", regex=False)].copy()
        if not drops.empty:
            drops = drops.sort_values("price_delta").head(5)
            lines.append("- 重点降价:")
            for _, item in drops.iterrows():
                android = as_text(item.get("android_version")) or "不区分"
                model = as_text(item.get("device_model")) or "-"
                currency = as_text(item.get("currency")) or "US$"
                pct = item.get("price_delta_pct")
                pct_text = f"{float(pct) * 100:.1f}%" if pct is not None and not missing(pct) else "无百分比"
                lines.append(
                    "  * "
                    f"{as_text(item.get('product_model')) or '-'} / {model} / Android {android} / "
                    f"{as_text(item.get('duration')) or '-'}: "
                    f"{format_price(currency, item.get('baseline_min_price'))} -> "
                    f"{format_price(currency, item.get('current_min_price'))} "
                    f"({format_number(item.get('price_delta'))}, {pct_text})"
                )
        elif not platform_alerts.empty:
            lines.append("- 本次没有降价项，但存在涨价、价格缺失或促销关键词提醒，请看 Excel 的价格变动表。")
        else:
            lines.append("- 未发现相对基准价的变化。")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def write_missing_baseline_outputs(
    output_dir: Path,
    baseline_path: Path,
    current_df: pd.DataFrame,
    ug_near_config_comparison: pd.DataFrame | None = None,
) -> dict:
    daily_changes_path = output_dir / "daily_changes.xlsx"
    summary = pd.DataFrame(
        [
            {
                "status": "baseline_missing",
                "baseline_path": str(baseline_path),
                "current_products": len(summarize_products(current_df)),
                "message": "Create a baseline with --init-baseline or place products.xlsx at the baseline path.",
            }
        ]
    )
    ug_config_comparison = build_ug_config_price_comparison(current_df, [BASE_PLATFORM, "VSPhone", "Redfinger", "LDCloud"])
    with pd.ExcelWriter(daily_changes_path, engine="openpyxl") as writer:
        to_chinese_columns(summary, REPORT_HEADER_CN).to_excel(writer, sheet_name=REPORT_SHEETS_CN["summary"], index=False)
        to_chinese_columns(pd.DataFrame(columns=COMPARISON_COLUMNS), REPORT_HEADER_CN).to_excel(
            writer,
            sheet_name=REPORT_SHEETS_CN["changes"],
            index=False,
        )
        to_chinese_columns(ug_config_comparison, CONFIG_PRICE_HEADER_CN).to_excel(
            writer,
            sheet_name=REPORT_SHEETS_CN["ug_config_prices"],
            index=False,
        )
        if ug_near_config_comparison is not None:
            to_chinese_columns(ug_near_config_comparison, QUALITY_HEADER_CN).to_excel(
                writer,
                sheet_name=REPORT_SHEETS_CN["ug_near_config_prices"],
                index=False,
            )
    return {
        "baseline_found": False,
        "baseline_path": str(baseline_path),
        "daily_changes_path": str(daily_changes_path),
        "current_products": int(summary.iloc[0]["current_products"]),
    }


def build_price_lookup(current_df: pd.DataFrame) -> dict[str, dict[str, object]]:
    current = summarize_products(current_df)
    return {
        row["identity_key"]: {
            "price": row.get("min_price"),
            "currency": as_text(row.get("currency")),
        }
        for _, row in current.iterrows()
    }


def build_current_overlay_lookup(current_df: pd.DataFrame) -> dict[str, dict[str, object]]:
    current = normalize_products(current_df)
    lookup: dict[str, dict[str, object]] = {}
    if current.empty:
        return lookup
    overlay_columns = [
        "source_url",
        "crawl_time_utc",
        "crawl_time_local",
        "supported_server_regions",
        "currency",
        "price",
        "original_price",
        "discount_price",
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
    for key, group in current.groupby("_identity_key", dropna=False, sort=False):
        prices = numeric_prices(group.get("price", []))
        if prices:
            chosen = group.assign(_price_num=group["price"].map(clean_number)).sort_values("_price_num").iloc[0]
        else:
            chosen = group.iloc[0]
        lookup[key] = {col: chosen.get(col) for col in overlay_columns if col in chosen.index}
        lookup[key]["current_rows"] = int(len(group))
    return lookup


def build_baseline_with_current_overlay(baseline_df: pd.DataFrame, current_df: pd.DataFrame) -> pd.DataFrame:
    baseline = normalize_products(baseline_df)
    current = normalize_products(current_df)
    if baseline.empty:
        return current[[col for col in current.columns if not col.startswith("_")]].copy()

    overlay_lookup = build_current_overlay_lookup(current_df)
    rows = []
    seen = set()
    for _, row in baseline.iterrows():
        key = row.get("_identity_key")
        out = {col: row.get(col) for col in row.index if not col.startswith("_")}
        overlay = overlay_lookup.get(key)
        if overlay:
            for col, value in overlay.items():
                if col == "current_rows":
                    continue
                if col in out and not missing(value):
                    out[col] = value
            out["notes"] = append_overlay_note(out.get("notes"), "current_price_overlay_applied")
        else:
            out["notes"] = append_overlay_note(out.get("notes"), "current_missing_used_baseline")
        rows.append(out)
        seen.add(key)

    for _, row in current.iterrows():
        key = row.get("_identity_key")
        if key in seen:
            continue
        out = {col: row.get(col) for col in row.index if not col.startswith("_")}
        out["notes"] = append_overlay_note(out.get("notes"), "new_current_product_not_in_baseline")
        rows.append(out)

    return pd.DataFrame(rows)


def append_overlay_note(existing, note: str) -> str:
    parts = []
    for part in as_text(existing).split(";"):
        item = part.strip()
        if item and item not in parts:
            parts.append(item)
    if note and note not in parts:
        parts.append(note)
    return "; ".join(parts)


def write_updated_baseline_workbook(path: Path, baseline_path: Path, current_df: pd.DataFrame) -> int:
    price_lookup = build_price_lookup(current_df)
    sheets = pd.read_excel(baseline_path, sheet_name=None, dtype=object)
    updated_count = 0
    seen_platforms = set()

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, frame in sheets.items():
            if frame.empty:
                frame.to_excel(writer, sheet_name=sheet_name[:31], index=False)
                continue

            original_columns = list(frame.columns)
            work = normalize_columns(frame.copy())
            if "platform" not in work.columns:
                work["platform"] = infer_platform_from_sheet(sheet_name)
            for col in BASELINE_KEY_COLUMNS:
                if col not in work.columns:
                    work[col] = None
            if "price" not in work.columns:
                to_chinese_columns(work, PRODUCT_HEADER_CN).to_excel(writer, sheet_name=sheet_name[:31], index=False)
                continue

            for idx, row in work.iterrows():
                current = price_lookup.get(identity_key(row))
                if current and current.get("price") is not None:
                    work.at[idx, "price"] = current["price"]
                    updated_count += 1
                    if "currency" in work.columns and current.get("currency"):
                        work.at[idx, "currency"] = current["currency"]

            ordered_columns = [CN_TO_EN.get(col, col) for col in original_columns if CN_TO_EN.get(col, col) in work.columns]
            extra_columns = [col for col in work.columns if col not in ordered_columns and not col.startswith("_")]
            out = work[ordered_columns + extra_columns]
            platform = normalize_platform_name(infer_platform_from_sheet(sheet_name))
            seen_platforms.add(platform)
            sheet_cn = BASELINE_PLATFORM_SHEETS_CN.get(platform, sheet_name)[:31]
            to_chinese_columns(out, PRODUCT_HEADER_CN).to_excel(writer, sheet_name=sheet_cn, index=False)

        current_norm = normalize_products(current_df)
        if BASE_PLATFORM not in seen_platforms and not current_norm.empty:
            ug_rows = current_norm[current_norm["platform"].map(normalize_platform_name) == BASE_PLATFORM].copy()
            if not ug_rows.empty:
                visible_cols = [col for col in ug_rows.columns if not col.startswith("_")]
                to_chinese_columns(ug_rows[visible_cols], PRODUCT_HEADER_CN).to_excel(
                    writer,
                    sheet_name=BASELINE_PLATFORM_SHEETS_CN[BASE_PLATFORM],
                    index=False,
                )

    return updated_count


def write_current_products_workbook(
    path: Path,
    current_df: pd.DataFrame,
    platforms: Iterable[str],
    sheet_names: dict[str, str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    work = normalize_products(current_df)
    visible_cols = [col for col in work.columns if not col.startswith("_")]
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for platform in platforms:
            normalized_platform = normalize_platform_name(platform)
            rows = work[work["platform"].map(normalize_platform_name) == normalized_platform].copy()
            sheet_name = (sheet_names or BASELINE_PLATFORM_SHEETS_CN).get(normalized_platform, normalized_platform)[:31]
            to_chinese_columns(rows[visible_cols], PRODUCT_HEADER_CN).to_excel(writer, sheet_name=sheet_name, index=False)


def write_baseline_monitor_outputs(
    output_dir: Path,
    current_df: pd.DataFrame,
    baseline_path: Path,
    platforms: Iterable[str],
    ug_near_config_comparison: pd.DataFrame | None = None,
) -> dict:
    daily_changes_path = output_dir / "daily_changes.xlsx"
    updated_baseline_path = output_dir / "baseline_products_updated.xlsx"

    if not baseline_path.exists():
        return write_missing_baseline_outputs(output_dir, baseline_path, current_df, ug_near_config_comparison)

    baseline_df = load_products_table(baseline_path)
    current_norm = normalize_products(current_df)
    baseline_platforms = {normalize_platform_name(value) for value in baseline_df.get("platform", [])} if not baseline_df.empty else set()
    if not baseline_df.empty and BASE_PLATFORM not in baseline_platforms:
        ug_rows = current_norm[current_norm["platform"].map(normalize_platform_name) == BASE_PLATFORM].copy()
        if not ug_rows.empty:
            baseline_df = pd.concat(
                [baseline_df, ug_rows[[col for col in ug_rows.columns if not col.startswith("_")]]],
                ignore_index=True,
            )
    comparison, summary, alerts = compare_products(current_df, baseline_df, platforms)
    ug_config_comparison = build_ug_config_price_comparison(current_df, platforms)
    write_daily_changes_workbook(daily_changes_path, summary, alerts, ug_config_comparison, ug_near_config_comparison)
    updated_count = write_updated_baseline_workbook(updated_baseline_path, baseline_path, current_df)
    return {
        "baseline_found": True,
        "baseline_path": str(baseline_path),
        "updated_baseline_path": str(updated_baseline_path),
        "updated_baseline_price_rows": updated_count,
        "daily_changes_path": str(daily_changes_path),
        "comparison_rows": int(len(comparison)),
        "alert_rows": int(len(alerts)),
        "ug_config_comparison_rows": int(len(ug_config_comparison)),
        "price_down_rows": int(comparison["monitor_status"].astype(str).str.contains("price_down", regex=False).sum())
        if not comparison.empty
        else 0,
    }


def initialize_baseline(current_products_xlsx: Path, baseline_path: Path) -> None:
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(current_products_xlsx, baseline_path)
