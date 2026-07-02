from __future__ import annotations

import json
import math
import re
import shutil
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


SAFE_OUTPUT_FILES = [
    "products.csv",
    "products.xlsx",
    "products.jsonl",
    "daily_changes.xlsx",
    "baseline_products_updated.xlsx",
    "quality_price_report.xlsx",
    "run_summary.json",
]

DASHBOARD_JSON_FILES = [
    "frontend_price_overview.json",
    "pairing_matrix.json",
    "duration_price_comparison.json",
    "price_trends.json",
    "price_change_tracking.json",
    "product_text_changes.json",
    "metric_definitions.json",
    "schedule_status.json",
    "meta.json",
]

PRICE_TRENDS_CHUNK_DIR = "price_trends_chunks"
# Keep every generated dashboard JSON safely below GitHub's hard 100MB single-file limit.
# This threshold is intentionally conservative because the final write_json uses
# pretty printed JSON, which is larger than the compact size used for chunking.
PRICE_TRENDS_DETAIL_CHUNK_TARGET_BYTES = 5 * 1024 * 1024


SCHEDULER_CONFIG_PATH = Path("output") / "scheduler_logs" / "schedule_status.json"

BASE_PLATFORM = "UgPhone"
LEGACY_BASE_PLATFORM = "UG" + "Phone"
COMPETITOR_PLATFORMS = ["VSPhone", "Redfinger", "LDCloud"]
FRONTEND_CORE_BUCKETS = [1, 3, 7, 15, 30, 60, 90, 180, 365]
# Platform-specific duration mapping for decision-facing comparison buckets.
# LDCloud has no true 7-day SKU in the monitored data, so its 8-day SKU is
# compared in the 7-day bucket while retaining actual duration fields.
PLATFORM_DURATION_BUCKET_OVERRIDES = {
    ("LDCloud", 8): 7,
}
DURATION_BUCKET_NOTES = {
    "7": "LDCloud 没有7天购买时限；7天档比较中，LDCloud 使用8天套餐价格参与对比。",
}
ALL_PLATFORMS = [BASE_PLATFORM, "VSPhone", "Redfinger", "LDCloud"]
PLATFORM_COLORS = {
    "UgPhone": "#dc2626",
    "VSPhone": "#111827",
    "Redfinger": "#2563eb",
    "LDCloud": "#eab308",
}
ALERT_RANK = {"critical": 0, "warning": 1, "info": 2, "none": 3, "": 4}
POSITION_RANK = {"high": 0, "slightly_high": 1, "competitive": 2, "below_market": 3, "unknown": 4}

QUALITY_COLS = {
    "UG套餐型号": "ug_product_model",
    "UG配置": "ug_config",
    "UG购买天数": "duration_days",
    "UG设备数": "ug_device_count",
    "UG 30天等效实付价": "ug_effective_price_30d",
    "UG 30天等效原价": "ug_list_price_30d",
    "UG折扣率": "ug_discount_rate",
    "UG价格口径": "ug_price_basis",
    "竞品平台": "competitor_platform",
    "竞品套餐型号": "competitor_product_model",
    "竞品配置": "competitor_config",
    "竞品购买天数": "competitor_duration_days",
    "竞品设备数": "competitor_device_count",
    "竞品30天等效实付价": "competitor_effective_price_30d",
    "竞品30天等效原价": "competitor_list_price_30d",
    "竞品折扣率": "competitor_discount_rate",
    "竞品价格口径": "competitor_price_basis",
    "配置相似度分": "config_similarity_score",
    "质量调整系数": "quality_adjustment_factor",
    "质量调整后30天价": "quality_adjusted_price_30d",
    "调整后价差": "adjusted_delta",
    "调整后价差比例": "adjusted_delta_pct",
    "可比性等级": "comparability_level",
    "配对来源": "pairing_source",
    "活动文案": "promotion_text",
    "支持服务器地区": "supported_server_regions",
    "备注": "notes",
}

RELATIVE_COLS = {
    "UG套餐型号": "ug_product_model",
    "UG配置": "ug_config",
    "UG购买天数": "duration_days",
    "UG 30天等效实付价": "ug_effective_price_30d",
    "竞品质量调整价中位数": "competitor_median_quality_adjusted_price_30d",
    "核心可比竞品数": "core_match_rows",
    "弱可比竞品数": "weak_match_rows",
    "弱可比竞品中位数": "weak_median_quality_adjusted_price_30d",
    "UG相对竞品指数": "ugphone_relative_index",
    "价格位置标签": "market_position_label",
    "提醒等级": "alert_level",
    "原因标签": "reason_code",
    "备注": "notes",
}

PAIRING_COLS = {
    "UG平台": "ug_platform",
    "UG套餐型号": "ug_product_model",
    "UG设备型号": "ug_device_model",
    "UG安卓版本": "ug_android_version",
    "UG CPU": "ug_cpu",
    "UG内存": "ug_ram",
    "UG存储": "ug_storage",
    "UG购买时长": "ug_duration",
    "竞品平台": "competitor_platform",
    "竞品套餐型号": "competitor_product_model",
    "竞品设备型号": "competitor_device_model",
    "竞品安卓版本": "competitor_android_version",
    "竞品CPU": "competitor_cpu",
    "竞品内存": "competitor_ram",
    "竞品存储": "competitor_storage",
    "竞品购买时长": "competitor_duration",
    "配置相似度分": "config_similarity_score",
    "可比性等级": "comparability_level",
    "配对来源": "pairing_source",
    "配对备注": "pairing_notes",
}

RATIONALITY_COLS = {
    "平台": "platform",
    "套餐型号": "product_model",
    "设备型号": "device_model",
    "安卓版本": "android_version",
    "CPU": "cpu",
    "内存": "ram",
    "存储": "storage",
    "购买天数": "duration_days",
    "基准30天等效实付价": "baseline_effective_price_30d",
    "本次30天等效实付价": "current_effective_price_30d",
    "自身价格指数": "own_price_index",
    "基准30天等效原价": "baseline_list_price_30d",
    "本次30天等效原价": "current_list_price_30d",
    "原价指数": "list_price_index",
    "基准折扣率": "baseline_discount_rate",
    "本次折扣率": "current_discount_rate",
    "折扣率变化": "discount_rate_change",
    "基准活动文案": "baseline_promotion_text",
    "本次活动文案": "current_promotion_text",
    "基准服务器地区": "baseline_supported_server_regions",
    "本次服务器地区": "current_supported_server_regions",
    "原因标签": "reason_code",
    "提醒等级": "alert_level",
    "备注": "notes",
}

PRODUCT_COLS = {
    "平台": "platform",
    "币种": "currency",
    "套餐型号": "product_model",
    "设备型号": "device_model",
    "安卓版本": "android_version",
    "CPU": "cpu",
    "内存": "ram",
    "存储": "storage",
    "价格": "price",
    "原价": "original_price",
    "购买时长": "duration",
    "库存状态": "stock_status",
    "活动文案": "promotion_text",
}

REASON_EXPLANATIONS = {
    "promo_change": "主要由活动价或促销文案变化导致。",
    "list_price_change": "官方原价发生变化。",
    "competitor_following": "UgPhone 与竞品中位价同方向变化。",
    "config_change": "配置变化导致价格不可直接比较。",
    "region_supply_change": "地区或服务器覆盖发生变化。",
    "duration_structure_change": "购买时长结构发生变化。",
    "stock_status_change": "库存状态发生变化。",
    "abnormal_unexplained": "无法由已知因素解释，需要人工复核。",
    "unchanged": "无明显变化。",
}

REASON_EXPLANATIONS_EN = {
    "promo_change": "The change is mainly caused by promotion copy or promotional price changes.",
    "list_price_change": "The official list price changed.",
    "competitor_following": "UgPhone moved in the same direction as the competitor median.",
    "config_change": "The product configuration changed, so prices are not directly comparable.",
    "region_supply_change": "Server region coverage changed.",
    "duration_structure_change": "The available duration structure changed.",
    "stock_status_change": "Stock status changed.",
    "abnormal_unexplained": "The change is not explained by known factors and needs manual review.",
    "unchanged": "No meaningful change detected.",
}

FRONTEND_REASON_EXPLANATIONS = {
    "price_unchanged": "现价无明显变化。",
    "price_up": "当前成交价高于上一次或 baseline 价格。",
    "price_down": "当前成交价低于上一次或 baseline 价格。",
    "promotion_text_changed": "商品或活动文案发生变化，需结合商品文本判断是否为活动。",
    "duration_missing_current_used_baseline": "今日该购买天数缺失，后台沿用 baseline 结构。",
    "product_missing_after_login": "确认登录后仍缺失该商品，需要内部排查。",
    "short_duration_excluded": "短周期或小时包不进入前台核心分档比较。",
    "abnormal_price_change": "现价变化超过阈值，且没有明显文案变化。",
    "baseline_structure_mismatch": "今日数据无法匹配 baseline 产品结构。",
}

METRIC_DEFINITIONS = [
    {
        "name_zh": "当前成交价",
        "field": "current_price",
        "meaning": "当前采集到的实际成交价格。",
        "source": "products.xlsx / quality_price_report.xlsx 的当前价格字段。",
        "calculation": "同购买天数下直接使用成交价；不会使用划线原价。",
        "interpretation": "用于判断用户真实需要支付的价格。",
        "pitfall": "不要把页面上的原价或划线价当成成交价。",
    },
    {
        "name_zh": "上次价格",
        "field": "previous_price",
        "meaning": "上一次成功采集的同商品同天数成交价。",
        "source": "历史采集或 baseline；历史不足时使用可用基准价并记录样本不足。",
        "calculation": "按 baseline key 匹配平台、配置和核心购买天数。",
        "interpretation": "用于判断本次现价相对上次是否上涨或下降。",
        "pitfall": "历史不足时不要过度解读趋势。",
    },
    {
        "name_zh": "Baseline 价格",
        "field": "baseline_price",
        "meaning": "已确认产品结构中的基准成交价。",
        "source": "baseline_products_updated.xlsx 或质量报告中的 baseline 对比。",
        "calculation": "严格按 baseline 产品结构和购买天数匹配。",
        "interpretation": "用于维持前台展示结构稳定。",
        "pitfall": "当天抓到但无法匹配 baseline 的临时商品不进入前台。",
    },
    {
        "name_zh": "价格变化比例",
        "field": "price_change_pct",
        "meaning": "当前价相对上次价的变化比例。",
        "source": "current_price 与 previous_price。",
        "calculation": "(current_price - previous_price) / previous_price。",
        "interpretation": "正数表示涨价，负数表示降价。",
        "pitfall": "previous_price 缺失时不计算。",
    },
    {
        "name_zh": "7日均价",
        "field": "seven_day_avg_price",
        "meaning": "最近 7 天同商品同天数成交价均值。",
        "source": "历史输出；历史不足时标记样本数。",
        "calculation": "sum(price) / sample_count。",
        "interpretation": "用于平滑单日价格波动。",
        "pitfall": "样本数不足 7 时只能辅助参考。",
    },
    {
        "name_zh": "30日均价",
        "field": "thirty_day_avg_price",
        "meaning": "最近 30 天同商品同天数成交价均值。",
        "source": "历史输出；历史不足时标记样本数。",
        "calculation": "sum(price) / sample_count。",
        "interpretation": "用于判断中期价格水平。",
        "pitfall": "样本不足 30 时不要当作完整月度均价。",
    },
    {
        "name_zh": "配置相似度",
        "field": "config_similarity_score",
        "meaning": "UgPhone 配置与竞品配置的相似度分数。",
        "source": "quality_price_report.xlsx 配置配对建议。",
        "calculation": "综合 Android、CPU、内存、存储、服务器地区和购买天数。",
        "interpretation": "分数越高越适合进入价格比较。",
        "pitfall": "套餐名不是主要匹配依据。",
    },
    {
        "name_zh": "竞品中位价",
        "field": "competitor_median_price",
        "meaning": "同购买天数下 strong_match / adjusted_match 竞品当前价格中位数。",
        "source": "duration_price_comparison.json。",
        "calculation": "只取核心可比竞品价格的中位数。",
        "interpretation": "用于判断 UgPhone 是否高于或低于竞品。",
        "pitfall": "weak_match 不进入核心中位数。",
    },
    {
        "name_zh": "UgPhone 相对竞品指数",
        "field": "ugphone_relative_index",
        "meaning": "UgPhone 当前价相对竞品中位价的指数。",
        "source": "UgPhone 当前价与竞品中位价。",
        "calculation": "UgPhone 当前价 / 竞品中位价 × 100。",
        "interpretation": "小于 90 偏低，90-105 有竞争力，105-115 略高，大于 115 明显偏高。",
        "pitfall": "这里按同购买天数比较，不默认使用 30 天等效价。",
    },
    {
        "name_zh": "商品文本变化",
        "field": "promotion_text_changed",
        "meaning": "商品或活动文案是否相对上次发生变化。",
        "source": "promotion_text / raw_text。",
        "calculation": "当前文本与上次文本比较。",
        "interpretation": "用于人工判断是否出现秒杀、促销、限时、组合包。",
        "pitfall": "不要用原价或折扣率推断活动。",
    },
    {
        "name_zh": "价格来源",
        "field": "price_source",
        "meaning": "说明趋势点使用的是当天采集、上一轮价格、baseline 补齐还是缺失。",
        "source": "price_trends.json / price_change_tracking.json。",
        "calculation": "current 表示当天真实采集；previous 表示上一轮；baseline_fallback 表示当天缺失但 baseline 有价；missing 表示当前与 baseline 都没有价格。",
        "interpretation": "看到 baseline_fallback 时，趋势线保持不断，但该点不是当天新抓到的真实价格。",
        "pitfall": "不要把 baseline_fallback 当作当天价格已经确认未变化。",
    },
    {
        "name_zh": "购买天数分档",
        "field": "duration_bucket",
        "meaning": "把购买周期归入 1/3/7/15/30/60/90/180/365 或 other。",
        "source": "duration 字段解析结果。",
        "calculation": "只有完全等于 7、30、90、180、365 天的记录进入核心分档，其余小时包、45天、120天等进入 other。",
        "interpretation": "前台默认只比较核心购买天数，避免把短周期活动包误当作月价。",
        "pitfall": "不要把 4小时、3天、45天强行折算进 7天或30天核心比较。",
    },
    {
        "name_zh": "配对等级",
        "field": "comparability_level",
        "meaning": "说明竞品配置与 UgPhone 基准配置是否可比。",
        "source": "配置相似度评分和手工推荐配对。",
        "calculation": "strong_match、adjusted_match 进入核心竞品中位数；weak_match 只辅助观察；not_comparable 不进入价格判断。",
        "interpretation": "价格比较优先看 strong_match 和 adjusted_match。",
        "pitfall": "weak_match 或 not_comparable 的低价不能直接证明 UgPhone 偏贵。",
    },
]


def normalize_platform_name(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() == "ugphone":
        return BASE_PLATFORM
    return text


def normalize_display_text(value: Any) -> str:
    return str(value).replace(LEGACY_BASE_PLATFORM, BASE_PLATFORM)


def json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, 6)
    if isinstance(value, str):
        return normalize_display_text(value)
    if isinstance(value, (int, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    # pandas/numpy scalar values are not JSON serializable by default.
    # Returning them unchanged from json.default can trigger "Circular reference detected".
    if hasattr(value, "item") and not isinstance(value, (dict, list, tuple, set)):
        try:
            return json_safe(value.item())
        except Exception:
            pass
    if pd.isna(value):
        return None
    return value


def records_from_df(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    clean = df.where(pd.notna(df), None)
    return [{key: json_safe(value) for key, value in row.items()} for row in clean.to_dict(orient="records")]


def normalize_json_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {normalize_display_text(key): normalize_json_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_json_payload(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_json_payload(item) for item in value]
    return json_safe(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalize_json_payload(payload), ensure_ascii=False, indent=2, default=json_safe), encoding="utf-8")


def estimate_compact_json_size(value: Any) -> int:
    """Approximate UTF-8 JSON size for chunk planning."""
    try:
        return len(json.dumps(normalize_json_payload(value), ensure_ascii=False, separators=(",", ":"), default=json_safe).encode("utf-8"))
    except Exception:
        return len(str(value).encode("utf-8", errors="ignore"))


def split_price_trends_detail_payloads(trends_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Move heavy region/Android detail data out of price_trends.json.

    The default merged trend data stays in price_trends.json so historical trend
    charts keep working and old correct merged data is preserved.  Heavy details
    required only for user-triggered views are written into small chunk files:

    - regional_points: product line × machine room history
    - android_breakdown_series: product line × Android version, including
      Android × machine-room histories

    This prevents docs/dashboard_data/price_trends.json from exceeding GitHub's
    100MB single-file limit while keeping all historical detail available.
    """
    payload = dict(trends_payload or {})
    series = [dict(item) for item in stable_list(payload.get("series")) if isinstance(item, dict)]
    if not series:
        payload["split_detail_mode"] = False
        return payload, {}

    detail_entries: list[dict[str, Any]] = []
    light_series: list[dict[str, Any]] = []
    for index, item in enumerate(series):
        series_id = normalize_display_text(item.get("series_id") or f"trend_series_{index}")
        item["series_id"] = series_id
        detail: dict[str, Any] = {"series_id": series_id}

        regional_points = item.pop("regional_points", None)
        android_children = item.pop("android_breakdown_series", None)

        if isinstance(regional_points, dict) and regional_points:
            detail["regional_points"] = regional_points
        if stable_list(android_children):
            detail["android_breakdown_series"] = stable_list(android_children)

        item["has_regional_points"] = bool(detail.get("regional_points"))
        item["has_android_breakdown"] = bool(detail.get("android_breakdown_series"))
        item["android_breakdown_series_count"] = len(stable_list(detail.get("android_breakdown_series")))
        if detail.get("regional_points") or detail.get("android_breakdown_series"):
            detail_entries.append(detail)
        light_series.append(item)

    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_size = 0
    for entry in detail_entries:
        entry_size = estimate_compact_json_size(entry)
        if current and current_size + entry_size > PRICE_TRENDS_DETAIL_CHUNK_TARGET_BYTES:
            chunks.append(current)
            current = []
            current_size = 0
        current.append(entry)
        current_size += entry_size
    if current:
        chunks.append(current)

    detail_index: dict[str, str] = {}
    detail_files: list[str] = []
    chunk_payloads: dict[str, Any] = {}
    for chunk_index, entries in enumerate(chunks, start=1):
        filename = f"{PRICE_TRENDS_CHUNK_DIR}/price_trends_detail_{chunk_index:04d}.json"
        detail_files.append(filename)
        for entry in entries:
            detail_index[str(entry.get("series_id") or "")] = filename
        chunk_payloads[filename] = {
            "type": "price_trends_detail_chunk",
            "chunk_index": chunk_index,
            "chunk_count": len(chunks),
            "entry_count": len(entries),
            "entries": entries,
        }

    for item in light_series:
        chunk_file = detail_index.get(str(item.get("series_id") or ""))
        if chunk_file:
            item["trend_detail_chunk"] = chunk_file

    payload["series"] = light_series
    payload["split_detail_mode"] = bool(detail_files)
    payload["trend_detail_chunk_count"] = len(detail_files)
    payload["trend_detail_files"] = detail_files
    payload["trend_detail_rule"] = "price_trends.json keeps merged historical series; machine-room and Android-version detail histories are stored in price_trends_chunks/*.json and loaded by the frontend only for the current view."
    return payload, chunk_payloads


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def next_weekday_run(now_local: datetime, run_time: time) -> datetime:
    candidate = now_local.replace(hour=run_time.hour, minute=run_time.minute, second=0, microsecond=0)
    if candidate <= now_local:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def data_freshness(last_run_time: datetime | None, now: datetime, stale_after_hours: int = 30) -> str:
    if last_run_time is None:
        return "unknown"
    age_hours = (now - last_run_time.astimezone(timezone.utc)).total_seconds() / 3600
    if age_hours > 48:
        return "outdated"
    if age_hours > stale_after_hours:
        return "stale"
    return "fresh"


def read_excel_sheet(path: Path, sheet_name: str, columns: dict[str, str] | None = None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        frame = pd.read_excel(path, sheet_name=sheet_name, dtype=object)
    except Exception:
        return pd.DataFrame()
    frame = frame.dropna(how="all")
    if columns:
        frame = frame.rename(columns={old: new for old, new in columns.items() if old in frame.columns})
    return frame


def parse_ug_config(ug_config: str) -> dict[str, Any]:
    parts = [part.strip() for part in str(ug_config or "").split("/") if part.strip()]
    android = ""
    cpu = ""
    ram = ""
    storage = ""
    if len(parts) > 1:
        android = parts[1].replace("Android", "").strip()
    if len(parts) > 2:
        cpu = parts[2]
    if len(parts) > 3:
        ram = parts[3]
    if len(parts) > 4:
        storage = parts[4]
    return {
        "ug_android_version": android,
        "ug_cpu": cpu,
        "ug_ram": ram,
        "ug_storage": storage,
    }


def parse_duration_days(value: Any) -> float | None:
    return parse_duration_info(value)["duration_days"]


def _format_duration_number(value: float) -> str:
    return f"{int(value) if float(value).is_integer() else value:g}"


def _duration_bucket_from_days(days: float | None) -> tuple[Any, bool]:
    if days is None:
        return "unknown", False
    try:
        numeric = float(days)
    except Exception:
        return "unknown", False
    if not math.isfinite(numeric):
        return "unknown", False
    nearest = int(round(numeric))
    if abs(numeric - nearest) < 1e-9 and nearest in FRONTEND_CORE_BUCKETS:
        return nearest, True
    return "other", False


def parse_duration_info(value: Any) -> dict[str, Any]:
    """Parse a purchase duration and map it to a frontend bucket.

    The collector may emit durations as English text ("3 days"), Chinese text
    ("15天" / "15日"), or sometimes as a bare numeric day count from Excel/JSON
    fields.  Bare mixed marketing text such as "Get 2 Devices" must not be
    treated as a duration, but a numeric cell like 15 should be accepted as 15
    days.
    """
    raw_value = value
    text = str(value or "").strip()
    lower = text.lower()
    failed = {
        "duration_days": None,
        "duration_display": text,
        "duration_bucket": "unknown",
        "duration_bucket_label": "未知",
        "is_core_duration_bucket": False,
        "duration_parse_status": "failed",
        "exclude_from_core_price_comparison": True,
        "exclusion_reason": "duration_parse_failed",
    }
    if raw_value is None or (isinstance(raw_value, float) and math.isnan(raw_value)) or not lower:
        return {**failed, "duration_display": ""}

    number: float | None = None
    unit = "day"

    # Excel/JSON may carry duration_days as a numeric scalar.  Treat numeric-only
    # values as day counts, but do not infer a duration from arbitrary text that
    # merely contains a number.
    if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
        number = float(raw_value)
        unit = "day"
    elif re.fullmatch(r"\d+(?:\.\d+)?", lower):
        number = float(lower)
        unit = "day"
    else:
        match = re.search(r"(?<![\d.])(\d+(?:\.\d+)?)\s*[- ]?\s*(hours?|hrs?|小时|h|days?|天|日|weeks?|周|months?|月|years?|年)(?=$|\s|[^a-z])", lower)
        if not match:
            return failed
        number = float(match.group(1))
        unit = match.group(2)

    if unit in {"hour", "hours", "hr", "hrs", "小时", "h"}:
        days = number / 24
        display = f"{_format_duration_number(number)}小时"
        exclusion = "short_duration_not_core_bucket"
    elif unit in {"day", "days", "天", "日"}:
        days = number
        display = f"{_format_duration_number(number)}天"
        exclusion = "non_core_duration_bucket"
    elif unit in {"week", "weeks", "周"}:
        days = number * 7
        display = f"{_format_duration_number(days)}天"
        exclusion = "non_core_duration_bucket"
    elif unit in {"month", "months", "月"}:
        days = number * 30
        display = f"{_format_duration_number(days)}天"
        exclusion = "non_core_duration_bucket"
    else:
        days = number * 365
        display = f"{_format_duration_number(days)}天"
        exclusion = "non_core_duration_bucket"

    bucket, is_core = _duration_bucket_from_days(days)
    return {
        "duration_days": json_safe(days),
        "duration_display": display,
        "duration_bucket": bucket,
        "duration_bucket_label": f"{bucket}天" if is_core else "其他",
        "is_core_duration_bucket": is_core,
        "duration_parse_status": "success",
        "exclude_from_core_price_comparison": not is_core,
        "exclusion_reason": "" if is_core else exclusion,
    }


def canonical_duration_info_from_fields(*values: Any) -> dict[str, Any] | None:
    """Return the first core duration parsed from known row fields.

    This is used to migrate stale historical JSON that may still have
    duration_bucket="other" even though duration_display/actual_duration_days is
    now a core bucket such as 3天、15天 or 60天.
    """
    for value in values:
        if value in {None, "", "unknown", "other", "其他"}:
            continue
        info = parse_duration_info(value)
        if info.get("is_core_duration_bucket"):
            return info
    return None


def migrate_duration_bucket_fields(row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        return row
    info = canonical_duration_info_from_fields(
        row.get("actual_duration_days"),
        row.get("duration_days"),
        row.get("actual_duration_display"),
        row.get("duration_display"),
        f"{row.get('duration_bucket')} day" if str(row.get("duration_bucket") or "").isdigit() else None,
    )
    if not info:
        return row
    migrated = dict(row)
    old_bucket = migrated.get("duration_bucket")
    migrated["duration_bucket"] = info.get("duration_bucket")
    migrated["duration_bucket_label"] = info.get("duration_bucket_label")
    migrated["duration_display"] = migrated.get("duration_display") or info.get("duration_display")
    migrated["actual_duration_days"] = migrated.get("actual_duration_days") if migrated.get("actual_duration_days") is not None else info.get("duration_days")
    migrated["actual_duration_display"] = migrated.get("actual_duration_display") or info.get("duration_display")
    if str(old_bucket) != str(info.get("duration_bucket")):
        migrated["migrated_duration_bucket"] = json_safe(old_bucket)
    return migrated


def normalize_comparison_duration_info(platform: Any, value: Any) -> dict[str, Any]:
    """Parse duration and apply platform-specific comparison buckets.

    LDCloud has no true 7-day SKU in the monitored data.  Its 8-day SKU is
    placed into the 7-day decision bucket, but the actual 8-day duration is
    preserved for display/audit fields.
    """
    info = parse_duration_info(value)
    platform_name = normalize_platform_name(platform)
    actual_days = info.get("duration_days")
    info["actual_duration_days"] = json_safe(actual_days)
    info["actual_duration_display"] = info.get("duration_display")
    info["comparison_duration_note"] = ""
    try:
        actual_int = int(float(actual_days)) if actual_days is not None and float(actual_days).is_integer() else None
    except Exception:
        actual_int = None
    override_bucket = PLATFORM_DURATION_BUCKET_OVERRIDES.get((platform_name, actual_int)) if actual_int is not None else None
    if override_bucket:
        info["duration_bucket"] = override_bucket
        info["duration_bucket_label"] = f"{override_bucket}天"
        info["is_core_duration_bucket"] = True
        info["exclude_from_core_price_comparison"] = False
        info["exclusion_reason"] = ""
        info["duration_display"] = f"{actual_int}天（按{override_bucket}天档比较）"
        info["comparison_duration_note"] = f"{platform_name}没有{override_bucket}天购买时限；使用{actual_int}天套餐参与{override_bucket}天档比较。"
    return info


def ug_config_id(ug_config: str, duration_days: Any) -> str:
    safe = str(ug_config or "unknown").lower()
    safe = "".join(ch if ch.isalnum() else "_" for ch in safe).strip("_")
    duration = json_safe(duration_days)
    if isinstance(duration, float) and duration.is_integer():
        duration = int(duration)
    return f"{safe}__{duration or 'unknown'}d"


def enrich_ids(details: pd.DataFrame, pairings: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not details.empty:
        details = details.copy()
        details["ug_config_id"] = details.apply(lambda row: ug_config_id(row.get("ug_config"), row.get("duration_days")), axis=1)
    if not pairings.empty:
        pairings = pairings.copy()
        pairings["ug_config"] = pairings.apply(
            lambda row: (
                f"{row.get('ug_product_model') or '-'} / Android {row.get('ug_android_version') or '-'} / "
                f"{row.get('ug_cpu') or '-'} / {row.get('ug_ram') or '-'} / {row.get('ug_storage') or '-'}"
            ),
            axis=1,
        )
        pairings["duration_days"] = pairings["ug_duration"].map(parse_duration_days)
        pairings["ug_config_id"] = pairings.apply(lambda row: ug_config_id(row.get("ug_config"), row.get("duration_days")), axis=1)
    return details, pairings


def market_position_label(index_value: Any) -> str:
    if index_value is None or pd.isna(index_value):
        return "unknown"
    value = float(index_value)
    if value < 90:
        return "below_market"
    if value <= 105:
        return "competitive"
    if value <= 115:
        return "slightly_high"
    return "high"


def recommendation_for(position: str, reason_code: str, confidence_level: str) -> str:
    if "abnormal_unexplained" in str(reason_code or ""):
        return "必须人工复核。"
    if position == "high" and confidence_level in {"low", "insufficient"}:
        return "不直接调价，先检查配对质量和数据缺失。"
    if position == "below_market":
        return "可保持价格，观察是否有提价空间。"
    if position == "competitive":
        return "价格健康，保持监测。"
    if position == "slightly_high":
        return "略高，检查活动价和竞品促销。"
    if position == "high":
        return "需要复盘定价或促销策略。"
    return "数据不足，先补充竞品覆盖。"


def confidence(core_platforms: set[str], weak_platforms: set[str], fallback_used: bool) -> tuple[float, str, str]:
    core_count = len(core_platforms)
    weak_count = len(weak_platforms)
    score = core_count / len(COMPETITOR_PLATFORMS) * 100
    notes = []
    if fallback_used:
        notes.append("baseline fallback used")
    if core_count >= 2 and not fallback_used:
        return score, "high", "; ".join(notes) or "two or more core competitor platforms"
    if core_count >= 2:
        return score, "medium", "; ".join(notes) or "two or more core competitors with fallback context"
    if core_count == 1:
        return score, "medium", "; ".join(notes) or "one core competitor platform"
    if weak_count > 0:
        return score, "low", "; ".join(notes) or "weak matches only"
    return score, "insufficient", "; ".join(notes) or "no usable competitor basket"


def build_competitor_basket(details: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    if details.empty:
        return rows
    for (ug_config, duration_days), group in details.groupby(["ug_config", "duration_days"], dropna=False, sort=False):
        config_id = ug_config_id(ug_config, duration_days)
        present_platforms = set()
        for _, row in group.iterrows():
            platform = row.get("competitor_platform")
            present_platforms.add(platform)
            level = row.get("comparability_level")
            adjusted = row.get("quality_adjusted_price_30d")
            included = level in {"strong_match", "adjusted_match"} and not pd.isna(adjusted)
            if included:
                exclusion = ""
            elif level == "weak_match":
                exclusion = "weak_match_not_in_core_median"
            elif level == "not_comparable":
                exclusion = "not_comparable"
            else:
                exclusion = "missing_quality_adjusted_price"
            rows.append(
                {
                    "ug_config_id": config_id,
                    "ug_config": ug_config,
                    "duration_days": json_safe(duration_days),
                    "competitor_platform": platform,
                    "competitor_product_model": json_safe(row.get("competitor_product_model")),
                    "competitor_config": json_safe(row.get("competitor_config")),
                    "raw_effective_price_30d": json_safe(row.get("competitor_effective_price_30d")),
                    "quality_adjustment_factor": json_safe(row.get("quality_adjustment_factor")),
                    "quality_adjusted_price_30d": json_safe(row.get("quality_adjusted_price_30d")),
                    "config_similarity_score": json_safe(row.get("config_similarity_score")),
                    "comparability_level": json_safe(level),
                    "included_in_core_median": included,
                    "exclusion_reason": exclusion,
                    "pairing_source": json_safe(row.get("pairing_source")),
                    "pairing_notes": json_safe(row.get("notes")),
                }
            )
        for platform in COMPETITOR_PLATFORMS:
            if platform not in present_platforms:
                rows.append(
                    {
                        "ug_config_id": config_id,
                        "ug_config": ug_config,
                        "duration_days": json_safe(duration_days),
                        "competitor_platform": platform,
                        "competitor_product_model": None,
                        "competitor_config": None,
                        "raw_effective_price_30d": None,
                        "quality_adjustment_factor": None,
                        "quality_adjusted_price_30d": None,
                        "config_similarity_score": None,
                        "comparability_level": "missing_competitor",
                        "included_in_core_median": False,
                        "exclusion_reason": "missing_competitor",
                        "pairing_source": "missing_competitor",
                        "pairing_notes": "No suitable competitor row was exported for this platform.",
                    }
                )
    return rows


def attach_decision_context(baskets: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {item.get("ug_config_id"): item for item in decisions}
    for row in baskets:
        decision = by_id.get(row.get("ug_config_id"), {})
        row["confidence_level"] = decision.get("confidence_level")
        row["market_position_label"] = decision.get("market_position_label")
        row["ugphone_relative_index"] = decision.get("ugphone_relative_index")
    return baskets


def build_pairing_evidence_records(pairings: pd.DataFrame) -> list[dict[str, Any]]:
    records = records_from_df(pairings)
    for row in records:
        level = row.get("comparability_level")
        row["linked_price_decision_id"] = row.get("ug_config_id")
        included = level in {"strong_match", "adjusted_match"}
        row["included_in_core_median"] = included
        if included:
            row["exclusion_reason"] = ""
        elif level == "weak_match":
            row["exclusion_reason"] = "weak_match_not_in_core_median"
        elif level == "not_comparable":
            row["exclusion_reason"] = "not_comparable"
        else:
            row["exclusion_reason"] = "missing_or_unknown_comparability"
    return records


def best_worst_competitors(group: pd.DataFrame) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    usable = group[pd.to_numeric(group["quality_adjusted_price_30d"], errors="coerce").notna()].copy()
    if usable.empty:
        return None, None
    usable["_adjusted"] = pd.to_numeric(usable["quality_adjusted_price_30d"], errors="coerce")
    best = usable.sort_values("_adjusted").iloc[0]
    worst = usable.sort_values("_adjusted").iloc[-1]

    def pack(row: pd.Series) -> dict[str, Any]:
        return {
            "platform": json_safe(row.get("competitor_platform")),
            "product_model": json_safe(row.get("competitor_product_model")),
            "config": json_safe(row.get("competitor_config")),
            "quality_adjusted_price_30d": json_safe(row.get("quality_adjusted_price_30d")),
            "comparability_level": json_safe(row.get("comparability_level")),
        }

    return pack(best), pack(worst)


def build_price_decision(relative_df: pd.DataFrame, details_df: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    details_by_key = {
        key: group.copy()
        for key, group in details_df.groupby(["ug_config", "duration_days"], dropna=False, sort=False)
    } if not details_df.empty else {}
    for _, row in relative_df.iterrows():
        ug_config = row.get("ug_config")
        duration_days = row.get("duration_days")
        config_id = ug_config_id(ug_config, duration_days)
        detail_group = details_by_key.get((ug_config, duration_days), pd.DataFrame())
        competitor_median = row.get("competitor_median_quality_adjusted_price_30d")
        ug_price = row.get("ug_effective_price_30d")
        if pd.isna(competitor_median) or pd.isna(ug_price) or not competitor_median:
            adjusted_gap = None
            adjusted_gap_pct = None
        else:
            adjusted_gap = float(ug_price) - float(competitor_median)
            adjusted_gap_pct = adjusted_gap / float(competitor_median)
        core = detail_group[detail_group["comparability_level"].isin(["strong_match", "adjusted_match"])] if not detail_group.empty else pd.DataFrame()
        weak = detail_group[detail_group["comparability_level"].eq("weak_match")] if not detail_group.empty else pd.DataFrame()
        core_platforms = set(core["competitor_platform"].dropna().astype(str).tolist()) if not core.empty else set()
        weak_platforms = set(weak["competitor_platform"].dropna().astype(str).tolist()) if not weak.empty else set()
        fallback_used = bool(
            not detail_group.empty
            and detail_group.get("notes", pd.Series(dtype=object)).astype(str).str.contains("current_missing_used_baseline", regex=False).any()
        )
        coverage_score, confidence_level, confidence_notes = confidence(core_platforms, weak_platforms, fallback_used)
        position = market_position_label(row.get("ugphone_relative_index"))
        reason_code = json_safe(row.get("reason_code")) or "unchanged"
        recommendation = recommendation_for(position, reason_code, confidence_level)
        best, worst = best_worst_competitors(detail_group)
        parsed = parse_ug_config(ug_config)
        rank_prices = []
        if not detail_group.empty:
            rank_prices = [
                float(value)
                for value in pd.to_numeric(detail_group["quality_adjusted_price_30d"], errors="coerce").dropna().tolist()
            ]
        if not pd.isna(ug_price):
            rank_prices.append(float(ug_price))
        price_rank = None
        if rank_prices and not pd.isna(ug_price):
            price_rank = 1 + sum(1 for value in rank_prices if value < float(ug_price))
        rows.append(
            {
                "ug_config_id": config_id,
                "ug_product_model": json_safe(row.get("ug_product_model")),
                **parsed,
                "duration_days": json_safe(duration_days),
                "ug_effective_price_30d": json_safe(ug_price),
                "competitor_median_quality_adjusted_price_30d": json_safe(competitor_median),
                "adjusted_price_gap": json_safe(adjusted_gap),
                "adjusted_price_gap_pct": json_safe(adjusted_gap_pct),
                "ugphone_relative_index": json_safe(row.get("ugphone_relative_index")),
                "market_position_label": position,
                "price_rank": price_rank,
                "core_competitor_count": len(core_platforms),
                "weak_competitor_count": len(weak_platforms),
                "pairing_coverage_score": json_safe(coverage_score),
                "confidence_level": confidence_level,
                "confidence_notes": confidence_notes,
                "alert_level": json_safe(row.get("alert_level")) or "none",
                "reason_code": reason_code,
                "reason_explanation": explain_reason(reason_code),
                "recommendation": recommendation,
                "best_competitor": best,
                "worst_competitor": worst,
            }
        )
    rows.sort(
        key=lambda item: (
            ALERT_RANK.get(item["alert_level"], 4),
            POSITION_RANK.get(item["market_position_label"], 4),
            -(item.get("ugphone_relative_index") or 0),
        )
    )
    return rows


def explain_reason(reason_code: str) -> str:
    codes = [part.strip() for part in str(reason_code or "").split(";") if part.strip()]
    if not codes:
        return REASON_EXPLANATIONS["unchanged"]
    return "；".join(REASON_EXPLANATIONS.get(code, code) for code in codes)


def explain_reason_en(reason_code: str) -> str:
    codes = [part.strip() for part in str(reason_code or "").split(";") if part.strip()]
    if not codes:
        return REASON_EXPLANATIONS_EN["unchanged"]
    return " ".join(REASON_EXPLANATIONS_EN.get(code, code) for code in codes)


def build_price_rationality_records(rationality: pd.DataFrame) -> list[dict[str, Any]]:
    rows = records_from_df(rationality)
    for row in rows:
        reason = row.get("reason_code") or "unchanged"
        row["reason_explanation_zh"] = explain_reason(reason)
        row["reason_explanation_en"] = explain_reason_en(reason)
    return rows


def build_matrix(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in decisions:
        best = item.get("best_competitor") or {}
        worst = item.get("worst_competitor") or {}
        ug_config = (
            f"{item.get('ug_product_model') or '-'} A{item.get('ug_android_version') or '-'} "
            f"{item.get('ug_cpu') or '-'}/{item.get('ug_ram') or '-'}/{item.get('ug_storage') or '-'}"
        )
        rows.append(
            {
                "ug_config_id": item["ug_config_id"],
                "ug_config": ug_config,
                "duration_days": item["duration_days"],
                "ug_effective_price_30d": item["ug_effective_price_30d"],
                "competitor_median_quality_adjusted_price_30d": item["competitor_median_quality_adjusted_price_30d"],
                "adjusted_price_gap": item["adjusted_price_gap"],
                "best_competitor": best.get("platform"),
                "best_competitor_adjusted_price": best.get("quality_adjusted_price_30d"),
                "worst_competitor": worst.get("platform"),
                "relative_index": item["ugphone_relative_index"],
                "adjusted_gap_pct": item["adjusted_price_gap_pct"],
                "market_position_label": item["market_position_label"],
                "core_matches": item["core_competitor_count"],
                "weak_matches": item["weak_competitor_count"],
                "confidence_level": item["confidence_level"],
                "alert_level": item["alert_level"],
                "reason_code": item["reason_code"],
                "recommendation": item["recommendation"],
            }
        )
    return rows


def distribution(decisions: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counts = Counter(item.get(key) or "unknown" for item in decisions)
    return [{"name": name, "value": count} for name, count in sorted(counts.items())]


def alert_priority(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        {
            "ug_config_id": item["ug_config_id"],
            "ug_config": (
                f"{item.get('ug_product_model') or '-'} A{item.get('ug_android_version') or '-'} "
                f"{item.get('ug_cpu') or '-'}/{item.get('ug_ram') or '-'}/{item.get('ug_storage') or '-'}"
            ),
            "relative_index": item.get("ugphone_relative_index"),
            "adjusted_gap_pct": item.get("adjusted_price_gap_pct"),
            "reason_code": item.get("reason_code"),
            "confidence_level": item.get("confidence_level"),
            "alert_level": item.get("alert_level"),
            "recommended_action": item.get("recommendation"),
            "needs_data_review": item.get("confidence_level") in {"low", "insufficient"}
            and (item.get("adjusted_price_gap_pct") or 0) > 0.1,
        }
        for item in decisions
        if item.get("alert_level") in {"critical", "warning"}
    ]
    rows.sort(key=lambda item: (ALERT_RANK.get(item["alert_level"], 4), -(item.get("relative_index") or 0)))
    return rows[:20]


def build_files(output_dir: Path, dashboard_files: list[str] | None = None) -> list[dict[str, Any]]:
    rows = []
    for name in SAFE_OUTPUT_FILES:
        path = output_dir / name
        rows.append(
            {
                "name": name,
                "path": str(path),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else None,
                "safe_to_open": path.exists() and "auth" not in path.parts,
            }
        )
    for name in dashboard_files or []:
        path = output_dir / "dashboard_data" / name
        rows.append(
            {
                "name": f"dashboard_data/{name}",
                "path": str(path),
                "exists": True,
                "size_bytes": path.stat().st_size if path.exists() else None,
                "safe_to_open": "auth" not in path.parts,
            }
        )
    return rows


def build_platform_status(output_dir: Path, run_summary: dict[str, Any]) -> list[dict[str, Any]]:
    products_path = output_dir / "products.xlsx"
    baseline_path = output_dir / "baseline_products_updated.xlsx"
    redfinger_summary_path = output_dir / "page_artifacts" / "redfinger_collection_summary.json"
    product_counts = {}
    priced_product_counts = {}
    baseline_counts = {}
    if products_path.exists():
        sheets = pd.read_excel(products_path, sheet_name=None, dtype=object)
        product_counts = {sheet.replace("采集", ""): len(df.dropna(how="all")) for sheet, df in sheets.items()}
        for sheet, frame in sheets.items():
            data = frame.dropna(how="all").copy()
            for column in ["price", "duration"]:
                if column not in data.columns:
                    data[column] = None
            priced_product_counts[sheet.replace("采集", "")] = int(
                (data["price"].notna() & data["duration"].notna()).sum()
            )
    if baseline_path.exists():
        sheets = pd.read_excel(baseline_path, sheet_name=None, dtype=object)
        baseline_counts = {
            sheet.replace("基准", "").replace("红手指", "Redfinger").replace("雷电云手机", "LDCloud"): len(df.dropna(how="all"))
            for sheet, df in sheets.items()
        }
        baseline_counts[BASE_PLATFORM] = baseline_counts.get(BASE_PLATFORM, baseline_counts.get(LEGACY_BASE_PLATFORM, baseline_counts.get(f"{LEGACY_BASE_PLATFORM}基准", 0)))
        baseline_counts["VSPhone"] = baseline_counts.get("VSPhone", 0)

    redfinger_summary = read_json(redfinger_summary_path) if redfinger_summary_path.exists() else {}
    rows = []
    raw_counts = run_summary.get("records_by_platform", {})
    blocked = run_summary.get("blocked_pages", {})
    names = ALL_PLATFORMS
    cn_to_name = {"红手指": "Redfinger", "雷电云手机": "LDCloud"}
    normalized_products = {}
    normalized_priced_products = {}
    for key, value in product_counts.items():
        normalized_products[normalize_platform_name(cn_to_name.get(key, key))] = value
    for key, value in priced_product_counts.items():
        normalized_priced_products[normalize_platform_name(cn_to_name.get(key, key))] = value

    for name in names:
        product_rows = normalized_products.get(name, 0)
        priced_product_rows = normalized_priced_products.get(name, 0)
        baseline_rows = baseline_counts.get(name, 0)
        legacy_name = LEGACY_BASE_PLATFORM if name == BASE_PLATFORM else name
        raw_records = raw_counts.get(name, raw_counts.get(legacy_name, 0))

        # Collection health and comparison with the old baseline are distinct signals.
        if name in blocked or legacy_name in blocked:
            collection_status = "blocked"
        elif raw_records <= 0 or priced_product_rows <= 0:
            collection_status = "failed"
        elif name == "Redfinger" and redfinger_summary:
            collection_status = str(redfinger_summary.get("collection_status") or "warning")
        else:
            collection_status = "ok"

        if baseline_rows <= 0:
            baseline_coverage_ratio = None
            baseline_coverage_status = "unknown"
        else:
            baseline_coverage_ratio = round(product_rows / baseline_rows, 4)
            if product_rows >= baseline_rows:
                baseline_coverage_status = "full"
            elif baseline_coverage_ratio >= 0.8:
                baseline_coverage_status = "changed"
            elif baseline_coverage_ratio >= 0.5:
                baseline_coverage_status = "partial"
            else:
                baseline_coverage_status = "low"

        row = {
            "platform": name,
            # Backward-compatible field for the existing dashboard UI.
            "status": collection_status,
            "collection_status": collection_status,
            "baseline_coverage_status": baseline_coverage_status,
            "baseline_coverage_ratio": baseline_coverage_ratio,
            "raw_records": raw_records,
            "product_rows": product_rows,
            "priced_product_rows": priced_product_rows,
            "baseline_rows": baseline_rows,
            "missing_vs_baseline": max(baseline_rows - product_rows, 0),
        }
        if name == "Redfinger" and redfinger_summary:
            row.update(
                {
                    "attempted_combinations": redfinger_summary.get("attempted_combinations"),
                    "price_api_seen_combinations": redfinger_summary.get("price_api_seen_combinations"),
                    "successful_price_combinations": redfinger_summary.get("successful_price_combinations"),
                    "price_api_coverage_ratio": redfinger_summary.get("price_api_coverage_ratio"),
                    "artifact_write_failures": redfinger_summary.get("artifact_write_failures", 0),
                }
            )
        rows.append(row)
    return rows


def build_daily_changes(output_dir: Path) -> list[dict[str, Any]]:
    path = output_dir / "daily_changes.xlsx"
    if not path.exists():
        return []
    xls = pd.ExcelFile(path)
    rows = []
    for sheet in xls.sheet_names:
        frame = pd.read_excel(path, sheet_name=sheet, dtype=object)
        rows.append(
            {
                "sheet": sheet,
                "rows": int(len(frame.dropna(how="all"))),
                "columns": list(frame.columns),
                "sample": records_from_df(frame.head(5)),
            }
        )
    return rows


def build_kpis(run_summary: dict[str, Any], decisions: list[dict[str, Any]], platform_rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_raw = sum((run_summary.get("records_by_platform") or {}).values())
    total_product_rows = sum(row.get("product_rows", 0) for row in platform_rows)
    total_baseline_rows = sum(row.get("baseline_rows", 0) for row in platform_rows)
    alerts = Counter(item.get("alert_level") or "none" for item in decisions)
    confidence_counts = Counter(item.get("confidence_level") or "unknown" for item in decisions)
    return {
        "total_raw_records": total_raw,
        "total_product_rows": total_product_rows,
        "total_baseline_rows": total_baseline_rows,
        "ug_config_count": len(decisions),
        "critical_alerts": alerts.get("critical", 0),
        "warning_alerts": alerts.get("warning", 0),
        "high_confidence_decisions": confidence_counts.get("high", 0),
        "low_confidence_decisions": confidence_counts.get("low", 0) + confidence_counts.get("insufficient", 0),
    }


def build_schedule_status(run_summary: dict[str, Any]) -> dict[str, Any]:
    scheduler_config = read_json(SCHEDULER_CONFIG_PATH)
    shanghai = ZoneInfo("Asia/Shanghai")
    now_utc = datetime.now(timezone.utc)
    last_run_time = parse_datetime(run_summary.get("end_time_utc") or run_summary.get("start_time_utc"))
    start_time = parse_datetime(run_summary.get("start_time_utc"))
    schedule_time_local = str(scheduler_config.get("schedule_time_local") or "10:00")
    try:
        hour, minute = [int(part) for part in schedule_time_local.split(":", 1)]
        run_time = time(hour=hour, minute=minute)
    except ValueError:
        schedule_time_local = "10:00"
        run_time = time(hour=10, minute=0)
    next_run = next_weekday_run(datetime.now(shanghai), run_time)
    if run_summary.get("failed_pages"):
        last_status = "failed"
    elif run_summary.get("warnings"):
        last_status = "warning"
    elif last_run_time:
        last_status = "success"
    else:
        last_status = "unknown"
    duration = None
    if start_time and last_run_time:
        duration = max(0, int((last_run_time - start_time).total_seconds()))
    stale_after_hours = int(scheduler_config.get("stale_after_hours") or 30)
    return {
        "scheduler_enabled": bool(scheduler_config.get("scheduler_enabled", False)),
        "scheduler_type": scheduler_config.get("scheduler_type") or "manual",
        "schedule_time_local": schedule_time_local,
        "last_run_time": last_run_time.isoformat(timespec="seconds") if last_run_time else None,
        "last_run_status": scheduler_config.get("last_run_status") or last_status,
        "next_run_time_estimated": next_run.isoformat(timespec="seconds"),
        "last_run_duration_seconds": duration,
        "data_freshness_status": data_freshness(last_run_time, now_utc, stale_after_hours),
        "stale_after_hours": stale_after_hours,
        "logs_path": str(Path("output") / "scheduler_logs"),
    }


def reconstruct_price(effective_price_30d: Any, duration_days: Any) -> float | None:
    if effective_price_30d is None or duration_days is None or pd.isna(effective_price_30d) or pd.isna(duration_days):
        return None
    duration = float(duration_days)
    if duration <= 0:
        return None
    return float(effective_price_30d) * duration / 30


def median(values: list[float]) -> float | None:
    clean = sorted(value for value in values if value is not None and not pd.isna(value))
    if not clean:
        return None
    mid = len(clean) // 2
    if len(clean) % 2:
        return clean[mid]
    return (clean[mid - 1] + clean[mid]) / 2


def frontend_position(index_value: Any) -> str:
    if index_value is None or pd.isna(index_value):
        return "unknown"
    value = float(index_value)
    if value < 90:
        return "below_market"
    if value <= 105:
        return "competitive"
    if value <= 115:
        return "slightly_high"
    return "high"


def split_config(config: Any) -> dict[str, Any]:
    parts = [part.strip() for part in str(config or "").split("/") if part.strip()]
    return {
        "product_model": parts[0] if len(parts) > 0 else None,
        "android_version": parts[1].replace("Android", "").strip() if len(parts) > 1 else None,
        "cpu": parts[2] if len(parts) > 2 else None,
        "ram": parts[3] if len(parts) > 3 else None,
        "storage": parts[4] if len(parts) > 4 else None,
    }


def public_config_id(ug_config: Any) -> str:
    safe = str(ug_config or "unknown").lower()
    return "".join(ch if ch.isalnum() else "_" for ch in safe).strip("_")


def build_pairing_matrix(pairing_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in pairing_records:
        config_id = public_config_id(row.get("ug_config"))
        current = grouped.setdefault(
            config_id,
            {
                "ug_config_id": config_id,
                "ug_config": row.get("ug_config"),
                "ug_product_model": row.get("ug_product_model"),
                "android_version": row.get("ug_android_version"),
                "cpu": row.get("ug_cpu"),
                "ram": row.get("ug_ram"),
                "storage": row.get("ug_storage"),
                "pairings": {},
            },
        )
        platform = normalize_platform_name(row.get("competitor_platform"))
        existing = current["pairings"].get(platform)
        score = row.get("config_similarity_score") or 0
        if not existing or score > (existing.get("config_similarity_score") or 0):
            current["pairings"][platform] = {
                "competitor_platform": platform,
                "competitor_product_model": row.get("competitor_product_model"),
                "competitor_config": (
                    f"{row.get('competitor_product_model') or '-'} / Android {row.get('competitor_android_version') or '-'} / "
                    f"{row.get('competitor_cpu') or '-'} / {row.get('competitor_ram') or '-'} / {row.get('competitor_storage') or '-'}"
                ),
                "config_similarity_score": row.get("config_similarity_score"),
                "comparability_level": row.get("comparability_level"),
                "pairing_source": row.get("pairing_source"),
                "pairing_notes": row.get("pairing_notes"),
                "included_in_core_median": row.get("included_in_core_median"),
                "exclusion_reason": row.get("exclusion_reason"),
            }
    return list(grouped.values())


def build_duration_price_comparison(details: pd.DataFrame) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {str(bucket): [] for bucket in FRONTEND_CORE_BUCKETS}
    other_rows: list[dict[str, Any]] = []
    if details.empty:
        return {"core_buckets": FRONTEND_CORE_BUCKETS, "buckets": buckets, "other_rows": other_rows}
    for (ug_config, duration_days), group in details.groupby(["ug_config", "duration_days"], dropna=False, sort=False):
        info = parse_duration_info(f"{duration_days} day" if not pd.isna(duration_days) else "")
        ug_price = reconstruct_price(group["ug_effective_price_30d"].dropna().iloc[0], duration_days) if "ug_effective_price_30d" in group and group["ug_effective_price_30d"].notna().any() else None
        parsed = split_config(ug_config)
        row = {
            "ug_config_id": public_config_id(ug_config),
            "ug_config": ug_config,
            "ug_product_model": parsed["product_model"],
            "ug_android_version": parsed["android_version"],
            "ug_cpu": parsed["cpu"],
            "ug_ram": parsed["ram"],
            "ug_storage": parsed["storage"],
            **info,
            "ugphone_price": json_safe(ug_price),
            "has_price_change": False,
            "promotion_text_changed": False,
            "competitors": {},
            "competitor_median_price": None,
            "ugphone_relative_index": None,
            "market_position_label": "unknown",
            "promotion_text": None,
        }
        core_prices = []
        for platform in COMPETITOR_PLATFORMS:
            candidates = group[(group["competitor_platform"].map(normalize_platform_name) == platform)] if "competitor_platform" in group else pd.DataFrame()
            if candidates.empty:
                row["competitors"][platform] = None
                continue
            candidates = candidates.copy()
            # Very important: a competitor price may come from a different actual
            # purchase duration when the quality report searched for a "nearest"
            # option.  Trend charts and day-bucket comparison must not show a
            # 90-day competitor price as a fake 180-day/365-day line.  The only
            # intentional cross-duration mapping currently allowed is LDCloud
            # 8-day -> 7-day bucket, handled by normalize_comparison_duration_info.
            def _candidate_duration_info(value: Any) -> dict[str, Any]:
                days = value
                if pd.isna(days):
                    return {"duration_bucket": "unknown", "duration_display": "未知", "is_core_duration_bucket": False}
                return normalize_comparison_duration_info(platform, f"{days} day")

            candidates["_duration_info"] = candidates["competitor_duration_days"].map(_candidate_duration_info) if "competitor_duration_days" in candidates else candidates["competitor_duration"].map(lambda value: normalize_comparison_duration_info(platform, value)) if "competitor_duration" in candidates else None
            candidates["_actual_duration_bucket"] = candidates["_duration_info"].map(lambda value: str((value or {}).get("duration_bucket") or "unknown"))
            target_bucket = str(info.get("duration_bucket") or "unknown")
            duration_matched = candidates[candidates["_actual_duration_bucket"] == target_bucket]
            if duration_matched.empty:
                # Keep an explanatory placeholder for the frontend, but do not
                # create a core price or a trend line.  Example: VSPhone has no
                # real 180-day SKU in products.csv, so its 90-day price must not
                # appear under the 180-day bucket.
                nearest = candidates.iloc[0]
                nearest_info = nearest.get("_duration_info") or {}
                row["competitors"][platform] = {
                    "platform": platform,
                    "product_model": json_safe(nearest.get("competitor_product_model")),
                    "config": json_safe(nearest.get("competitor_config")),
                    "current_price": None,
                    "config_similarity_score": json_safe(nearest.get("config_similarity_score")),
                    "comparability_level": json_safe(nearest.get("comparability_level")),
                    "included_in_core_median": False,
                    "exclusion_reason": "actual_duration_bucket_mismatch",
                    "pairing_source": json_safe(nearest.get("pairing_source")),
                    "promotion_text": json_safe(nearest.get("promotion_text")),
                    "actual_duration_days": json_safe(nearest.get("competitor_duration_days")),
                    "actual_duration_display": json_safe((nearest_info or {}).get("actual_duration_display") or (nearest_info or {}).get("duration_display")),
                    "actual_duration_bucket": json_safe(nearest_info.get("duration_bucket")),
                    "duration_mismatch_note": f"该竞品没有{info.get('duration_display') or target_bucket + '天'}的真实购买周期；已排除，不把其他周期价格伪装成本周期价格。",
                }
                continue

            candidates = duration_matched.copy()
            candidates["_is_core"] = candidates["comparability_level"].isin(["strong_match", "adjusted_match"])
            candidates["_variant_info"] = candidates["promotion_text"].map(lambda value: classify_price_variant(value))
            candidates["_is_core_price_variant"] = candidates["_variant_info"].map(lambda value: bool(value.get("include_in_core_price_monitor")))
            candidates["_variant_rank"] = candidates["_variant_info"].map(lambda value: variant_sort_rank(value.get("price_variant")))
            candidates = candidates.sort_values(["_is_core", "_is_core_price_variant", "_variant_rank", "config_similarity_score"], ascending=[False, False, True, False])
            candidate = candidates.iloc[0]
            variant_info = candidate.get("_variant_info") or classify_price_variant(candidate.get("promotion_text"))
            candidate_duration_info = candidate.get("_duration_info") or {}
            price = reconstruct_price(candidate.get("competitor_effective_price_30d"), candidate.get("competitor_duration_days") or duration_days)
            included = bool(candidate.get("comparability_level") in {"strong_match", "adjusted_match"} and price is not None and info["is_core_duration_bucket"] and variant_info.get("include_in_core_price_monitor"))
            if included:
                core_prices.append(price)
            row["competitors"][platform] = {
                "platform": platform,
                "product_model": json_safe(candidate.get("competitor_product_model")),
                "config": json_safe(candidate.get("competitor_config")),
                "current_price": json_safe(price),
                "config_similarity_score": json_safe(candidate.get("config_similarity_score")),
                "comparability_level": json_safe(candidate.get("comparability_level")),
                "included_in_core_median": included,
                "exclusion_reason": "" if included else ("not_core_duration_bucket" if not info["is_core_duration_bucket"] else f"{candidate.get('comparability_level') or 'missing'}_not_in_core_median"),
                "pairing_source": json_safe(candidate.get("pairing_source")),
                "promotion_text": json_safe(candidate.get("promotion_text")),
                "price_variant": json_safe(variant_info.get("price_variant")),
                "price_variant_label": json_safe(variant_info.get("price_variant_label")),
                "include_in_core_price_monitor": bool(variant_info.get("include_in_core_price_monitor")),
                "variant_exclusion_reason": json_safe(variant_info.get("variant_exclusion_reason")),
                "actual_duration_days": json_safe(candidate.get("competitor_duration_days")),
                "actual_duration_display": json_safe(candidate_duration_info.get("actual_duration_display") or candidate_duration_info.get("duration_display")),
                "actual_duration_bucket": json_safe(candidate_duration_info.get("duration_bucket")),
                "comparison_duration_note": json_safe(candidate_duration_info.get("comparison_duration_note")),
            }
        row["competitor_median_price"] = json_safe(median(core_prices))
        if ug_price is not None and row["competitor_median_price"]:
            row["ugphone_relative_index"] = json_safe(ug_price / row["competitor_median_price"] * 100)
            row["market_position_label"] = frontend_position(row["ugphone_relative_index"])
        if info["is_core_duration_bucket"]:
            buckets[str(info["duration_bucket"])].append(row)
        else:
            other_rows.append(row)
    return {"core_buckets": FRONTEND_CORE_BUCKETS, "buckets": buckets, "other_rows": other_rows}


def build_frontend_price_overview(duration_comparison: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    rows = [row for bucket in duration_comparison["buckets"].values() for row in bucket]
    counts = Counter(row.get("market_position_label") or "unknown" for row in rows)
    focus = sorted(
        [row for row in rows if row.get("market_position_label") in {"high", "slightly_high"}],
        key=lambda item: (POSITION_RANK.get(item.get("market_position_label"), 4), -(item.get("ugphone_relative_index") or 0)),
    )[:12]
    return {
        "updated_at": meta.get("last_run_at_utc") or meta.get("generated_at_utc"),
        "baseline_config_count": len({row.get("ug_config_id") for row in rows}),
        "core_duration_buckets": FRONTEND_CORE_BUCKETS,
        "rows_compared": len(rows),
        "market_position_counts": dict(counts),
        "above_market_count": counts.get("slightly_high", 0) + counts.get("high", 0),
        "below_market_count": counts.get("below_market", 0),
        "attention_items": focus,
    }


def attach_price_change_flags(duration_comparison: dict[str, Any], price_changes: list[dict[str, Any]]) -> dict[str, Any]:
    by_product_duration = {}
    for row in price_changes:
        if normalize_platform_name(row.get("platform")) != BASE_PLATFORM:
            continue
        key = (str(row.get("product_model") or "").lower(), str(row.get("duration_bucket")))
        by_product_duration[key] = row
    for rows in (duration_comparison.get("buckets") or {}).values():
        for row in rows:
            change = by_product_duration.get((str(row.get("ug_product_model") or "").lower(), str(row.get("duration_bucket"))), {})
            row["has_price_change"] = bool(change.get("price_change_pct") not in {None, 0})
            row["promotion_text_changed"] = bool(change.get("promotion_text_changed"))
            row["price_change_pct"] = json_safe(change.get("price_change_pct"))
            row["reason_code"] = json_safe(change.get("reason_code"))
            row["alert_level"] = json_safe(change.get("alert_level"))
    return duration_comparison


def price_reason(current: float | None, previous: float | None, promo_changed: bool, excluded: bool = False) -> tuple[str, str]:
    if excluded:
        return "short_duration_excluded", "info"
    if current is None:
        return "duration_missing_current_used_baseline", "info"
    if previous is None or previous == 0:
        return ("promotion_text_changed", "info") if promo_changed else ("price_unchanged", "none")
    pct_change = (current - previous) / previous
    if abs(pct_change) >= 0.1 and not promo_changed:
        return "abnormal_price_change", "warning"
    if pct_change > 0.01:
        return "price_up", "warning"
    if pct_change < -0.01:
        return "price_down", "info"
    if promo_changed:
        return "promotion_text_changed", "info"
    return "price_unchanged", "none"


def _is_missing_cell(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    text = str(value).strip().lower()
    return text in {"", "nan", "none", "null", "-", "—"}


def _is_valid_rationality_row(item: pd.Series | dict[str, Any]) -> bool:
    """Filter out workbook note rows such as baseline_missing.

    When quality_price_report.xlsx cannot build a baseline-backed rationality
    table, older rebuild logic created one diagnostic row with only reason_code.
    The frontend then displayed it as `nan / Anan / nan / nan / nan`.  Such rows
    are not product rows and must not enter price_change_tracking.json.
    """
    platform = item.get("platform")
    product_model = item.get("product_model")
    duration_days = item.get("duration_days")
    return not (_is_missing_cell(platform) or _is_missing_cell(product_model) or _is_missing_cell(duration_days))


def build_price_change_tracking(rationality: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    if rationality.empty:
        return rows
    for _, item in rationality.iterrows():
        if not _is_valid_rationality_row(item):
            continue
        duration_days = item.get("duration_days")
        info = parse_duration_info(f"{duration_days} day" if not pd.isna(duration_days) else "")
        current = reconstruct_price(item.get("current_effective_price_30d"), duration_days)
        baseline = reconstruct_price(item.get("baseline_effective_price_30d"), duration_days)
        previous = baseline
        promo_changed = json_safe(item.get("baseline_promotion_text")) != json_safe(item.get("current_promotion_text"))
        reason, alert = price_reason(current, previous, promo_changed, excluded=not info["is_core_duration_bucket"])
        change_abs = None if current is None or previous is None else current - previous
        change_pct = None if change_abs is None or previous in {None, 0} else change_abs / previous
        config = f"{item.get('product_model') or '-'} / A{item.get('android_version') or '-'} / {item.get('cpu') or '-'} / {item.get('ram') or '-'} / {item.get('storage') or '-'}"
        rows.append(
            {
                "platform": normalize_platform_name(item.get("platform")),
                "product_model": json_safe(item.get("product_model")),
                "device_model": json_safe(item.get("device_model")),
                "android_version": json_safe(item.get("android_version")),
                "cpu": json_safe(item.get("cpu")),
                "ram": json_safe(item.get("ram")),
                "storage": json_safe(item.get("storage")),
                "config": config,
                **info,
                "baseline_price": json_safe(baseline),
                "previous_price": json_safe(previous),
                "current_price": json_safe(current),
                "price_change_abs": json_safe(change_abs),
                "price_change_pct": json_safe(change_pct),
                "baseline_price_change_abs": json_safe(change_abs),
                "baseline_price_change_pct": json_safe(change_pct),
                "seven_day_avg_price": json_safe(current if current is not None else previous),
                "seven_day_sample_count": 1 if current is not None or previous is not None else 0,
                "thirty_day_avg_price": json_safe(current if current is not None else previous),
                "thirty_day_sample_count": 1 if current is not None or previous is not None else 0,
                "promotion_text_changed": promo_changed,
                "current_promotion_text": json_safe(item.get("current_promotion_text")),
                "previous_promotion_text": json_safe(item.get("baseline_promotion_text")),
                "reason_code": reason,
                "reason_explanation": FRONTEND_REASON_EXPLANATIONS.get(reason),
                "alert_level": alert,
                "price_source": "baseline_fallback" if current is None and baseline is not None else ("current" if current is not None else "missing"),
            }
        )
    return rows


def build_product_text_changes(price_changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "platform": row["platform"],
            "product_model": row.get("product_model"),
            "config": row["config"],
            "duration_bucket": row["duration_bucket"],
            "duration_display": row["duration_display"],
            "current_price": row["current_price"],
            "current_promotion_text": row["current_promotion_text"],
            "previous_promotion_text": row["previous_promotion_text"],
            "promotion_text_changed": row["promotion_text_changed"],
            "reason_code": row["reason_code"],
        }
        for row in price_changes
    ]



def trend_date_label(value: Any, fallback: str) -> str:
    parsed = parse_datetime(value)
    if parsed:
        return parsed.date().isoformat()
    return fallback


def compact_series_id(*parts: Any) -> str:
    raw = "_".join(str(part or "unknown") for part in parts)
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in raw).strip("_")


def is_iso_date_label(value: Any) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", str(value or "")))


def parse_float_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "-", "—"}:
        return None
    text = re.sub(r"[^0-9.\-]", "", text)
    if text in {"", ".", "-"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


# Price variants are used to keep core market monitoring clean.
# Core charts should use real general-purchase paid prices only.  New-user-only,
# trial, flash/Discord-only, and multi-device package prices are still exported
# as "other paid prices", but they do not drive the main trend/index charts.
PRICE_VARIANT_LABELS = {
    "regular": "日常实付价",
    "public_offer": "公开活动实付价",
    "holiday_offer": "节日活动实付价",
    "new_user_offer": "新客活动实付价",
    "flash_sale": "限时/渠道秒杀实付价",
    "duet_pack": "双设备组合包实付价",
    "team_pack": "多设备团队包实付价",
    "multi_device_pack": "多设备组合包实付价",
    "trial": "短时试用价",
    "unknown_offer": "其他实付价",
    "higher_region_price": "同产品其他机房实付价",
    "minority_region_price": "少数机房实付价",
    "unavailable_region_price": "无库存/不可购买机房价格",
}
CORE_PRICE_VARIANTS = {"regular", "public_offer", "holiday_offer"}
NON_CORE_PRICE_VARIANTS = {"new_user_offer", "flash_sale", "duet_pack", "team_pack", "multi_device_pack", "trial", "unknown_offer", "higher_region_price", "minority_region_price", "unavailable_region_price"}


def _non_empty_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    if text.lower() in {"", "none", "nan", "null", "-", "—"}:
        return ""
    return text


def _is_probably_bulk_api_text(text: str) -> bool:
    """Return True for long API blobs that may contain other products' words.

    Historical products.csv rows often store a full API response in raw_text.
    If we scan that blob for tokens such as "new user", "trial", or
    "unavailable", one row can be contaminated by unrelated products in the same
    API payload.  Therefore raw_text is only a fallback when it looks like a
    short row-level label, not a full JSON/API blob.
    """
    if not text:
        return False
    stripped = text.strip()
    if len(stripped) > 300:
        return True
    lowered = stripped.lower()
    if stripped.startswith(("{", "[")):
        return True
    if any(marker in lowered for marker in ["\"goodsid\"", "\"goodscode\"", "\"config\"", "\"meal", "api_", "productid", "cardtype"]):
        return True
    return False


def _row_level_variant_text(promotion_text: Any = "", raw_text: Any = "", duration_text: Any = "") -> str:
    """Build clean text for price-variant classification.

    Priority: current row promotion text + duration.  raw_text is deliberately
    excluded in normal cases because old exports often save the whole API
    response there, which caused normal UgPhone prices to be misclassified as
    trial/new-user/unavailable.
    """
    promo = _non_empty_text(promotion_text)
    duration = _non_empty_text(duration_text)
    parts = [promo, duration]
    raw = _non_empty_text(raw_text)
    if not promo and raw and not _is_probably_bulk_api_text(raw):
        parts.append(raw)
    return " ".join(part for part in parts if part).lower()


def classify_price_variant(promotion_text: Any = "", raw_text: Any = "", duration_text: Any = "") -> dict[str, Any]:
    text = _row_level_variant_text(promotion_text, raw_text, duration_text)
    device_count = 1
    device_match = re.search(r"get\s*(\d+)\s*devices?", text)
    if device_match:
        try:
            device_count = max(1, int(device_match.group(1)))
        except ValueError:
            device_count = 1
    elif any(token in text for token in ["duet pack", "双设备", "分拆两台", "2台", "two devices"]):
        device_count = 2
    elif any(token in text for token in ["team pack", "团购", "批量", "5 devices", "五台", "5台"]):
        device_count = 5

    if any(token in text for token in ["new user", "新用户", "新客", "first purchase", "first order", "trial", "4-hour", "4 hour", "hour trial"]):
        variant = "trial" if any(token in text for token in ["trial", "4-hour", "4 hour", "hour trial"]) else "new_user_offer"
        return {
            "price_variant": variant,
            "price_variant_label": PRICE_VARIANT_LABELS[variant],
            "device_count": device_count,
            "include_in_core_price_monitor": False,
            "variant_exclusion_reason": "new_user_or_trial_price_not_core",
        }
    if any(token in text for token in ["duet pack", "team pack", "devices in total", "get 2 devices", "get 5 devices", "分拆", "团购", "批量"]):
        if "duet" in text or "get 2" in text or "分拆两台" in text:
            variant = "duet_pack"
        elif "team" in text or "get 5" in text or "团购" in text or "批量" in text:
            variant = "team_pack"
        else:
            variant = "multi_device_pack"
        return {
            "price_variant": variant,
            "price_variant_label": PRICE_VARIANT_LABELS[variant],
            "device_count": device_count,
            "include_in_core_price_monitor": False,
            "variant_exclusion_reason": "multi_device_package_price_not_core",
        }
    if any(token in text for token in ["discord exclusive", "flash sale", "秒杀"]):
        return {
            "price_variant": "flash_sale",
            "price_variant_label": PRICE_VARIANT_LABELS["flash_sale"],
            "device_count": device_count,
            "include_in_core_price_monitor": False,
            "variant_exclusion_reason": "channel_or_flash_sale_not_core",
        }
    if any(token in text for token in ["holiday offer", "holiday exclusive", "五一", "节日"]):
        return {
            "price_variant": "holiday_offer",
            "price_variant_label": PRICE_VARIANT_LABELS["holiday_offer"],
            "device_count": device_count,
            "include_in_core_price_monitor": True,
            "variant_exclusion_reason": "",
        }
    if any(token in text for token in ["special offer", "you save", "limited time", "offer", "recommend"]):
        return {
            "price_variant": "public_offer",
            "price_variant_label": PRICE_VARIANT_LABELS["public_offer"],
            "device_count": device_count,
            "include_in_core_price_monitor": True,
            "variant_exclusion_reason": "",
        }
    return {
        "price_variant": "regular",
        "price_variant_label": PRICE_VARIANT_LABELS["regular"],
        "device_count": device_count,
        "include_in_core_price_monitor": True,
        "variant_exclusion_reason": "",
    }


def normalize_price_for_variant(price: Any, variant_info: dict[str, Any]) -> float | None:
    price_value = parse_float_value(price)
    if price_value is None:
        return None
    device_count = variant_info.get("device_count") or 1
    try:
        device_count = max(1, int(device_count))
    except Exception:
        device_count = 1
    return price_value / device_count


UNAVAILABLE_STOCK_TERMS = [
    "out of stock", "sold out", "unavailable", "not available", "no stock",
    "disabled", "stop selling", "stopped", "cannot purchase",
    "无库存", "缺货", "售罄", "不可购买", "停止售卖", "已下架", "无法购买",
]


def normalize_region_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = normalize_display_text(value).strip()
    if text.lower() in {"", "none", "nan", "null", "-", "—"}:
        return ""
    return text


def row_region_text(row: pd.Series | dict[str, Any]) -> str:
    for key in ["server_region", "supported_server_regions", "region", "regions"]:
        try:
            value = row.get(key)
        except Exception:
            value = None
        text = normalize_region_text(value)
        if text:
            return text
    return ""


REGION_LABEL_ALIASES = {
    "us": "United States",
    "usa": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "america": "United States",
    "united states of america": "United States",
    "美国": "United States",
    "hongkong": "Hong Kong",
    "hong kong": "Hong Kong",
    "hongkong2": "Hong Kong 2",
    "hong kong 2": "Hong Kong 2",
    "hk2": "Hong Kong 2",
    "hk": "Hong Kong",
    "香港": "Hong Kong",
    "singapore": "Singapore",
    "sg": "Singapore",
    "新加坡": "Singapore",
    "thailand": "Thailand",
    "thai": "Thailand",
    "泰国": "Thailand",
    "japan": "Japan",
    "jp": "Japan",
    "日本": "Japan",
    "germany": "Germany",
    "de": "Germany",
    "netherlands": "Netherlands",
    "nl": "Netherlands",
    "德国": "Germany",
    "indonesia": "Indonesia",
    "id": "Indonesia",
    "印尼": "Indonesia",
    "vietnam": "Vietnam",
    "vn": "Vietnam",
    "越南": "Vietnam",
    "brazil": "Brazil",
    "br": "Brazil",
    "巴西": "Brazil",
    "taiwan": "Taiwan",
    "tw": "Taiwan",
    "台湾": "Taiwan",
    "italy": "Italy",
    "it": "Italy",
    "意大利": "Italy",
    "korea": "South Korea",
    "south korea": "South Korea",
    "kr": "South Korea",
    "韩国": "South Korea",
}


def normalize_region_label(value: Any) -> str:
    text = normalize_region_text(value)
    if not text:
        return ""
    key = re.sub(r"\s+", " ", text.strip().lower())
    return REGION_LABEL_ALIASES.get(key, text.strip())


def split_region_values(value: Any) -> list[str]:
    text = normalize_region_text(value)
    if not text:
        return []
    parts = re.split(r"[;,，、/\n]+", text)
    cleaned = [normalize_region_label(part) for part in parts]
    deduped: list[str] = []
    for part in cleaned:
        if part and part not in deduped:
            deduped.append(part)
    return deduped




def region_count_for_selection(value: Any) -> int:
    """Count machine rooms/regions represented by a grouped product row.

    When one product has different prices by machine room, the core trend should
    represent the price seen by most machine rooms. If counts tie, choose the
    lower price. Grouped region text such as "美国; 德国; 新加坡" counts as 3.
    """
    regions = split_region_values(value)
    return max(1, len(regions))


def price_bucket_key(value: Any) -> float | None:
    price = parse_float_value(value)
    if price is None:
        return None
    return round(float(price), 4)

def is_unavailable_product_row(row: pd.Series | dict[str, Any]) -> bool:
    """Detect unavailable rows from row-level availability fields only.

    Do not scan full raw_text/API blobs by default. Historical raw_text can
    contain other products' sold-out/unavailable labels and previously caused
    normal prices to be excluded from core trends.
    """
    status_parts: list[str] = []
    for key in ["stock_status", "availability", "status"]:
        value = _non_empty_text(row.get(key) if hasattr(row, "get") else None)
        if value:
            status_parts.append(value)
    status_text = " ".join(status_parts).lower()
    if status_text:
        if any(term in status_text for term in UNAVAILABLE_STOCK_TERMS):
            return True
        # Explicit available statuses are authoritative.
        if any(term in status_text for term in ["available", "in stock", "on sale", "可购买", "有库存", "在售"]):
            return False

    context_parts: list[str] = []
    for key in ["promotion_text", "notes"]:
        value = _non_empty_text(row.get(key) if hasattr(row, "get") else None)
        if value:
            context_parts.append(value)
    raw = _non_empty_text(row.get("raw_text") if hasattr(row, "get") else None)
    if raw and not _is_probably_bulk_api_text(raw):
        context_parts.append(raw)
    context_text = " ".join(context_parts).lower()
    return bool(context_text and any(term in context_text for term in UNAVAILABLE_STOCK_TERMS))


def is_majority_region_activity_override_candidate(row: dict[str, Any]) -> bool:
    """Allow selected row-level activity prices to enter region-majority selection.

    UgPhone GVIP 30-day rows in recent outputs are labeled with a
    new-user-looking promotion text, but the same 7.99 paid price covers the
    overwhelming majority of currently purchasable machine rooms.  Excluding
    those rows before region-majority selection leaves only minority prices such
    as Singapore/Thailand 10.99/11.99 and produces a wrong core trend.

    Keep this override intentionally narrow: UgPhone + GVIP + 30-day only.
    Minority/new-user-only rows still lose to the majority-region rule and are
    exported as other paid prices.
    """
    platform = normalize_platform_name(row.get("platform"))
    product = normalize_series_product(row.get("product_model"))
    bucket = str(row.get("duration_bucket") or "")
    variant = str(row.get("price_variant") or "")
    try:
        device_count = int(row.get("device_count") or 1)
    except Exception:
        device_count = 1
    return (
        platform == BASE_PLATFORM
        and product == "gvip"
        and bucket == "30"
        and variant == "new_user_offer"
        and device_count == 1
    )


def is_single_device_payable_variant(variant_info: dict[str, Any]) -> bool:
    """Return True only for generally purchasable single-device paid prices.

    New-user-only prices are real paid prices, but they should not drive the
    core trend or the brand index. They are exported as “其他实付价” instead.
    """
    if not bool(variant_info.get("include_in_core_price_monitor")):
        return False
    variant = str(variant_info.get("price_variant") or "")
    if variant in NON_CORE_PRICE_VARIANTS or variant in {"new_user_offer"}:
        return False
    try:
        device_count = int(variant_info.get("device_count") or 1)
    except Exception:
        device_count = 1
    return device_count == 1


def config_signature_without_android_from_product_row(row: pd.Series) -> str:
    cpu = normalize_token(row.get("cpu"))
    ram = normalize_token(row.get("ram"))
    storage = normalize_token(row.get("storage"))
    cpu_num = re.search(r"[0-9]+(?:\.[0-9]+)?", cpu)
    ram_num = re.search(r"[0-9]+(?:\.[0-9]+)?", ram)
    storage_num = re.search(r"[0-9]+(?:\.[0-9]+)?", storage)
    return "|".join([
        cpu_num.group(0).rstrip(".0") if cpu_num and cpu_num.group(0).endswith(".0") else (cpu_num.group(0) if cpu_num else cpu),
        ram_num.group(0).rstrip(".0") if ram_num and ram_num.group(0).endswith(".0") else (ram_num.group(0) if ram_num else ram),
        storage_num.group(0).rstrip(".0") if storage_num and storage_num.group(0).endswith(".0") else (storage_num.group(0) if storage_num else storage),
    ])


def android_version_from_row(row: pd.Series | dict[str, Any]) -> str:
    try:
        value = row.get("android_version")
    except Exception:
        value = None
    text = normalize_display_text(value)
    match = re.search(r"[0-9]+(?:\.[0-9]+)?", text)
    return match.group(0).rstrip(".0") if match and match.group(0).endswith(".0") else (match.group(0) if match else text)


def is_core_price_variant(promotion_text: Any = "", raw_text: Any = "", duration_text: Any = "") -> bool:
    return bool(classify_price_variant(promotion_text, raw_text, duration_text).get("include_in_core_price_monitor"))


def variant_sort_rank(variant: Any) -> int:
    # Public/holiday offers are real current paid prices when available to all users.
    # Regular price is next.  Non-core variants should not normally be compared here.
    return {
        "holiday_offer": 0,
        "public_offer": 0,
        "regular": 1,
        "new_user_offer": 50,
        "trial": 51,
        "flash_sale": 52,
        "duet_pack": 53,
        "team_pack": 54,
        "multi_device_pack": 55,
        "higher_region_price": 56,
        "minority_region_price": 56,
        "unavailable_region_price": 57,
        "unknown_offer": 60,
    }.get(str(variant or ""), 40)


def normalize_token(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def normalize_series_product(value: Any) -> str:
    return normalize_token(normalize_display_text(value))


def normalize_config_signature(value: Any) -> str:
    """Create a stable configuration signature for matching historical product rows.

    Historical products.csv has explicit android/cpu/ram/storage columns, while current
    trend series usually stores a human-readable config string.  We normalize both to a
    compact signature so historical daily prices can be attached to the correct line.
    """
    text = normalize_display_text(value)
    lower = str(text or "").lower()
    android = ""
    cpu = ""
    ram = ""
    storage = ""
    android_match = re.search(r"(?:android|a)\s*([0-9]+(?:\.[0-9]+)?)", lower)
    if android_match:
        android = android_match.group(1).rstrip(".0") if android_match.group(1).endswith(".0") else android_match.group(1)
    cpu_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:cores?|c\b)", lower)
    if cpu_match:
        cpu = cpu_match.group(1).rstrip(".0") if cpu_match.group(1).endswith(".0") else cpu_match.group(1)
    gb_values = re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*gb", lower)
    if gb_values:
        ram = gb_values[0].rstrip(".0") if gb_values[0].endswith(".0") else gb_values[0]
    if len(gb_values) > 1:
        storage = gb_values[1].rstrip(".0") if gb_values[1].endswith(".0") else gb_values[1]
    if not any([android, cpu, ram, storage]):
        return normalize_token(text)
    return "|".join([android, cpu, ram, storage])


def config_signature_from_product_row(row: pd.Series) -> str:
    android = normalize_token(row.get("android_version"))
    android = android[:-2] if android.endswith(".0") else android
    cpu = normalize_token(row.get("cpu"))
    ram = normalize_token(row.get("ram"))
    storage = normalize_token(row.get("storage"))
    cpu_num = re.search(r"[0-9]+(?:\.[0-9]+)?", cpu)
    ram_num = re.search(r"[0-9]+(?:\.[0-9]+)?", ram)
    storage_num = re.search(r"[0-9]+(?:\.[0-9]+)?", storage)
    return "|".join([
        android,
        cpu_num.group(0).rstrip(".0") if cpu_num and cpu_num.group(0).endswith(".0") else (cpu_num.group(0) if cpu_num else cpu),
        ram_num.group(0).rstrip(".0") if ram_num and ram_num.group(0).endswith(".0") else (ram_num.group(0) if ram_num else ram),
        storage_num.group(0).rstrip(".0") if storage_num and storage_num.group(0).endswith(".0") else (storage_num.group(0) if storage_num else storage),
    ])


def local_date_from_iso(value: Any, fallback_tz: str = "Asia/Shanghai") -> str | None:
    """Return the business/display date for a timestamp.

    The scraper stores run_summary times in UTC while the output directory name
    and dashboard expectation follow the operator's local day (UTC+8 in this
    workflow).  A run executed on May 8 morning local time can still have a May 7
    UTC timestamp.  Using the raw UTC date makes the latest local run overwrite
    or merge into the prior day, which is why the chart sometimes stopped at
    May 7 even though output/cloud_phone_monitor_20260508_* existed.
    """
    if value is None or str(value).strip() in {"", "nan", "None"}:
        return None
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            # Local-looking timestamps such as crawl_time_local already express
            # the intended display day.
            return dt.date().isoformat()
        return dt.astimezone(ZoneInfo(fallback_tz)).date().isoformat()
    except Exception:
        match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
        if match:
            y, m, d = match.groups()
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    return None


def _find_column_case_insensitive(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the real column name for any candidate, ignoring case/spacing."""
    normalized = {str(col).strip().lower(): col for col in frame.columns}
    for candidate in candidates:
        key = str(candidate).strip().lower()
        if key in normalized:
            return normalized[key]
    return None


def output_run_date_from_products(run_dir: Path) -> str | None:
    """Infer dashboard display date from row-level product crawl timestamps.

    This project treats the business day as UTC+8.  Some run directories or
    run_summary fields can still be stamped with the UTC day, so the most
    reliable source is the products table's crawl_time_local (or crawl_time_utc
    converted to UTC+8).  Read enough rows to survive blank/sample rows and
    prefer local-time columns over UTC columns.
    """

    def infer_from_frame(sample: pd.DataFrame) -> str | None:
        if sample is None or sample.empty:
            return None
        column_groups = [
            ["crawl_time_local", "采集时间本地", "local_time", "crawl_local_time"],
            ["crawl_time_utc", "采集时间UTC", "utc_time", "crawl_utc_time"],
            ["timestamp", "crawl_time", "采集时间", "created_at", "updated_at"],
        ]
        for candidates in column_groups:
            col = _find_column_case_insensitive(sample, candidates)
            if not col:
                continue
            values = sample[col].dropna().tolist()
            # Use the latest row-level local display date in this products table.
            labels: list[str] = []
            for value in values:
                label = local_date_from_iso(value)
                if is_iso_date_label(label):
                    labels.append(str(label))
            if labels:
                return max(labels)
        return None

    csv_path = run_dir / "products.csv"
    try:
        if csv_path.exists():
            sample = pd.read_csv(csv_path, dtype=object, nrows=80)
            label = infer_from_frame(sample)
            if is_iso_date_label(label):
                return label
    except Exception:
        pass
    xlsx_path = run_dir / "products.xlsx"
    try:
        if xlsx_path.exists():
            sample = pd.read_excel(xlsx_path, dtype=object, nrows=80)
            label = infer_from_frame(sample)
            if is_iso_date_label(label):
                return label
    except Exception:
        pass
    return None


def output_run_date(run_dir: Path) -> str | None:
    # The dashboard business date must be UTC+8.  Prefer row-level products
    # crawl_time_local / crawl_time_utc converted to UTC+8 for *all* output
    # directories, not only output/latest.  This prevents a local May 8 run
    # stored in a UTC-stamped run folder from being collapsed into May 7.
    product_date = output_run_date_from_products(run_dir)
    if is_iso_date_label(product_date):
        return product_date

    summary = read_json(run_dir / "run_summary.json")
    for key in ["end_time_local", "start_time_local", "generated_at_local", "end_time_utc", "start_time_utc", "generated_at_utc"]:
        label = local_date_from_iso(summary.get(key))
        if is_iso_date_label(label):
            return label

    # Final fallback: timestamped directory name.  This is intentionally last
    # because the directory can reflect UTC or stale copy time, while products
    # rows reflect the actual business collection date.
    match = re.search(r"cloud_phone_monitor_(\d{8})", run_dir.name)
    if match:
        raw = match.group(1)
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return None


def iter_history_output_dirs(current_output_dir: Path) -> list[Path]:
    root = current_output_dir.parent
    if not root.exists():
        return []
    dirs = [item for item in root.iterdir() if item.is_dir() and item.name.startswith("cloud_phone_monitor_")]
    # Keep chronological order.  Multiple runs on the same day intentionally overwrite
    # earlier daily points so the latest successful run of that day is used.
    return sorted(dirs, key=lambda item: item.name)


def add_history_point(
    history: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]],
    loose_history: dict[tuple[str, str, str], dict[str, dict[str, Any]]],
    *,
    platform: Any,
    product_model: Any,
    config_signature: str,
    bucket: Any,
    date: str,
    price: Any,
    source: str,
    price_variant: str = "regular",
    price_variant_label: str = "日常实付价",
    device_count: int = 1,
    package_total_price: Any = None,
    promotion_text: Any = None,
    source_run_dir: Any = None,
    source_file: Any = None,
    include_in_core_price_monitor: bool = True,
    selected_regions: Any = None,
    selected_android_versions: Any = None,
    region_price_selection_rule: Any = None,
    stock_status: Any = None,
    actual_duration_days: Any = None,
    actual_duration_display: Any = None,
    comparison_duration_note: Any = None,
) -> None:
    price_value = parse_float_value(price)
    if price_value is None or not is_iso_date_label(date):
        return
    platform_name = normalize_platform_name(platform)
    product_key = normalize_series_product(product_model)
    bucket_key = str(bucket)
    if not platform_name or not product_key or bucket_key in {"", "unknown"}:
        return
    point = {
        "date": date,
        "price": json_safe(price_value),
        "price_source": source,
        "platform": platform_name,
        "product_model": normalize_display_text(product_model),
        "config_signature": config_signature,
        "duration_bucket": bucket_key,
        "price_variant": price_variant,
        "price_variant_label": price_variant_label,
        "device_count": json_safe(device_count),
        "package_total_price": json_safe(package_total_price),
        "promotion_text": json_safe(promotion_text),
        "source_run_dir": json_safe(source_run_dir),
        "source_file": json_safe(source_file),
        "include_in_core_price_monitor": bool(include_in_core_price_monitor),
        "selected_regions": json_safe(selected_regions),
        "selected_android_versions": json_safe(selected_android_versions),
        "region_price_selection_rule": json_safe(region_price_selection_rule),
        "stock_status": json_safe(stock_status),
        "actual_duration_days": json_safe(actual_duration_days),
        "actual_duration_display": json_safe(actual_duration_display),
        "comparison_duration_note": json_safe(comparison_duration_note),
    }
    strict_key = (platform_name, product_key, config_signature, bucket_key)
    loose_key = (platform_name, product_key, bucket_key)

    def choose(existing: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, Any]:
        if not existing:
            return new
        existing_rank = variant_sort_rank(existing.get("price_variant"))
        new_rank = variant_sort_rank(new.get("price_variant"))
        if new_rank < existing_rank:
            return new
        if new_rank > existing_rank:
            return existing
        # Same variant rank: use the lower actually payable price for the same day/config.
        try:
            return new if float(new.get("price")) < float(existing.get("price")) else existing
        except Exception:
            return new

    current_strict = history.setdefault(strict_key, {}).get(date)
    history[strict_key][date] = choose(current_strict, point)
    current_loose = loose_history.setdefault(loose_key, {}).get(date)
    loose_history[loose_key][date] = choose(current_loose, point)



def add_regional_history_point(
    regional_history: dict[tuple[str, str, str, str], dict[str, dict[str, dict[str, Any]]]],
    regional_loose_history: dict[tuple[str, str, str], dict[str, dict[str, dict[str, Any]]]],
    *,
    platform: Any,
    product_model: Any,
    config_signature: str,
    bucket: Any,
    region: Any,
    date: str,
    price: Any,
    source: str,
    price_variant: str = "regular",
    price_variant_label: str = "日常实付价",
    device_count: int = 1,
    package_total_price: Any = None,
    promotion_text: Any = None,
    source_run_dir: Any = None,
    source_file: Any = None,
    stock_status: Any = None,
    actual_duration_days: Any = None,
    actual_duration_display: Any = None,
    comparison_duration_note: Any = None,
    selected_android_versions: Any = None,
) -> None:
    price_value = parse_float_value(price)
    region_label = normalize_region_label(region)
    if price_value is None or not is_iso_date_label(date) or not region_label:
        return
    platform_name = normalize_platform_name(platform)
    product_key = normalize_series_product(product_model)
    bucket_key = str(bucket)
    if not platform_name or not product_key or bucket_key in {"", "unknown"}:
        return
    point = {
        "date": date,
        "price": json_safe(price_value),
        "price_source": source,
        "platform": platform_name,
        "product_model": normalize_display_text(product_model),
        "config_signature": config_signature,
        "duration_bucket": bucket_key,
        "machine_room_region": region_label,
        "price_variant": price_variant,
        "price_variant_label": price_variant_label,
        "device_count": json_safe(device_count),
        "package_total_price": json_safe(package_total_price),
        "promotion_text": json_safe(promotion_text),
        "source_run_dir": json_safe(source_run_dir),
        "source_file": json_safe(source_file),
        "stock_status": json_safe(stock_status),
        "actual_duration_days": json_safe(actual_duration_days),
        "actual_duration_display": json_safe(actual_duration_display),
        "comparison_duration_note": json_safe(comparison_duration_note),
        "selected_android_versions": json_safe(selected_android_versions),
        "region_price_selection_rule": "按所选机房/地区展示该地区当前可购买单设备实付价；新客价、无库存、不可购买价格不参与该机房趋势。",
    }
    strict_key = (platform_name, product_key, config_signature, bucket_key)
    loose_key = (platform_name, product_key, bucket_key)

    def choose(existing: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, Any]:
        if not existing:
            return new
        existing_rank = variant_sort_rank(existing.get("price_variant"))
        new_rank = variant_sort_rank(new.get("price_variant"))
        if new_rank < existing_rank:
            return new
        if new_rank > existing_rank:
            return existing
        try:
            return new if float(new.get("price")) < float(existing.get("price")) else existing
        except Exception:
            return new

    regional_history.setdefault(strict_key, {}).setdefault(region_label, {})[date] = choose(
        regional_history.setdefault(strict_key, {}).setdefault(region_label, {}).get(date), point
    )
    regional_loose_history.setdefault(loose_key, {}).setdefault(region_label, {})[date] = choose(
        regional_loose_history.setdefault(loose_key, {}).setdefault(region_label, {}).get(date), point
    )


def read_products_history_frame(run_dir: Path) -> pd.DataFrame:
    """Read a historical products table quickly.

    Most historical output directories contain products.csv; some only have
    products.xlsx.  Trend history should not depend on historical
    price_trends.json being present, because older runs did not generate it.
    """
    csv_path = run_dir / "products.csv"
    if csv_path.exists():
        try:
            return pd.read_csv(csv_path, dtype=object)
        except Exception:
            pass
    xlsx_path = run_dir / "products.xlsx"
    if xlsx_path.exists():
        try:
            # products.xlsx may contain multiple sheets; reading all sheets is slower,
            # so first try the first sheet and fall back to all sheets only if needed.
            frame = pd.read_excel(xlsx_path, dtype=object)
            if not frame.empty:
                return frame
        except Exception:
            try:
                sheets = pd.read_excel(xlsx_path, sheet_name=None, dtype=object)
                frames = [df for df in sheets.values() if isinstance(df, pd.DataFrame) and not df.empty]
                if frames:
                    return pd.concat(frames, ignore_index=True)
            except Exception:
                pass
    return pd.DataFrame()


def collect_history_from_products(
    run_dir: Path,
    date: str,
    history: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]],
    loose_history: dict[tuple[str, str, str], dict[str, dict[str, Any]]],
    other_paid_prices: list[dict[str, Any]],
    regional_history: dict[tuple[str, str, str, str], dict[str, dict[str, dict[str, Any]]]],
    regional_loose_history: dict[tuple[str, str, str], dict[str, dict[str, dict[str, Any]]]],
    android_history: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]] | None = None,
    android_loose_history: dict[tuple[str, str, str], dict[str, dict[str, Any]]] | None = None,
    android_regional_history: dict[tuple[str, str, str, str], dict[str, dict[str, dict[str, Any]]]] | None = None,
    android_regional_loose_history: dict[tuple[str, str, str], dict[str, dict[str, dict[str, Any]]]] | None = None,
) -> int:
    """Read one day's products table and add one clean price point per product line.

    Core rule: if the same platform/product/duration has different machine-room
    prices, use the majority-region currently purchasable single-device paid
    price. If region counts tie, the lower price wins. Minority region prices and
    unavailable-region prices are retained as secondary context.
    """
    frame = read_products_history_frame(run_dir)
    if frame.empty:
        return 0
    rename_map = {cn: en for cn, en in PRODUCT_COLS.items() if cn in frame.columns}
    if rename_map:
        frame = frame.rename(columns=rename_map)
    required = {"platform", "product_model", "duration", "price"}
    if not required.issubset(set(frame.columns)):
        return 0

    source_file = "products.csv" if (run_dir / "products.csv").exists() else "products.xlsx"
    candidate_groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    android_candidate_groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}

    for _, row in frame.iterrows():
        platform = normalize_platform_name(row.get("platform"))
        product_model = row.get("product_model")
        product_key = normalize_series_product(product_model)
        duration_info = normalize_comparison_duration_info(platform, row.get("duration"))
        bucket = duration_info.get("duration_bucket")
        if bucket in {None, "", "unknown"}:
            continue
        promotion_text = row.get("promotion_text")
        raw_text = row.get("raw_text")
        variant = classify_price_variant(promotion_text, raw_text, row.get("duration"))
        total_price = parse_float_value(row.get("price"))
        unit_price = normalize_price_for_variant(total_price, variant)
        if unit_price is None:
            continue
        unavailable = is_unavailable_product_row(row)
        region_text = row_region_text(row)
        android_version = android_version_from_row(row)
        signature_no_android = config_signature_without_android_from_product_row(row)
        signature_full = config_signature_from_product_row(row)
        common = {
            "date": date,
            "platform": platform,
            "product_model": normalize_display_text(product_model),
            "device_model": json_safe(row.get("device_model")),
            "android_version": json_safe(row.get("android_version")),
            "cpu": json_safe(row.get("cpu")),
            "ram": json_safe(row.get("ram")),
            "storage": json_safe(row.get("storage")),
            "config_signature": signature_full,
            "config_signature_no_android": signature_no_android,
            "duration_bucket": json_safe(bucket),
            "duration_display": duration_info.get("duration_display"),
            "actual_duration_days": duration_info.get("actual_duration_days"),
            "actual_duration_display": duration_info.get("actual_duration_display"),
            "comparison_duration_note": duration_info.get("comparison_duration_note"),
            "raw_price": json_safe(total_price),
            "unit_device_price": json_safe(unit_price),
            "currency": json_safe(row.get("currency")),
            "promotion_text": json_safe(promotion_text),
            "price_variant": variant["price_variant"],
            "price_variant_label": variant["price_variant_label"],
            "device_count": variant["device_count"],
            "include_in_core_price_monitor": variant["include_in_core_price_monitor"],
            "variant_exclusion_reason": variant["variant_exclusion_reason"],
            "source_run_dir": str(run_dir.as_posix()),
            "source_file": source_file,
            "supported_server_regions": json_safe(row.get("supported_server_regions")),
            "server_region": json_safe(row.get("server_region")),
            "selected_regions": region_text,
            "selected_android_versions": android_version,
            "stock_status": json_safe(row.get("stock_status")),
            "is_unavailable_region_price": unavailable,
        }

        if is_single_device_payable_variant(variant):
            key = (platform, product_key, str(bucket), signature_no_android)
            candidate_groups.setdefault(key, []).append(common)
            android_key = (platform, product_key, str(bucket), signature_full)
            android_candidate_groups.setdefault(android_key, []).append(common)
        elif is_majority_region_activity_override_candidate(common):
            # Narrow override: let UgPhone GVIP 30-day activity rows compete in
            # the region-majority selector.  This prevents one minority machine
            # room price from becoming the core line while the real majority
            # purchasable price is 7.99.
            override = dict(common)
            override["price_variant_original"] = override.get("price_variant")
            override["price_variant"] = "public_offer"
            override["price_variant_label"] = PRICE_VARIANT_LABELS["public_offer"]
            override["include_in_core_price_monitor"] = True
            override["variant_exclusion_reason"] = ""
            override["price_variant_override_reason"] = "ugphone_gvip_30_majority_region_activity_price"
            key = (platform, product_key, str(bucket), signature_no_android)
            candidate_groups.setdefault(key, []).append(override)
            android_key = (platform, product_key, str(bucket), signature_full)
            android_candidate_groups.setdefault(android_key, []).append(override)
        else:
            other_paid_prices.append(common)

    added = 0
    for (platform, product_key, bucket_key, signature_no_android), candidates in candidate_groups.items():
        purchasable = [row for row in candidates if not row.get("is_unavailable_region_price")]
        if not purchasable:
            for row in candidates:
                contextual = dict(row)
                contextual["price_variant"] = "unavailable_region_price"
                contextual["price_variant_label"] = PRICE_VARIANT_LABELS["unavailable_region_price"]
                contextual["variant_exclusion_reason"] = "unavailable_region_price_not_core"
                contextual["include_in_core_price_monitor"] = False
                other_paid_prices.append(contextual)
            continue

        price_groups: dict[float, list[dict[str, Any]]] = {}
        for row in purchasable:
            key_price = price_bucket_key(row.get("unit_device_price"))
            if key_price is None:
                continue
            price_groups.setdefault(key_price, []).append(row)
        if not price_groups:
            continue

        # Export machine-room-level trend points before the majority-region
        # selector collapses the product into one core price.  A grouped row such
        # as "Hong Kong; Singapore" is expanded to one point for each region.
        for candidate in purchasable:
            for region in split_region_values(candidate.get("selected_regions")):
                add_regional_history_point(
                    regional_history,
                    regional_loose_history,
                    platform=platform,
                    product_model=candidate.get("product_model") or product_key,
                    config_signature=signature_no_android,
                    bucket=bucket_key,
                    region=region,
                    date=date,
                    price=candidate.get("unit_device_price"),
                    source="historical_products_region_paid_price",
                    price_variant=candidate.get("price_variant") or "regular",
                    price_variant_label=candidate.get("price_variant_label") or PRICE_VARIANT_LABELS["regular"],
                    device_count=candidate.get("device_count") or 1,
                    package_total_price=candidate.get("raw_price"),
                    promotion_text=candidate.get("promotion_text"),
                    source_run_dir=candidate.get("source_run_dir"),
                    source_file=candidate.get("source_file"),
                    stock_status=candidate.get("stock_status"),
                    actual_duration_days=candidate.get("actual_duration_days"),
                    actual_duration_display=candidate.get("actual_duration_display"),
                    comparison_duration_note=candidate.get("comparison_duration_note"),
                )

        def group_region_count(group_rows: list[dict[str, Any]]) -> int:
            return sum(region_count_for_selection(row.get("selected_regions")) for row in group_rows)

        selected_price, selected = sorted(
            price_groups.items(),
            key=lambda item: (
                -group_region_count(item[1]),   # price used by most machine rooms first
                float(item[0]),                 # if tied, choose the lower price
                min(variant_sort_rank(row.get("price_variant")) for row in item[1]),
            ),
        )[0]
        selected_region_count = group_region_count(selected)
        total_region_count = sum(group_region_count(rows) for rows in price_groups.values())
        representative = sorted(selected, key=lambda row: (variant_sort_rank(row.get("price_variant")), str(row.get("selected_regions") or "")))[0]
        selected_regions = sorted({region for row in selected for region in split_region_values(row.get("selected_regions"))})
        selected_androids = sorted({normalize_display_text(row.get("selected_android_versions")) for row in selected if normalize_display_text(row.get("selected_android_versions")) and normalize_display_text(row.get("selected_android_versions")).lower() not in {"none", "nan"}}, key=android_version_sort_key)

        add_history_point(
            history,
            loose_history,
            platform=platform,
            product_model=representative.get("product_model") or product_key,
            config_signature=signature_no_android,
            bucket=bucket_key,
            date=date,
            price=selected_price,
            source="historical_products_majority_region_paid_price",
            price_variant=representative.get("price_variant") or "regular",
            price_variant_label=representative.get("price_variant_label") or PRICE_VARIANT_LABELS["regular"],
            device_count=representative.get("device_count") or 1,
            package_total_price=representative.get("raw_price"),
            promotion_text=representative.get("promotion_text"),
            source_run_dir=representative.get("source_run_dir"),
            source_file=representative.get("source_file"),
            include_in_core_price_monitor=True,
            selected_regions="; ".join(selected_regions),
            selected_android_versions="/".join(selected_androids),
            region_price_selection_rule=f"同产品/同购买天数/同非Android配置存在多机房价格时，选择覆盖机房数量最多的当前可购买单设备实付价；若价格覆盖数量持平，选择低价。当前选择 {selected_price:g}，覆盖 {selected_region_count}/{total_region_count} 个机房/地区；新客价、无库存、不可购买价格不参与核心趋势。",
            stock_status=representative.get("stock_status"),
            actual_duration_days=representative.get("actual_duration_days"),
            actual_duration_display=representative.get("actual_duration_display"),
            comparison_duration_note=representative.get("comparison_duration_note"),
        )
        added += 1

        for row in candidates:
            if row in selected:
                if row.get("price_variant") in NON_CORE_PRICE_VARIANTS:
                    other_paid_prices.append(dict(row))
                continue
            contextual = dict(row)
            if contextual.get("is_unavailable_region_price"):
                contextual["price_variant"] = "unavailable_region_price"
                contextual["price_variant_label"] = PRICE_VARIANT_LABELS["unavailable_region_price"]
                contextual["variant_exclusion_reason"] = "unavailable_region_price_not_core"
            else:
                contextual["price_variant"] = "minority_region_price"
                contextual["price_variant_label"] = PRICE_VARIANT_LABELS["minority_region_price"]
                contextual["variant_exclusion_reason"] = "minority_region_price_not_core_majority_selected"
            contextual["include_in_core_price_monitor"] = False
            other_paid_prices.append(contextual)


    if all(map(lambda value: value is not None, [android_history, android_loose_history, android_regional_history, android_regional_loose_history])):
        for (platform, product_key, bucket_key, signature_full), candidates in android_candidate_groups.items():
            purchasable = [row for row in candidates if not row.get("is_unavailable_region_price")]
            if not purchasable:
                continue

            price_groups: dict[float, list[dict[str, Any]]] = {}
            for row in purchasable:
                key_price = price_bucket_key(row.get("unit_device_price"))
                if key_price is None:
                    continue
                price_groups.setdefault(key_price, []).append(row)
            if not price_groups:
                continue

            for candidate in purchasable:
                for region in split_region_values(candidate.get("selected_regions")):
                    add_regional_history_point(
                        android_regional_history,
                        android_regional_loose_history,
                        platform=platform,
                        product_model=candidate.get("product_model") or product_key,
                        config_signature=signature_full,
                        bucket=bucket_key,
                        region=region,
                        date=date,
                        price=candidate.get("unit_device_price"),
                        source="historical_products_android_region_paid_price",
                        price_variant=candidate.get("price_variant") or "regular",
                        price_variant_label=candidate.get("price_variant_label") or PRICE_VARIANT_LABELS["regular"],
                        device_count=candidate.get("device_count") or 1,
                        package_total_price=candidate.get("raw_price"),
                        promotion_text=candidate.get("promotion_text"),
                        source_run_dir=candidate.get("source_run_dir"),
                        source_file=candidate.get("source_file"),
                        stock_status=candidate.get("stock_status"),
                        actual_duration_days=candidate.get("actual_duration_days"),
                        actual_duration_display=candidate.get("actual_duration_display"),
                        comparison_duration_note=candidate.get("comparison_duration_note"),
                        selected_android_versions=candidate.get("selected_android_versions"),
                    )

            def group_region_count(group_rows: list[dict[str, Any]]) -> int:
                return sum(region_count_for_selection(row.get("selected_regions")) for row in group_rows)

            selected_price, selected = sorted(
                price_groups.items(),
                key=lambda item: (
                    -group_region_count(item[1]),
                    float(item[0]),
                    min(variant_sort_rank(row.get("price_variant")) for row in item[1]),
                ),
            )[0]
            selected_region_count = group_region_count(selected)
            total_region_count = sum(group_region_count(rows) for rows in price_groups.values())
            representative = sorted(selected, key=lambda row: (variant_sort_rank(row.get("price_variant")), str(row.get("selected_regions") or "")))[0]
            selected_regions = sorted({region for row in selected for region in split_region_values(row.get("selected_regions"))})
            selected_androids = sorted({normalize_display_text(row.get("selected_android_versions")) for row in selected if normalize_display_text(row.get("selected_android_versions")) and normalize_display_text(row.get("selected_android_versions")).lower() not in {"none", "nan"}}, key=android_version_sort_key)

            add_history_point(
                android_history,
                android_loose_history,
                platform=platform,
                product_model=representative.get("product_model") or product_key,
                config_signature=signature_full,
                bucket=bucket_key,
                date=date,
                price=selected_price,
                source="historical_products_android_majority_region_paid_price",
                price_variant=representative.get("price_variant") or "regular",
                price_variant_label=representative.get("price_variant_label") or PRICE_VARIANT_LABELS["regular"],
                device_count=representative.get("device_count") or 1,
                package_total_price=representative.get("raw_price"),
                promotion_text=representative.get("promotion_text"),
                source_run_dir=representative.get("source_run_dir"),
                source_file=representative.get("source_file"),
                include_in_core_price_monitor=True,
                selected_regions="; ".join(selected_regions),
                selected_android_versions="/".join(selected_androids),
                region_price_selection_rule=f"同产品/同购买天数/同Android版本/同配置存在多机房价格时，选择覆盖机房数量最多的当前可购买单设备实付价；若价格覆盖数量持平，选择低价。当前选择 {selected_price:g}，覆盖 {selected_region_count}/{total_region_count} 个机房/地区；新客价、无库存、不可购买价格不参与核心趋势。",
                stock_status=representative.get("stock_status"),
                actual_duration_days=representative.get("actual_duration_days"),
                actual_duration_display=representative.get("actual_duration_display"),
                comparison_duration_note=representative.get("comparison_duration_note"),
            )

    return added


def latest_unique_other_paid_prices(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only the latest-date non-core paid prices and deduplicate identical offers.

    The frontend should not show a long historical audit table here.  Other paid
    prices are contextual evidence (new-user price, trial price, multi-device
    pack, channel flash sale), so showing the latest current snapshot is enough
    and prevents repeated rows from different historical dates from crowding the
    product-line detail table.
    """
    if not rows:
        return []
    dated = [row for row in rows if is_iso_date_label(row.get("date"))]
    if dated:
        latest_date = max(str(row.get("date")) for row in dated)
        rows = [row for row in rows if str(row.get("date")) == latest_date]
    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = (
            normalize_platform_name(row.get("platform")),
            normalize_display_text(row.get("product_model")),
            str(row.get("duration_bucket")),
            normalize_display_text(row.get("duration_display")),
            normalize_display_text(row.get("price_variant")),
            parse_float_value(row.get("raw_price")),
            parse_float_value(row.get("unit_device_price")),
            row.get("device_count"),
            normalize_display_text(row.get("promotion_text")),
        )
        if key not in deduped:
            row = dict(row)
            row["latest_only"] = True
            row["duplicate_policy"] = "latest_date_unique_offer"
            deduped[key] = row
    return sorted(
        deduped.values(),
        key=lambda row: (
            str(row.get("date") or ""),
            (ALL_PLATFORMS.index(normalize_platform_name(row.get("platform"))) if normalize_platform_name(row.get("platform")) in ALL_PLATFORMS else 99),
            str(row.get("product_model") or ""),
            str(row.get("duration_bucket") or ""),
            variant_sort_rank(row.get("price_variant")),
            parse_float_value(row.get("unit_device_price")) or 0,
        ),
    )

def collect_history_from_price_trends(
    run_dir: Path,
    history: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]],
    loose_history: dict[tuple[str, str, str], dict[str, dict[str, Any]]],
) -> None:
    trends_path = run_dir / "dashboard_data" / "price_trends.json"
    if not trends_path.exists():
        return
    try:
        payload = json.loads(trends_path.read_text(encoding="utf-8"))
    except Exception:
        return
    series_rows = payload.get("series") if isinstance(payload, dict) else payload
    if not isinstance(series_rows, list):
        return
    for item in series_rows:
        if not isinstance(item, dict):
            continue
        platform = normalize_platform_name(item.get("platform"))
        product_model = item.get("product_model")
        stale_bucket = item.get("duration_bucket")
        migrated_duration_info = canonical_duration_info_from_fields(
            item.get("actual_duration_days"),
            item.get("duration_days"),
            item.get("actual_duration_display"),
            item.get("duration_display"),
            f"{stale_bucket} day" if str(stale_bucket).isdigit() else None,
        )
        if migrated_duration_info:
            bucket = migrated_duration_info.get("duration_bucket")
            duration_display = migrated_duration_info.get("duration_display")
            actual_duration_days = migrated_duration_info.get("duration_days")
            actual_duration_display = migrated_duration_info.get("duration_display")
        else:
            bucket = stale_bucket
            duration_display = item.get("duration_display")
            actual_duration_days = item.get("actual_duration_days")
            actual_duration_display = item.get("actual_duration_display")
        signature = normalize_config_signature(item.get("config"))
        for point in item.get("points") or []:
            if not isinstance(point, dict):
                continue
            date = point.get("date")
            if not is_iso_date_label(date):
                continue
            add_history_point(
                history,
                loose_history,
                platform=platform,
                product_model=product_model,
                config_signature=signature,
                bucket=bucket,
                date=date,
                price=point.get("price"),
                source=point.get("price_source") or "historical_trend",
                actual_duration_days=actual_duration_days,
                actual_duration_display=actual_duration_display,
                comparison_duration_note=item.get("comparison_duration_note"),
            )


def collect_history_from_quality_report(
    run_dir: Path,
    date: str,
    history: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]],
    loose_history: dict[tuple[str, str, str], dict[str, dict[str, Any]]],
) -> None:
    report_path = run_dir / "quality_price_report.xlsx"
    if not report_path.exists():
        return
    details = read_excel_sheet(report_path, "质量调整价格明细", QUALITY_COLS)
    if details.empty:
        return
    for _, row in details.iterrows():
        ug_duration = row.get("duration_days")
        duration_info = parse_duration_info(f"{ug_duration} day" if not pd.isna(ug_duration) else "")
        bucket = duration_info.get("duration_bucket")
        if bucket in {None, "", "unknown"}:
            continue
        ug_price = reconstruct_price(row.get("ug_effective_price_30d"), ug_duration)
        add_history_point(
            history,
            loose_history,
            platform=BASE_PLATFORM,
            product_model=row.get("ug_product_model"),
            config_signature=normalize_config_signature(row.get("ug_config")),
            bucket=bucket,
            date=date,
            price=ug_price,
            source="historical_quality_report",
        )
        competitor_platform = row.get("competitor_platform")
        competitor_model = row.get("competitor_product_model")
        competitor_price = reconstruct_price(row.get("competitor_effective_price_30d"), row.get("competitor_duration_days"))
        add_history_point(
            history,
            loose_history,
            platform=competitor_platform,
            product_model=competitor_model,
            config_signature=normalize_config_signature(row.get("competitor_config")),
            bucket=bucket,
            date=date,
            price=competitor_price,
            source="historical_quality_report",
        )


def collect_historical_trend_points(current_output_dir: Path) -> tuple[
    dict[tuple[str, str, str, str], dict[str, dict[str, Any]]],
    dict[tuple[str, str, str], dict[str, dict[str, Any]]],
    list[dict[str, Any]],
    dict[tuple[str, str, str, str], dict[str, dict[str, dict[str, Any]]]],
    dict[tuple[str, str, str], dict[str, dict[str, dict[str, Any]]]],
    dict[tuple[str, str, str, str], dict[str, dict[str, Any]]],
    dict[tuple[str, str, str], dict[str, dict[str, Any]]],
    dict[tuple[str, str, str, str], dict[str, dict[str, dict[str, Any]]]],
    dict[tuple[str, str, str], dict[str, dict[str, dict[str, Any]]]],
]:
    """Collect daily historical prices from prior output/cloud_phone_monitor_* runs.

    Important behavior:
    - History is reconstructed primarily from products.csv/products.xlsx, because
      old runs usually do not have dashboard_data/price_trends.json.
    - Only the latest successful run for each calendar day is used. This prevents
      dozens of runs on the same day from overwriting each other unpredictably and
      makes the trend chart show one point per day.
    - Historical quality_price_report.xlsx is intentionally not scanned for every
      run here; reading many Excel reports is slow and was a major reason the
      trend export appeared to do nothing. The current run's quality report is
      still used to define paired product lines; history points come from the
      daily products table.
    """
    history: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]] = {}
    loose_history: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = {}
    other_paid_prices: list[dict[str, Any]] = []
    regional_history: dict[tuple[str, str, str, str], dict[str, dict[str, dict[str, Any]]]] = {}
    regional_loose_history: dict[tuple[str, str, str], dict[str, dict[str, dict[str, Any]]]] = {}
    android_history: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]] = {}
    android_loose_history: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = {}
    android_regional_history: dict[tuple[str, str, str, str], dict[str, dict[str, dict[str, Any]]]] = {}
    android_regional_loose_history: dict[tuple[str, str, str], dict[str, dict[str, dict[str, Any]]]] = {}

    # Keep only the latest usable run for each day.
    runs_by_date: dict[str, Path] = {}
    for run_dir in iter_history_output_dirs(current_output_dir):
        date = output_run_date(run_dir)
        if not date:
            continue
        if not ((run_dir / "products.csv").exists() or (run_dir / "products.xlsx").exists() or (run_dir / "dashboard_data" / "price_trends.json").exists()):
            continue
        runs_by_date[date] = run_dir

    for date, run_dir in sorted(runs_by_date.items()):
        # Prefer products.csv/products.xlsx because they allow us to classify price
        # variants and exclude new-user / flash / multi-device package prices from
        # core monitoring.  Old price_trends.json may already be contaminated by
        # those variants, so only use it when the run has no readable products table.
        added = collect_history_from_products(
            run_dir,
            date,
            history,
            loose_history,
            other_paid_prices,
            regional_history,
            regional_loose_history,
            android_history,
            android_loose_history,
            android_regional_history,
            android_regional_loose_history,
        )
        if added == 0:
            collect_history_from_price_trends(run_dir, history, loose_history)
            collect_history_from_quality_report(run_dir, date, history, loose_history)
    other_paid_prices.sort(key=lambda row: (str(row.get("date") or ""), str(row.get("platform") or ""), str(row.get("product_model") or ""), str(row.get("duration_bucket") or ""), variant_sort_rank(row.get("price_variant"))))
    return (
        history,
        loose_history,
        latest_unique_other_paid_prices(other_paid_prices),
        regional_history,
        regional_loose_history,
        android_history,
        android_loose_history,
        android_regional_history,
        android_regional_loose_history,
    )

def merge_series_points(
    base_points: list[dict[str, Any]],
    history_points: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for point in history_points.values():
        date = point.get("date")
        if is_iso_date_label(date):
            by_date[str(date)] = {**point, "date": str(date), "price": json_safe(point.get("price")), "price_source": point.get("price_source") or "historical"}
    previous_points: list[dict[str, Any]] = []
    for point in base_points:
        date = str(point.get("date") or "")
        if is_iso_date_label(date):
            if date not in by_date:
                by_date[date] = {"date": date, "price": json_safe(point.get("price")), "price_source": point.get("price_source") or "current"}
        elif date == "previous":
            previous_points.append(point)
    real_points = [by_date[key] for key in sorted(by_date)]
    if len(real_points) >= 2:
        return real_points
    # Only keep the synthetic Previous point when no real daily history exists yet.
    return [*previous_points, *real_points]






def merge_regional_points_map(
    regional_points: dict[str, dict[str, dict[str, Any]]] | None,
) -> dict[str, list[dict[str, Any]]]:
    if not regional_points:
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    for region, points_by_date in regional_points.items():
        region_label = normalize_region_label(region)
        if not region_label or not isinstance(points_by_date, dict):
            continue
        points = merge_series_points([], points_by_date)
        if any(point.get("price") is not None for point in points):
            result[region_label] = points
    return dict(sorted(result.items(), key=lambda item: item[0]))


def merge_regional_points_for_android_group(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, dict[str, list[tuple[dict[str, Any], dict[str, Any]]]]] = {}
    for series in items:
        for region, points in (series.get("regional_points") or {}).items():
            region_label = normalize_region_label(region)
            if not region_label:
                continue
            for point in stable_list(points):
                if not isinstance(point, dict) or not is_iso_date_label(point.get("date")):
                    continue
                grouped.setdefault(region_label, {}).setdefault(str(point.get("date")), []).append((point, series))

    merged: dict[str, list[dict[str, Any]]] = {}
    for region, date_map in grouped.items():
        region_points: list[dict[str, Any]] = []
        for date, entries in sorted(date_map.items()):
            by_price: dict[str, dict[str, Any]] = {}
            for point, series in entries:
                price = parse_float_value(point.get("price"))
                if price is None:
                    continue
                key = f"{price:.6f}"
                current = by_price.setdefault(key, {"price": price, "weight": 0, "points": []})
                current["weight"] += int(series.get("merged_series_count") or 1)
                current["points"].append(point)
            if not by_price:
                continue
            chosen = sorted(by_price.values(), key=lambda item: (-item["weight"], item["price"]))[0]
            representative = sorted(chosen["points"], key=lambda point: (variant_sort_rank(point.get("price_variant")), str(point.get("price_source") or "")))[0]
            merged_point = dict(representative)
            merged_point["date"] = date
            merged_point["price"] = json_safe(chosen["price"])
            merged_point["android_merge_weight"] = json_safe(chosen["weight"])
            region_points.append(merged_point)
        if region_points:
            merged[region] = region_points
    return dict(sorted(merged.items(), key=lambda item: item[0]))


def stable_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def iso_date_range(start_date: str, end_date: str) -> list[str]:
    """Return each natural day between start_date and end_date, inclusive."""
    if not (is_iso_date_label(start_date) and is_iso_date_label(end_date)):
        return []
    try:
        start = datetime.fromisoformat(str(start_date)).date()
        end = datetime.fromisoformat(str(end_date)).date()
    except Exception:
        return []
    if end < start:
        return []
    days: list[str] = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def fill_points_by_natural_days(points: list[dict[str, Any]], date_range: list[str]) -> list[dict[str, Any]]:
    """Render on a natural-day x-axis while keeping collection-day data.

    Exact collection dates keep their original point. Missing natural days carry
    forward the previous valid collected price. This means hovering over a
    non-collection date such as 2026-05-01 will show the latest real price from
    2026-04-30, with price_source=carry_forward and carried_from_date recorded.
    """
    if not date_range:
        return points
    by_date: dict[str, dict[str, Any]] = {}
    for point in points:
        date = str(point.get("date") or "")
        if is_iso_date_label(date):
            existing = by_date.get(date)
            if existing is None or point.get("price") is not None:
                by_date[date] = {**point, "date": date}
    filled: list[dict[str, Any]] = []
    last_valid: dict[str, Any] | None = None
    for date in date_range:
        raw = by_date.get(date)
        if raw is not None:
            point = dict(raw)
            if point.get("price") is not None:
                point.setdefault("source_collection_date", date)
                point.setdefault("carried_from_date", date)
                last_valid = point
            filled.append(point)
            continue
        if last_valid is not None and last_valid.get("price") is not None:
            origin_date = last_valid.get("source_collection_date") or last_valid.get("carried_from_date") or last_valid.get("date")
            carried = dict(last_valid)
            carried.update({
                "date": date,
                "price": json_safe(last_valid.get("price")),
                "price_source": "carry_forward",
                "source_collection_date": origin_date,
                "carried_from_date": origin_date,
                "source_price_source": last_valid.get("price_source"),
                "carry_forward_note": "当天没有采集数据，沿用上一采集日有效价格。",
            })
            filled.append(carried)
        else:
            filled.append({
                "date": date,
                "price": None,
                "price_source": "missing",
                "missing_reason": "no_previous_collection_price",
            })
    return filled


def apply_natural_day_axis(series: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fill each series to every natural day between the first and latest collection date."""
    raw_dates = sorted({
        str(point.get("date"))
        for item in series
        for point in item.get("points", [])
        if is_iso_date_label(point.get("date")) and point.get("price_source") != "carry_forward"
    })
    if not raw_dates:
        return series, {
            "history_start_date": None,
            "history_end_date": None,
            "raw_collection_dates": [],
            "filled_dates": [],
            "natural_history_dates": [],
            "date_fill_mode": "collection_days_only_no_raw_dates",
        }
    date_range = iso_date_range(raw_dates[0], raw_dates[-1])
    raw_set = set(raw_dates)
    filled_dates = [date for date in date_range if date not in raw_set]
    for item in series:
        item["raw_collection_dates"] = raw_dates
        item["points"] = fill_points_by_natural_days(item.get("points") or [], date_range)
        regional_points = item.get("regional_points") if isinstance(item.get("regional_points"), dict) else {}
        if regional_points:
            item["regional_points"] = {
                normalize_region_label(region): fill_points_by_natural_days(points or [], date_range)
                for region, points in sorted(regional_points.items(), key=lambda pair: normalize_region_label(pair[0]))
                if normalize_region_label(region)
            }
            item["available_regions"] = sorted(item["regional_points"].keys())
        android_children = []
        for child in stable_list(item.get("android_breakdown_series")):
            if not isinstance(child, dict):
                continue
            child = dict(child)
            child["raw_collection_dates"] = raw_dates
            child["points"] = fill_points_by_natural_days(child.get("points") or [], date_range)
            child_regional_points = child.get("regional_points") if isinstance(child.get("regional_points"), dict) else {}
            if child_regional_points:
                child["regional_points"] = {
                    normalize_region_label(region): fill_points_by_natural_days(points or [], date_range)
                    for region, points in sorted(child_regional_points.items(), key=lambda pair: normalize_region_label(pair[0]))
                    if normalize_region_label(region)
                }
                child["available_regions"] = sorted(child["regional_points"].keys())
            child["date_fill_mode"] = "natural_day_axis_with_collection_day_carry_forward"
            update_series_stats_from_points(child)
            android_children.append(child)
        if android_children:
            item["android_breakdown_series"] = android_children
        item["date_fill_mode"] = "natural_day_axis_with_collection_day_carry_forward"
        update_series_stats_from_points(item)
    return series, {
        "history_start_date": raw_dates[0],
        "history_end_date": raw_dates[-1],
        "raw_collection_dates": raw_dates,
        "filled_dates": filled_dates,
        "natural_history_dates": date_range,
        "date_fill_mode": "natural_day_axis_with_collection_day_carry_forward",
    }


def update_series_stats_from_points(item: dict[str, Any]) -> None:
    points = [point for point in (item.get("points") or []) if is_iso_date_label(point.get("date")) and point.get("price") is not None]
    points = sorted(points, key=lambda point: point.get("date"))
    if not points:
        return

    # Natural-day points include carry_forward values.  They are useful for
    # display, but they must not hide whether the product actually changed on
    # real collection days.  Keep two sets of statistics:
    #   1) current/previous: for the rendered natural-day chart
    #   2) collection_*: for audit and for explaining whether historical output
    #      really contains price changes.
    current = points[-1].get("price")
    previous = points[-2].get("price") if len(points) >= 2 else item.get("previous_price")
    item["current_price"] = json_safe(current)
    item["previous_price"] = json_safe(previous)
    if current is not None and previous not in {None, 0}:
        item["price_change_pct"] = json_safe((float(current) - float(previous)) / float(previous))

    collection_points = [point for point in points if point.get("price_source") != "carry_forward"]
    # If a series only has carried values for some reason, fall back to all points.
    if not collection_points:
        collection_points = points
    collection_points = sorted(collection_points, key=lambda point: point.get("date"))
    collection_prices = [float(point["price"]) for point in collection_points if point.get("price") is not None]
    distinct_prices = sorted({round(price, 6) for price in collection_prices})
    item["valid_collection_point_count"] = len(collection_points)
    item["distinct_price_count"] = len(distinct_prices)
    item["has_price_change"] = len(distinct_prices) > 1
    if collection_points:
        first = collection_points[0]
        last = collection_points[-1]
        first_price = parse_float_value(first.get("price"))
        last_price = parse_float_value(last.get("price"))
        item["first_valid_date"] = json_safe(first.get("date"))
        item["first_valid_price"] = json_safe(first_price)
        item["last_valid_date"] = json_safe(last.get("date"))
        item["last_valid_price"] = json_safe(last_price)
        if first_price not in {None, 0} and last_price is not None:
            item["collection_price_change_pct"] = json_safe((float(last_price) - float(first_price)) / float(first_price))
        else:
            item["collection_price_change_pct"] = None
    if collection_prices:
        item["min_price"] = json_safe(min(collection_prices))
        item["max_price"] = json_safe(max(collection_prices))
    changed_dates: list[str] = []
    previous_price: float | None = None
    for point in collection_points:
        price = parse_float_value(point.get("price"))
        if price is None:
            continue
        if previous_price is not None and round(price, 6) != round(previous_price, 6):
            changed_dates.append(str(point.get("date")))
        previous_price = price
    item["price_changed_dates"] = changed_dates
    item["price_change_summary"] = (
        f"采集日价格发生变化：{', '.join(changed_dates)}" if changed_dates else "采集日价格未变化"
    )

    recent7 = [float(point["price"]) for point in points[-7:] if point.get("price") is not None]
    recent30 = [float(point["price"]) for point in points[-30:] if point.get("price") is not None]
    if recent7:
        item["seven_day_avg_price"] = json_safe(sum(recent7) / len(recent7))
        item["seven_day_sample_count"] = len(recent7)
    if recent30:
        item["thirty_day_avg_price"] = json_safe(sum(recent30) / len(recent30))
        item["thirty_day_sample_count"] = len(recent30)
    latest = points[-1]
    item["price_source"] = latest.get("price_source") or item.get("price_source")
    for key in [
        "price_variant", "price_variant_label", "selected_regions", "selected_android_versions",
        "region_price_selection_rule", "stock_status", "source_run_dir", "source_file",
        "actual_duration_days", "actual_duration_display", "comparison_duration_note",
    ]:
        if latest.get(key) not in {None, "", "None", "nan"}:
            item[key] = json_safe(latest.get(key))




def android_version_sort_key(value: Any) -> tuple[int, str]:
    text = str(value or "").strip()
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return (9999, text)
    try:
        return (int(float(match.group(0)) * 100), text)
    except Exception:
        return (9999, text)


def extract_android_versions_from_config(value: Any) -> list[str]:
    text = normalize_display_text(value)
    versions = []
    for match in re.finditer(r"(?:android|a)\s*([0-9]+(?:\.[0-9]+)?)", text, flags=re.I):
        raw = match.group(1)
        label = raw[:-2] if raw.endswith(".0") else raw
        versions.append(label)
    return sorted(set(versions), key=android_version_sort_key)


def config_without_android_version(value: Any) -> str:
    text = normalize_display_text(value)
    # Keep CPU/RAM/storage/model information, but remove Android version so
    # identical-price Android variants can be represented as one product line.
    text = re.sub(r"\s*/?\s*(?:Android|A)\s*[0-9]+(?:\.[0-9]+)?\s*/?\s*", " / ", text, flags=re.I)
    text = re.sub(r"\s*/\s*/+\s*", " / ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" /-") or normalize_display_text(value)


def build_merged_config_label(base_config: Any, configs: list[Any]) -> str:
    base = normalize_display_text(base_config)
    versions: list[str] = []
    for config in configs:
        versions.extend(extract_android_versions_from_config(config))
    versions = sorted(set(versions), key=android_version_sort_key)
    if len(versions) <= 1:
        return base
    android_label = "Android " + "/".join(versions)
    if re.search(r"(?:Android|A)\s*[0-9]+(?:\.[0-9]+)?", base, flags=re.I):
        return re.sub(r"(?:Android|A)\s*[0-9]+(?:\.[0-9]+)?", android_label, base, count=1, flags=re.I)
    stripped = config_without_android_version(base)
    return f"{android_label} / {stripped}" if stripped else android_label


def price_sequence_signature(item: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    points = item.get("points") or []
    signature = []
    for point in points:
        date = point.get("date")
        if not is_iso_date_label(date):
            continue
        price = parse_float_value(point.get("price"))
        signature.append((str(date), "" if price is None else f"{price:.6f}"))
    if not signature:
        current = parse_float_value(item.get("current_price"))
        signature.append(("current", "" if current is None else f"{current:.6f}"))
    return tuple(sorted(signature))


def merge_equivalent_android_price_series(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge duplicate Android-version product lines with identical prices.

    Some platforms expose the same product tier across multiple Android versions,
    while all visible payable prices are exactly the same.  Showing every Android
    version as a separate selectable trend line makes the frontend unusable and
    also overweights that product in the composite index.  This merge only
    collapses lines when the non-Android configuration, platform, product,
    duration bucket, and full dated price sequence match.

    It intentionally does NOT merge different prices, different product tiers,
    different duration buckets, or different non-Android configurations.  This preserves the
    earlier fixes for LDCloud price variants, new-user offers, and multi-device
    packages.
    """
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for item in series:
        platform = normalize_platform_name(item.get("platform"))
        key = (
            platform,
            normalize_series_product(item.get("product_model")),
            str(item.get("duration_bucket") or ""),
            normalize_token(config_without_android_version(item.get("config"))),
            price_sequence_signature(item),
        )
        groups.setdefault(key, []).append(item)

    merged: list[dict[str, Any]] = []
    for group_items in groups.values():
        if len(group_items) == 1:
            item = dict(group_items[0])
            item.setdefault("merged_series_count", 1)
            item.setdefault("merged_android_versions", extract_android_versions_from_config(item.get("config")))
            item.setdefault("ug_config_ids", [item.get("ug_config_id")] if item.get("ug_config_id") else [])
            if isinstance(item.get("regional_points"), dict):
                item["available_regions"] = sorted(normalize_region_label(region) for region in item.get("regional_points", {}).keys() if normalize_region_label(region))
            item["android_breakdown_series"] = stable_list(item.get("android_breakdown_series"))
            merged.append(item)
            continue

        group_items = sorted(
            group_items,
            key=lambda value: (
                android_version_sort_key("/".join(extract_android_versions_from_config(value.get("config")))),
                str(value.get("series_id") or ""),
            ),
        )
        base = dict(group_items[0])
        configs = [item.get("config") for item in group_items]
        android_versions: list[str] = []
        ug_config_ids: list[Any] = []
        source_series_ids: list[Any] = []
        scores: list[float] = []
        comparability_levels: list[str] = []
        android_breakdown_children: list[dict[str, Any]] = []
        for item in group_items:
            android_versions.extend(extract_android_versions_from_config(item.get("config")))
            android_breakdown_children.extend([child for child in stable_list(item.get("android_breakdown_series")) if isinstance(child, dict)])
            source_series_ids.append(item.get("series_id"))
            level = str(item.get("comparability_level") or "")
            if level and level not in comparability_levels:
                comparability_levels.append(level)
            ug_id = item.get("ug_config_id")
            if ug_id not in {None, ""} and ug_id not in ug_config_ids:
                ug_config_ids.append(ug_id)
            score = parse_float_value(item.get("config_similarity_score"))
            if score is not None:
                scores.append(score)
        android_versions = sorted(set(android_versions), key=android_version_sort_key)
        base["config"] = build_merged_config_label(base.get("config"), configs)
        base["series_id"] = compact_series_id(
            "merged_android",
            base.get("platform"),
            base.get("product_model"),
            base.get("duration_bucket"),
            config_without_android_version(base.get("config")),
            price_sequence_signature(base),
        )
        base["merged_series_count"] = len(group_items)
        base["merged_comparability_levels"] = comparability_levels
        if len(comparability_levels) > 1:
            # Keep the strongest/most useful display label while preserving all levels.
            preferred = ["base", "strong_match", "adjusted_match", "weak_match", "not_comparable", "historical_unmatched"]
            base["comparability_level"] = next((level for level in preferred if level in comparability_levels), comparability_levels[0])
        base["merged_android_versions"] = android_versions
        base["regional_points"] = merge_regional_points_for_android_group(group_items)
        base["available_regions"] = sorted(base["regional_points"].keys())
        if android_breakdown_children:
            unique_children: dict[str, dict[str, Any]] = {}
            for child in android_breakdown_children:
                child_key = "||".join([
                    str(child.get("platform") or ""),
                    normalize_series_product(child.get("product_model")),
                    str(child.get("config_signature") or child.get("android_version") or ""),
                    str(child.get("duration_bucket") or ""),
                ])
                unique_children.setdefault(child_key, child)
            base["android_breakdown_series"] = sorted(unique_children.values(), key=lambda child: (android_version_sort_key(child.get("android_version")), str(child.get("series_id") or "")))
        base["source_series_ids"] = [json_safe(value) for value in source_series_ids if value]
        base["ug_config_ids"] = [json_safe(value) for value in ug_config_ids]
        if ug_config_ids:
            base["ug_config_id"] = json_safe(ug_config_ids[0] if len(ug_config_ids) == 1 else compact_series_id("merged_ug_config", *ug_config_ids))
        if len(android_versions) > 1:
            base["line_name"] = normalize_display_text(f"{base.get('platform')} {base.get('product_model') or '-'} Android {'/'.join(android_versions)} {base.get('duration_display') or (str(base.get('duration_bucket')) + '天' if str(base.get('duration_bucket')) in {str(v) for v in FRONTEND_CORE_BUCKETS} else '其他')}")
            base["merge_note"] = "多个Android版本价格完全一致，已合并为一条产品线"
        if scores:
            min_score = min(scores)
            max_score = max(scores)
            base["config_similarity_score"] = json_safe(round(min_score, 2) if abs(max_score - min_score) < 1e-9 else f"{round(min_score, 2)}-{round(max_score, 2)}")
        merged.append(base)

    return sorted(merged, key=lambda item: (
        ALL_PLATFORMS.index(normalize_platform_name(item.get("platform"))) if normalize_platform_name(item.get("platform")) in ALL_PLATFORMS else 99,
        str(item.get("product_model") or ""),
        str(item.get("duration_bucket") or ""),
        parse_float_value(item.get("current_price")) or 0,
        str(item.get("line_name") or ""),
    ))



def config_signature_without_android_from_signature(value: Any) -> str:
    text = normalize_display_text(value)
    parts = text.split("|")
    if len(parts) >= 4:
        return "|".join(parts[1:])
    return text


def android_version_from_config_signature_value(value: Any) -> str | None:
    text = normalize_display_text(value)
    parts = text.split("|")
    if not parts:
        return None
    return normalize_display_text(parts[0]) or None

def build_price_trends(
    price_changes: list[dict[str, Any]],
    duration_comparison: dict[str, Any],
    meta: dict[str, Any],
) -> dict[str, Any]:
    timestamp = meta.get("last_run_at_utc") or meta.get("generated_at_utc")
    current_date = meta.get("last_run_date") or local_date_from_iso(timestamp) or trend_date_label(timestamp, "current")
    previous_date = "previous"
    output_dir = Path(meta.get("source_output_dir") or ".")
    (
        history,
        loose_history,
        other_paid_prices,
        regional_history,
        regional_loose_history,
        android_history,
        android_loose_history,
        android_regional_history,
        android_regional_loose_history,
    ) = collect_historical_trend_points(output_dir)
    change_lookup: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in price_changes:
        key = (
            normalize_platform_name(row.get("platform")),
            normalize_series_product(row.get("product_model")),
            str(row.get("duration_bucket")),
        )
        change_lookup[key] = row

    series: list[dict[str, Any]] = []


    def build_android_breakdown_series_for_item(
        *,
        platform: str,
        product_model: Any,
        product_key: str,
        bucket_key: str,
        signature_no_android: str,
        ug_config_id_value: Any,
        duration_display: Any,
        comparability_level: str,
        config_similarity_score: Any,
        ug_product_model_value: Any = None,
    ) -> list[dict[str, Any]]:
        platform_name = normalize_platform_name(platform)
        matched_keys = sorted(
            key for key in android_history.keys()
            if key[0] == platform_name
            and key[1] == product_key
            and str(key[3]) == bucket_key
            and config_signature_without_android_from_signature(key[2]) == signature_no_android
        )
        children: list[dict[str, Any]] = []
        for key in matched_keys:
            _, _, signature_full, _ = key
            android_version = android_version_from_config_signature_value(signature_full)
            if not android_version:
                continue
            hist_points = android_history.get(key) or {}
            if not hist_points:
                hist_points = android_loose_history.get((platform_name, product_key, bucket_key), {})
            points = merge_series_points([], hist_points or {})
            regional_hist_points = android_regional_history.get(key)
            if not regional_hist_points:
                regional_hist_points = android_regional_loose_history.get((platform_name, product_key, bucket_key), {})
            regional_points = merge_regional_points_map(regional_hist_points or {})
            if not points and not regional_points:
                continue
            child_name = normalize_display_text(f"{platform_name} {product_model or '-'} Android {android_version} {duration_display or (bucket_key + '天' if bucket_key in {str(v) for v in FRONTEND_CORE_BUCKETS} else '其他')}")
            child = {
                "series_id": compact_series_id(platform_name, product_model, ug_config_id_value, "android", signature_full, bucket_key),
                "platform": platform_name,
                "product_model": json_safe(product_model),
                "ug_product_model": json_safe(ug_product_model_value if ug_product_model_value is not None else (product_model if platform_name == BASE_PLATFORM else None)),
                "config": json_safe(f"Android {android_version} / {signature_no_android}"),
                "config_signature": signature_full,
                "ug_config_id": json_safe(ug_config_id_value),
                "duration_bucket": json_safe(bucket_key),
                "duration_display": json_safe(duration_display),
                "actual_duration_days": None,
                "actual_duration_display": None,
                "comparison_duration_note": None,
                "comparability_level": comparability_level,
                "config_similarity_score": json_safe(config_similarity_score),
                "line_name": child_name,
                "display_name": child_name,
                "color": PLATFORM_COLORS.get(platform_name, "#64748b"),
                "current_price": None,
                "previous_price": None,
                "seven_day_avg_price": None,
                "seven_day_sample_count": 0,
                "thirty_day_avg_price": None,
                "thirty_day_sample_count": 0,
                "price_change_pct": None,
                "price_source": "historical_products_android",
                "points": points,
                "region_display_mode": "merged_all_regions",
                "regional_points": regional_points,
                "available_regions": sorted(regional_points.keys()),
                "android_version": android_version,
                "android_versions": [android_version],
                "merged_android_versions": [android_version],
                "display_android_versions": [android_version],
                "android_display_mode": "expanded",
                "parent_non_android_config_signature": signature_no_android,
            }
            update_series_stats_from_points(child)
            children.append(child)
        return children

    def add_series(
        *,
        platform: str,
        product_model: Any,
        config: Any,
        ug_config_id_value: Any,
        bucket: Any,
        duration_display: Any,
        current_price: Any,
        comparability_level: str,
        config_similarity_score: Any,
        price_source: str = "current",
        ug_product_model_value: Any = None,
    ) -> None:
        platform = normalize_platform_name(platform)
        product_key = normalize_series_product(product_model)
        bucket_key = str(bucket)
        signature = normalize_config_signature(config)
        signature_no_android = config_signature_without_android_from_signature(signature)
        change = change_lookup.get((platform, product_key, bucket_key), {})
        previous = change.get("previous_price")
        baseline = change.get("baseline_price")
        current = current_price if current_price is not None else change.get("current_price")
        source = price_source
        if current is None and baseline is not None:
            current = baseline
            source = "baseline_fallback"
        elif current is None:
            source = "missing"
        if previous is None:
            previous = baseline if baseline is not None else current
        line_name = f"{platform} {product_model or '-'} {duration_display or bucket}"
        base_points = [
            {"date": previous_date, "price": json_safe(previous), "price_source": "previous"},
            {"date": current_date, "price": json_safe(current), "price_source": source},
        ]
        hist_points = history.get((platform, product_key, signature_no_android, bucket_key))
        if not hist_points:
            hist_points = loose_history.get((platform, product_key, bucket_key), {})
        points = merge_series_points(base_points, hist_points or {})
        regional_hist_points = regional_history.get((platform, product_key, signature_no_android, bucket_key))
        if not regional_hist_points:
            regional_hist_points = regional_loose_history.get((platform, product_key, bucket_key), {})
        regional_points = merge_regional_points_map(regional_hist_points or {})
        android_breakdown_series = build_android_breakdown_series_for_item(
            platform=platform,
            product_model=product_model,
            product_key=product_key,
            bucket_key=bucket_key,
            signature_no_android=signature_no_android,
            ug_config_id_value=ug_config_id_value,
            duration_display=duration_display,
            comparability_level=comparability_level,
            config_similarity_score=config_similarity_score,
            ug_product_model_value=ug_product_model_value,
        )
        item = {
            "series_id": compact_series_id(platform, product_model, ug_config_id_value, signature, bucket),
            "platform": platform,
            "product_model": json_safe(product_model),
            "ug_product_model": json_safe(ug_product_model_value if ug_product_model_value is not None else (product_model if platform == BASE_PLATFORM else None)),
            "config": json_safe(config),
            "ug_config_id": json_safe(ug_config_id_value),
            "duration_bucket": json_safe(bucket),
            "duration_display": json_safe(duration_display),
            "actual_duration_days": None,
            "actual_duration_display": None,
            "comparison_duration_note": None,
            "comparability_level": comparability_level,
            "config_similarity_score": json_safe(config_similarity_score),
            "line_name": normalize_display_text(line_name),
            "color": PLATFORM_COLORS.get(platform, "#64748b"),
            "current_price": json_safe(current),
            "previous_price": json_safe(previous),
            "seven_day_avg_price": json_safe(change.get("seven_day_avg_price") if change else current),
            "seven_day_sample_count": json_safe(change.get("seven_day_sample_count") if change else (1 if current is not None else 0)),
            "thirty_day_avg_price": json_safe(change.get("thirty_day_avg_price") if change else current),
            "thirty_day_sample_count": json_safe(change.get("thirty_day_sample_count") if change else (1 if current is not None else 0)),
            "price_change_pct": json_safe(change.get("price_change_pct")),
            "price_source": source,
            "points": points,
            "region_display_mode": "merged_all_regions",
            "regional_points": regional_points,
            "available_regions": sorted(regional_points.keys()),
            "android_breakdown_series": android_breakdown_series,
        }
        update_series_stats_from_points(item)
        series.append(item)

    all_rows = [row for rows in (duration_comparison.get("buckets") or {}).values() for row in rows]
    all_rows.extend(duration_comparison.get("other_rows") or [])
    existing_line_keys: set[tuple[str, str, str]] = set()
    for row in all_rows:
        bucket = row.get("duration_bucket")
        add_series(
            platform=BASE_PLATFORM,
            product_model=row.get("ug_product_model"),
            config=row.get("ug_config"),
            ug_config_id_value=row.get("ug_config_id"),
            bucket=bucket,
            duration_display=row.get("duration_display"),
            current_price=row.get("ugphone_price"),
            comparability_level="base",
            config_similarity_score=100,
            ug_product_model_value=row.get("ug_product_model"),
        )
        existing_line_keys.add((BASE_PLATFORM, normalize_series_product(row.get("ug_product_model")), str(bucket)))
        for platform, competitor in (row.get("competitors") or {}).items():
            if not competitor:
                continue
            # Do not create misleading trend lines from nearest-duration competitor
            # prices.  If VSPhone/Redfinger has no true 180-day SKU, its 90-day
            # price must not become a fake "180天" trend.  The only intended
            # cross-duration mapping is performed earlier in duration bucket
            # normalization, e.g. LDCloud 8-day -> 7-day.
            if competitor.get("current_price") is None:
                continue
            add_series(
                platform=platform,
                product_model=competitor.get("product_model"),
                config=competitor.get("config"),
                ug_config_id_value=row.get("ug_config_id"),
                bucket=bucket,
                duration_display=row.get("duration_display"),
                current_price=competitor.get("current_price"),
                comparability_level=competitor.get("comparability_level") or "missing_competitor",
                config_similarity_score=competitor.get("config_similarity_score"),
                ug_product_model_value=row.get("ug_product_model"),
            )
            existing_line_keys.add((normalize_platform_name(platform), normalize_series_product(competitor.get("product_model")), str(bucket)))

    # Add history-only lines when the current quality report does not define a
    # matching paired row. This prevents old daily product data from being ignored
    # completely and makes the trend chart prove that history was actually read.
    for (platform, product_key, bucket_key), hist_points in sorted(loose_history.items()):
        if (platform, product_key, bucket_key) in existing_line_keys:
            continue
        if not hist_points:
            continue
        sample = next(iter(hist_points.values()))
        product_model = sample.get("product_model") or product_key
        duration_display = sample.get("actual_duration_display") or sample.get("duration_display") or (f"{bucket_key}天" if bucket_key in {str(v) for v in FRONTEND_CORE_BUCKETS} else "其他")
        points = merge_series_points([], hist_points)
        regional_hist_points = regional_loose_history.get((platform, product_key, bucket_key), {})
        regional_points = merge_regional_points_map(regional_hist_points or {})
        signature_no_android = config_signature_without_android_from_signature(sample.get("config_signature") or "")
        android_breakdown_series = build_android_breakdown_series_for_item(
            platform=platform,
            product_model=product_model,
            product_key=product_key,
            bucket_key=bucket_key,
            signature_no_android=signature_no_android,
            ug_config_id_value="history_only",
            duration_display=duration_display,
            comparability_level="historical_unmatched",
            config_similarity_score=None,
            ug_product_model_value=product_model if platform == BASE_PLATFORM else None,
        )
        item = {
            "series_id": compact_series_id(platform, product_model, "history_only", bucket_key),
            "platform": platform,
            "product_model": normalize_display_text(product_model),
            "config": "历史 products.csv 产品线",
            "ug_config_id": "history_only",
            "duration_bucket": json_safe(bucket_key),
            "duration_display": duration_display,
            "actual_duration_days": sample.get("actual_duration_days"),
            "actual_duration_display": sample.get("actual_duration_display"),
            "comparison_duration_note": sample.get("comparison_duration_note"),
            "comparability_level": "historical_unmatched",
            "config_similarity_score": None,
            "line_name": normalize_display_text(f"{platform} {product_model} {duration_display}"),
            "color": PLATFORM_COLORS.get(platform, "#64748b"),
            "current_price": None,
            "previous_price": None,
            "seven_day_avg_price": None,
            "seven_day_sample_count": 0,
            "thirty_day_avg_price": None,
            "thirty_day_sample_count": 0,
            "price_change_pct": None,
            "price_source": "historical_products",
            "points": points,
            "region_display_mode": "merged_all_regions",
            "regional_points": regional_points,
            "available_regions": sorted(regional_points.keys()),
            "android_breakdown_series": android_breakdown_series,
        }
        update_series_stats_from_points(item)
        series.append(item)

    # Final safety migration: if stale historical rows still carry bucket="other"
    # but their display/actual duration is now a core bucket (3/15/60天), move
    # them before the frontend receives the JSON.
    series = [migrate_duration_bucket_fields(item) for item in series]
    other_paid_prices = [migrate_duration_bucket_fields(item) for item in other_paid_prices]

    series = merge_equivalent_android_price_series(series)
    series, date_axis_meta = apply_natural_day_axis(series)
    history_dates = sorted({point.get("date") for item in series for point in item.get("points", []) if is_iso_date_label(point.get("date"))})
    history_point_count = sum(1 for item in series for point in item.get("points", []) if is_iso_date_label(point.get("date")))
    regional_history_point_count = sum(
        1
        for item in series
        for points in (item.get("regional_points") or {}).values()
        for point in points
        if is_iso_date_label(point.get("date"))
    )
    carry_forward_point_count = sum(1 for item in series for point in item.get("points", []) if point.get("price_source") == "carry_forward")
    region_options = sorted({
        normalize_region_label(region)
        for item in series
        for region in (item.get("regional_points") or {}).keys()
        if normalize_region_label(region)
    })
    merged_series_count = sum(int(item.get("merged_series_count") or 1) for item in series) - len(series)
    android_breakdown_series_count = sum(len(stable_list(item.get("android_breakdown_series"))) for item in series)
    return {
        "updated_at": timestamp,
        "available_duration_buckets": [*FRONTEND_CORE_BUCKETS, "other"],
        "history_source": "daily_products_csv_xlsx_first_then_dashboard_price_trends",
        "history_dates": history_dates,
        "history_date_count": len(history_dates),
        "history_start_date": date_axis_meta.get("history_start_date"),
        "history_end_date": date_axis_meta.get("history_end_date"),
        "raw_collection_dates": date_axis_meta.get("raw_collection_dates", []),
        "filled_dates": date_axis_meta.get("filled_dates", []),
        "natural_history_dates": date_axis_meta.get("natural_history_dates", []),
        "date_fill_mode": date_axis_meta.get("date_fill_mode"),
        "history_point_count": history_point_count,
        "regional_history_point_count": regional_history_point_count,
        "region_options": region_options,
        "region_display_default": "merged_all_regions",
        "region_display_rule": "图二默认使用合并所有机房的多数机房价格；选择具体机房后，前端改用 regional_points 中该机房的历史实付价。",
        "carry_forward_point_count": carry_forward_point_count,
        "history_run_dir_count": len(iter_history_output_dirs(output_dir)),
        "duration_comparison_rule": "LDCloud has no true 7-day SKU in the monitored data; its 8-day SKU is mapped to the 7-day bucket for comparison while preserving actual 8-day display/audit fields.",
        "core_price_rule": "core trend uses the majority-region current purchasable single-device paid price for the same platform/product/duration/non-Android config; if region counts tie, the lower price wins; new-user, unavailable, multi-device, trial and flash prices do not drive the core trend",
        "regional_price_rule": "when the same product differs by machine room/region, core trend selects the price covering the most purchasable machine rooms; lower or higher minority-region prices are exported as other_paid_prices",
        "date_axis_rule": "charts display every natural day from first to latest collection date; days without collection carry forward the latest collection-day price and are marked price_source=carry_forward",
        "merged_android_duplicate_series_count": merged_series_count,
        "android_breakdown_series_count": android_breakdown_series_count,
        "android_breakdown_rule": "when products expose multiple Android versions under the same product/duration/non-Android config, android_breakdown_series preserves product × Android version and product × Android version × region historical points for the frontend expanded mode",
        "android_merge_rule": "same platform/product/duration/non-Android config with identical dated price sequence is merged into one product line; multiple comparability levels are preserved in merged_comparability_levels",
        "other_paid_price_count": len(other_paid_prices),
        "other_paid_prices": other_paid_prices[:2000],
        "series": series,
    }

def build_admin_diagnostics(run_summary: dict[str, Any], platform_rows: list[dict[str, Any]], details: pd.DataFrame, rationality: pd.DataFrame) -> dict[str, Any]:
    safe_run_summary = {
        key: value
        for key, value in run_summary.items()
        if key not in {"platform_storage_states"}
    }
    platform_states = []
    blocked = run_summary.get("blocked_pages", {}) or {}
    failed = run_summary.get("failed_pages", {}) or {}
    for row in platform_rows:
        platform = row["platform"]
        login_required = platform in {"Redfinger", "LDCloud", BASE_PLATFORM, "VSPhone"}
        failed_due_to_login = platform in failed and "login" in str(failed.get(platform, "")).lower()
        row_collection_status = str(row.get("collection_status") or row.get("status") or "unknown")
        if failed_due_to_login:
            diagnostic_collection_status = "failed_due_to_login"
        elif platform in failed:
            diagnostic_collection_status = "failed_after_login"
        elif row_collection_status == "warning":
            diagnostic_collection_status = "warning"
        elif row_collection_status in {"blocked", "failed"}:
            diagnostic_collection_status = f"collection_{row_collection_status}"
        else:
            diagnostic_collection_status = "success"
        platform_states.append(
            {
                "platform": platform,
                "login_required": login_required,
                "login_checked": False,
                "login_status": "unknown",
                "login_check_method": "manual_check",
                "login_error_message": str(failed.get(platform, "")) if failed_due_to_login else "",
                "collection_status": diagnostic_collection_status,
                "collection_health": row_collection_status,
                "baseline_coverage_status": row.get("baseline_coverage_status", "unknown"),
                "baseline_coverage_ratio": row.get("baseline_coverage_ratio"),
                "fallback_to_baseline": bool(row.get("missing_vs_baseline", 0)),
                "fallback_reason": "current_missing_used_baseline" if row.get("missing_vs_baseline", 0) else "",
                "unmatched_current_rows": 0,
                "missing_baseline_rows": row.get("missing_vs_baseline", 0),
            }
        )
    fallback_count = 0
    if not details.empty and "notes" in details.columns:
        fallback_count = int(details["notes"].astype(str).str.contains("current_missing_used_baseline", regex=False).sum())
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "platform_diagnostics": platform_states,
        "blocked_pages": blocked,
        "failed_pages": failed,
        "warnings": run_summary.get("warnings", []),
        "fallback_to_baseline_rows": fallback_count,
        "unmatched_current_rows": [],
        "missing_baseline_rows": records_from_df(rationality[rationality.get("notes", pd.Series(dtype=object)).astype(str).str.contains("baseline_row_missing_for_current_product", regex=False)]) if not rationality.empty else [],
        "raw_run_summary": safe_run_summary,
    }


def export_dashboard_data(output_dir: Path, mirror_dirs: list[Path] | None = None) -> Path:
    output_dir = Path(output_dir)
    dashboard_dir = output_dir / "dashboard_data"
    run_summary = read_json(output_dir / "run_summary.json")
    quality_path = output_dir / "quality_price_report.xlsx"

    details = read_excel_sheet(quality_path, "质量调整价格明细", QUALITY_COLS)
    relative = read_excel_sheet(quality_path, "UG相对竞品指数", RELATIVE_COLS)
    pairings = read_excel_sheet(quality_path, "配置配对建议", PAIRING_COLS)
    rationality = read_excel_sheet(quality_path, "变价合理性判断", RATIONALITY_COLS)
    details, pairings = enrich_ids(details, pairings)

    decisions = build_price_decision(relative, details)
    baskets = attach_decision_context(build_competitor_basket(details), decisions)
    matrix = build_matrix(decisions)
    platform_rows = build_platform_status(output_dir, run_summary)
    daily_changes = build_daily_changes(output_dir)
    schedule_status = build_schedule_status(run_summary)
    meta = {
        "is_mock_data": False,
        "source": "dashboard_export",
        "source_output_dir": str(output_dir),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "last_run_at_utc": run_summary.get("end_time_utc"),
        "last_run_date": output_run_date(output_dir),
        "safe_data_only": True,
    }
    pairing_records = build_pairing_evidence_records(pairings)
    price_changes = build_price_change_tracking(rationality)
    duration_comparison = attach_price_change_flags(build_duration_price_comparison(details), price_changes)

    price_trends_payload, price_trends_chunk_payloads = split_price_trends_detail_payloads(
        build_price_trends(price_changes, duration_comparison, meta)
    )

    payloads = {
        "frontend_price_overview.json": build_frontend_price_overview(duration_comparison, meta),
        "pairing_matrix.json": build_pairing_matrix(pairing_records),
        "duration_price_comparison.json": duration_comparison,
        "price_trends.json": price_trends_payload,
        **price_trends_chunk_payloads,
        "price_change_tracking.json": price_changes,
        "product_text_changes.json": build_product_text_changes(price_changes),
        "metric_definitions.json": METRIC_DEFINITIONS,
        "admin_diagnostics.json": build_admin_diagnostics(run_summary, platform_rows, details, rationality),
        "meta.json": meta,
        "kpis.json": build_kpis(run_summary, decisions, platform_rows),
        "files.json": build_files(output_dir, DASHBOARD_JSON_FILES),
        "platform_status.json": platform_rows,
        "price_decision_overview.json": decisions,
        "ug_config_price_matrix.json": matrix,
        "competitor_basket.json": baskets,
        "pairing_evidence.json": pairing_records,
        "quality_price_details.json": records_from_df(details),
        "relative_index_series.json": {
            "rows": records_from_df(relative),
            "market_position_distribution": distribution(decisions, "market_position_label"),
            "alert_distribution": distribution(decisions, "alert_level"),
            "confidence_distribution": distribution(decisions, "confidence_level"),
            "alert_priority_board": alert_priority(decisions),
        },
        "price_rationality.json": {
            "rows": build_price_rationality_records(rationality),
            "reason_explanations": REASON_EXPLANATIONS,
            "reason_explanations_en": REASON_EXPLANATIONS_EN,
        },
        "daily_changes.json": daily_changes,
        "run_summary_view.json": {
            "start_time_utc": run_summary.get("start_time_utc"),
            "end_time_utc": run_summary.get("end_time_utc"),
            "records_by_platform": run_summary.get("records_by_platform", {}),
            "blocked_pages": run_summary.get("blocked_pages", {}),
            "failed_pages": run_summary.get("failed_pages", {}),
            "warnings": run_summary.get("warnings", []),
            "baseline_monitor": run_summary.get("baseline_monitor", {}),
            "quality_price_monitor": run_summary.get("quality_price_monitor", {}),
            "missing_field_stats": run_summary.get("missing_field_stats", {}),
        },
        "schedule_status.json": schedule_status,
    }

    if dashboard_dir.exists():
        shutil.rmtree(dashboard_dir)
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in payloads.items():
        write_json(dashboard_dir / filename, payload)

    for mirror in mirror_dirs or []:
        mirror = Path(mirror)
        # The static dashboard can be opened directly from dashboard/dist.
        # Ensure parent directories exist so a data-only update after `python run.py`
        # can refresh dashboard/dist/dashboard_data even before/without a new build.
        mirror.parent.mkdir(parents=True, exist_ok=True)
        if mirror.exists():
            shutil.rmtree(mirror)
        shutil.copytree(dashboard_dir, mirror)

    return dashboard_dir
