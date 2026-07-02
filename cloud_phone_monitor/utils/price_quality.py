from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from pathlib import Path
from statistics import median
from typing import Iterable

import pandas as pd


BASE_PLATFORM = "UgPhone"
COMPETITOR_PLATFORMS = ["VSPhone", "Redfinger", "LDCloud"]
EFFECTIVE_PERIOD_DAYS = 30


def normalize_platform_name(value):
    text = str(value or "").strip()
    if text.lower() == "ugphone":
        return BASE_PLATFORM
    return text

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

QUALITY_FIELD_COLUMNS = [
    "duration_days",
    "device_count",
    "effective_price_30d",
    "list_price_30d",
    "discount_rate",
    "price_basis",
]

PAIRING_COLUMNS = [
    "ug_platform",
    "ug_product_model",
    "ug_device_model",
    "ug_android_version",
    "ug_cpu",
    "ug_ram",
    "ug_storage",
    "ug_duration",
    "competitor_platform",
    "competitor_product_model",
    "competitor_device_model",
    "competitor_android_version",
    "competitor_cpu",
    "competitor_ram",
    "competitor_storage",
    "competitor_duration",
    "config_similarity_score",
    "comparability_level",
    "recommended_pairing_source",
    "pairing_notes",
]

QUALITY_DETAIL_COLUMNS = [
    "ug_product_model",
    "ug_config",
    "ug_duration_days",
    "ug_device_count",
    "ug_effective_price_30d",
    "ug_list_price_30d",
    "ug_discount_rate",
    "ug_price_basis",
    "competitor_platform",
    "competitor_product_model",
    "competitor_config",
    "competitor_duration_days",
    "competitor_device_count",
    "competitor_effective_price_30d",
    "competitor_list_price_30d",
    "competitor_discount_rate",
    "competitor_price_basis",
    "config_similarity_score",
    "quality_adjustment_factor",
    "quality_adjusted_price_30d",
    "adjusted_delta",
    "adjusted_delta_pct",
    "comparability_level",
    "recommended_pairing_source",
    "promotion_text",
    "supported_server_regions",
    "notes",
]

RELATIVE_INDEX_COLUMNS = [
    "ug_product_model",
    "ug_config",
    "ug_duration_days",
    "ug_effective_price_30d",
    "competitor_median_quality_adjusted_price_30d",
    "competitor_count_core",
    "competitor_count_weak",
    "weak_median_quality_adjusted_price_30d",
    "ugphone_relative_index",
    "price_position_label",
    "alert_level",
    "reason_code",
    "notes",
]

REASON_COLUMNS = [
    "platform",
    "product_model",
    "device_model",
    "android_version",
    "cpu",
    "ram",
    "storage",
    "duration_days",
    "baseline_effective_price_30d",
    "current_effective_price_30d",
    "own_price_index",
    "baseline_list_price_30d",
    "current_list_price_30d",
    "list_price_index",
    "baseline_discount_rate",
    "current_discount_rate",
    "discount_rate_change",
    "baseline_promotion_text",
    "current_promotion_text",
    "baseline_supported_server_regions",
    "current_supported_server_regions",
    "reason_code",
    "alert_level",
    "notes",
]

DAILY_NEAR_CONFIG_COLUMNS = [
    "ug_product_model",
    "ug_config",
    "ug_duration_days",
    "ug_effective_price_30d",
    "competitor_platform",
    "competitor_product_model",
    "competitor_config",
    "competitor_duration_days",
    "competitor_effective_price_30d",
    "quality_adjustment_factor",
    "quality_adjusted_price_30d",
    "adjusted_delta",
    "adjusted_delta_pct",
    "config_similarity_score",
    "comparability_level",
    "recommended_pairing_source",
    "promotion_text",
    "supported_server_regions",
    "notes",
]

QUALITY_HEADER_CN = {
    "ug_platform": "UG平台",
    "ug_product_model": "UG套餐型号",
    "ug_device_model": "UG设备型号",
    "ug_android_version": "UG安卓版本",
    "ug_cpu": "UG CPU",
    "ug_ram": "UG内存",
    "ug_storage": "UG存储",
    "ug_duration": "UG购买时长",
    "competitor_platform": "竞品平台",
    "competitor_product_model": "竞品套餐型号",
    "competitor_device_model": "竞品设备型号",
    "competitor_android_version": "竞品安卓版本",
    "competitor_cpu": "竞品CPU",
    "competitor_ram": "竞品内存",
    "competitor_storage": "竞品存储",
    "competitor_duration": "竞品购买时长",
    "config_similarity_score": "配置相似度分",
    "comparability_level": "可比性等级",
    "recommended_pairing_source": "配对来源",
    "pairing_notes": "配对备注",
    "ug_config": "UG配置",
    "ug_duration_days": "UG购买天数",
    "ug_device_count": "UG设备数",
    "ug_effective_price_30d": "UG 30天等效实付价",
    "ug_list_price_30d": "UG 30天等效原价",
    "ug_discount_rate": "UG折扣率",
    "ug_price_basis": "UG价格口径",
    "competitor_config": "竞品配置",
    "competitor_duration_days": "竞品购买天数",
    "competitor_device_count": "竞品设备数",
    "competitor_effective_price_30d": "竞品30天等效实付价",
    "competitor_list_price_30d": "竞品30天等效原价",
    "competitor_discount_rate": "竞品折扣率",
    "competitor_price_basis": "竞品价格口径",
    "quality_adjustment_factor": "质量调整系数",
    "quality_adjusted_price_30d": "质量调整后30天价",
    "adjusted_delta": "调整后价差",
    "adjusted_delta_pct": "调整后价差比例",
    "promotion_text": "活动文案",
    "supported_server_regions": "支持服务器地区",
    "notes": "备注",
    "competitor_median_quality_adjusted_price_30d": "竞品质量调整价中位数",
    "competitor_count_core": "核心可比竞品数",
    "competitor_count_weak": "弱可比竞品数",
    "weak_median_quality_adjusted_price_30d": "弱可比竞品中位数",
    "ugphone_relative_index": "UG相对竞品指数",
    "price_position_label": "价格位置标签",
    "alert_level": "提醒等级",
    "reason_code": "原因标签",
    "platform": "平台",
    "product_model": "套餐型号",
    "device_model": "设备型号",
    "android_version": "安卓版本",
    "cpu": "CPU",
    "ram": "内存",
    "storage": "存储",
    "duration_days": "购买天数",
    "baseline_effective_price_30d": "基准30天等效实付价",
    "current_effective_price_30d": "本次30天等效实付价",
    "own_price_index": "自身价格指数",
    "baseline_list_price_30d": "基准30天等效原价",
    "current_list_price_30d": "本次30天等效原价",
    "list_price_index": "原价指数",
    "baseline_discount_rate": "基准折扣率",
    "current_discount_rate": "本次折扣率",
    "discount_rate_change": "折扣率变化",
    "baseline_promotion_text": "基准活动文案",
    "current_promotion_text": "本次活动文案",
    "baseline_supported_server_regions": "基准服务器地区",
    "current_supported_server_regions": "本次服务器地区",
}

DEFAULT_QUALITY_PRICE_CONFIG = {
    "enabled": True,
    "base_platform": BASE_PLATFORM,
    "competitor_platforms": COMPETITOR_PLATFORMS,
    "effective_period_days": EFFECTIVE_PERIOD_DAYS,
    "similarity_thresholds": {
        "strong_match": 90,
        "adjusted_match": 75,
        "weak_match": 60,
    },
    "relative_index_thresholds": {
        "below_market": 90,
        "competitive": 105,
        "slightly_high": 115,
    },
    "quality_adjustment_factor_min": 0.75,
    "quality_adjustment_factor_max": 1.35,
    "auto_top_n": 3,
    "manual_pairings": [
        {
            "ug_product_models": ["UVIP"],
            "competitors": {
                "VSPhone": [
                    {
                        "aliases": ["Basic"],
                        "notes": "手工推荐: Basic / Android 10 / 6C / 4GB / 32GB；CPU/RAM 高于 UG，核心判断需谨慎。",
                    }
                ],
                "Redfinger": [
                    {
                        "aliases": ["VIP"],
                        "notes": "手工推荐: VIP / Android 10 / 8C / 4GB / 64GB；配置明显高于 UG，不进入核心定价判断或仅作弱配对。",
                    }
                ],
                "LDCloud": [
                    {
                        "aliases": ["VIP10", "VIP12"],
                        "notes": "手工推荐: VIP10/VIP12 / 3C / 4GB / 45GB，作为 UG UVIP 最佳近似。",
                    }
                ],
            },
        },
        {
            "ug_product_models": ["GVIP"],
            "competitors": {
                "VSPhone": [{"aliases": ["VIP"], "notes": "手工推荐: VIP；按当前业务口径，UgPhone GVIP 对标 VSPhone VIP，而不是 KVIP。"}],
                "Redfinger": [{"aliases": ["VIP"], "notes": "手工推荐: VIP；CPU 明显高于 UG，弱配对。"}],
                "LDCloud": [
                    {
                        "aliases": ["KVIP10", "KVIP12"],
                        "notes": "手工推荐: KVIP10/KVIP12 / 4C / 5.3GB / 64GB，优先配对。",
                    }
                ],
            },
        },
        {
            "ug_product_models": ["KVIP"],
            "competitors": {
                "VSPhone": [{"aliases": ["SVIP"], "notes": "手工推荐: SVIP / 8C / 5.3GB / 85GB。"}],
                "Redfinger": [{"aliases": ["KVIP"], "notes": "手工推荐: KVIP / 8C / 6GB / 80GB。"}],
                "LDCloud": [
                    {
                        "aliases": ["KVIP10", "KVIP12", "KVIP14"],
                        "notes": "手工推荐: KVIP10/KVIP12/KVIP14，按安卓版本和相似度取最优。",
                    }
                ],
            },
        },
        {
            "ug_product_models": ["MVIP"],
            "competitors": {
                "VSPhone": [{"aliases": ["XVIP"], "notes": "手工推荐: XVIP / 8C / 8GB / 128GB，强配对。"}],
                "Redfinger": [{"aliases": ["SVIP"], "notes": "手工推荐: SVIP / 8C / 8GB / 128GB，强配对。"}],
                "LDCloud": [
                    {
                        "aliases": ["XVIP10", "XVIP12"],
                        "notes": "手工推荐: XVIP10/XVIP12 / 8C / 8GB / 90GB，存储低于 UG，近似配对。",
                    }
                ],
            },
        },
        {
            "ug_product_models": ["SVIP"],
            "competitors": {
                "VSPhone": [{"aliases": ["MVIP"], "notes": "手工推荐: MVIP / 8C / 16GB / 256GB，强配对。"}],
                "Redfinger": [{"aliases": ["XVIP"], "notes": "手工推荐: XVIP / 8C / 16GB / 256GB，强配对。"}],
                "LDCloud": [
                    {
                        "aliases": ["MVIP10", "MVIP12"],
                        "notes": "手工推荐: MVIP10/MVIP12 / 8C / 16GB / 185GB，存储略低于 UG。",
                    }
                ],
            },
        },
    ],
}

NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
REGION_SPLIT_RE = re.compile(r"[;；,，、/|]\s*")
TOKEN_RE = re.compile(r"[^a-z0-9]+")
TWO_DEVICE_RE = re.compile(
    r"(get\s*2\s*devices?|2\s*devices?|duet\s*pack|双设备|2\s*台|两\s*台)",
    re.IGNORECASE,
)


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


def append_note(existing, note: str) -> str:
    notes = []
    for part in as_text(existing).split(";"):
        item = part.strip()
        if item and item not in notes:
            notes.append(item)
    if note and note not in notes:
        notes.append(note)
    return "; ".join(notes)


def clean_number(value) -> float | None:
    text = as_text(value).replace(",", "")
    if not text:
        return None
    match = NUMBER_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def round_or_none(value, digits: int = 6):
    if value is None or missing(value):
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def deep_merge(base: dict, override: dict) -> dict:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_quality_price_config(config_path: Path | None = None) -> dict:
    config = deepcopy(DEFAULT_QUALITY_PRICE_CONFIG)
    if config_path is None:
        return config
    if not config_path.exists():
        raise FileNotFoundError(f"quality price config not found: {config_path}")
    override = json.loads(config_path.read_text(encoding="utf-8"))
    return deep_merge(config, override.get("quality_price_monitor", override))


def parse_duration_days(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return float(value)
        except Exception:
            return None
    text = as_text(value).lower()
    if not text:
        return None
    number = clean_number(text)
    if number is None:
        return None
    # A bare numeric cell in products.xlsx/products.csv means day count; marketing
    # text that merely contains a number, such as "Get 2 Devices", does not.
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return number
    if "hour" in text or "小时" in text:
        return number / 24
    if "day" in text or "天" in text or "日" in text:
        return number
    if "week" in text or "周" in text:
        return number * 7
    if "month" in text or "月" in text:
        return number * 30
    if "year" in text or "年" in text:
        return number * 365
    return None


def parse_cpu_cores(value) -> float | None:
    return clean_number(value)


def parse_ram_gb(value) -> float | None:
    return clean_number(value)


def parse_storage_gb(value) -> float | None:
    return clean_number(value)


def parse_android_version(value) -> float | None:
    return clean_number(value)


def parse_region_set(value) -> set[str]:
    text = as_text(value)
    if not text:
        return set()
    parts = [part.strip().lower() for part in REGION_SPLIT_RE.split(text) if part.strip()]
    return set(parts)


def detect_device_count(row: pd.Series | dict) -> tuple[int, str]:
    text = " ".join([as_text(row.get("promotion_text")), as_text(row.get("raw_text"))])
    if TWO_DEVICE_RE.search(text):
        return 2, ""
    return 1, "device_count_defaulted_to_1"


def determine_price_basis(price, original_price, promotion_text) -> str:
    price_num = clean_number(price)
    original_num = clean_number(original_price)
    has_promo = bool(as_text(promotion_text))
    if has_promo:
        return "promo_price"
    if price_num is not None and original_num is not None:
        if price_num < original_num:
            return "promo_price"
        if abs(price_num - original_num) < 0.000001:
            return "list_price"
    return "unknown_price_basis"


def add_standardized_price_fields(df: pd.DataFrame, effective_period_days: int = EFFECTIVE_PERIOD_DAYS) -> pd.DataFrame:
    out = df.copy()
    for col in [
        "platform",
        "product_model",
        "device_model",
        "android_version",
        "cpu",
        "ram",
        "storage",
        "price",
        "original_price",
        "discount_price",
        "duration",
        "supported_server_regions",
        "promotion_text",
        "raw_text",
        "stock_status",
        "notes",
    ]:
        if col not in out.columns:
            out[col] = None

    duration_days = []
    device_counts = []
    effective_prices = []
    list_prices = []
    discount_rates = []
    price_basis = []
    parsed_cpu = []
    parsed_ram = []
    parsed_storage = []
    parsed_android = []
    notes = []

    for _, row in out.iterrows():
        row_notes = as_text(row.get("notes"))
        days = parse_duration_days(row.get("duration"))
        if days is None:
            row_notes = append_note(row_notes, "duration_days_unparsed")
        device_count, device_note = detect_device_count(row)
        if device_note:
            row_notes = append_note(row_notes, device_note)
        price = clean_number(row.get("price"))
        original_price = clean_number(row.get("original_price"))
        if days and days > 0 and device_count > 0 and price is not None:
            effective_price = price / days * effective_period_days / device_count
        else:
            effective_price = None
            row_notes = append_note(row_notes, "effective_price_30d_missing_fields")
        if days and days > 0 and device_count > 0 and original_price is not None:
            list_price = original_price / days * effective_period_days / device_count
        else:
            list_price = None
        if original_price and price is not None:
            discount_rate = 1 - price / original_price
        else:
            discount_rate = None

        duration_days.append(round_or_none(days))
        device_counts.append(device_count)
        effective_prices.append(round_or_none(effective_price))
        list_prices.append(round_or_none(list_price))
        discount_rates.append(round_or_none(discount_rate))
        price_basis.append(determine_price_basis(row.get("price"), row.get("original_price"), row.get("promotion_text")))
        parsed_cpu.append(parse_cpu_cores(row.get("cpu")))
        parsed_ram.append(parse_ram_gb(row.get("ram")))
        parsed_storage.append(parse_storage_gb(row.get("storage")))
        parsed_android.append(parse_android_version(row.get("android_version")))
        notes.append(row_notes)

    out["duration_days"] = duration_days
    out["device_count"] = device_counts
    out["effective_price_30d"] = effective_prices
    out["list_price_30d"] = list_prices
    out["discount_rate"] = discount_rates
    out["price_basis"] = price_basis
    out["_cpu_num"] = parsed_cpu
    out["_ram_gb"] = parsed_ram
    out["_storage_gb"] = parsed_storage
    out["_android_num"] = parsed_android
    out["notes"] = notes
    return out


def normalize_token(value) -> str:
    return TOKEN_RE.sub("", as_text(value).lower())


def product_text(row: pd.Series | dict) -> str:
    return normalize_token(
        " ".join(
            [
                as_text(row.get("product_model")),
                as_text(row.get("device_model")),
                as_text(row.get("product_name")),
            ]
        )
    )


def config_text(row: pd.Series | dict) -> str:
    android = as_text(row.get("android_version")) or "未知安卓"
    return (
        f"{as_text(row.get('product_model')) or '-'} / "
        f"Android {android} / "
        f"{as_text(row.get('cpu')) or '-'} / "
        f"{as_text(row.get('ram')) or '-'} / "
        f"{as_text(row.get('storage')) or '-'}"
    )


def identity_key(row: pd.Series | dict) -> str:
    return "|".join(as_text(row.get(col)).lower() for col in BASELINE_KEY_COLUMNS)


def config_without_duration_key(row: pd.Series | dict) -> str:
    columns = ["platform", "product_model", "device_model", "android_version", "cpu", "ram", "storage"]
    return "|".join(as_text(row.get(col)).lower() for col in columns)


def product_duration_key(row: pd.Series | dict) -> str:
    columns = ["platform", "product_model", "device_model", "duration"]
    return "|".join(as_text(row.get(col)).lower() for col in columns)


def config_signature(row: pd.Series | dict) -> str:
    columns = ["android_version", "cpu", "ram", "storage"]
    return "|".join(as_text(row.get(col)).lower() for col in columns)


def score_android(ug_value, competitor_value) -> tuple[float, str]:
    ug = parse_android_version(ug_value)
    competitor = parse_android_version(competitor_value)
    if ug is None or competitor is None:
        return 6, "android_missing"
    diff = competitor - ug
    if abs(diff) < 0.000001:
        return 15, "android_same"
    if diff > 0:
        return (12 if diff <= 2 else 10), "android_competitor_higher"
    if diff == -1:
        return 8, "android_competitor_lower_1"
    return 4, "android_competitor_lower_2_plus"


def score_numeric(ug_value, competitor_value, full: float, higher_cap: float, higher_weight: float, lower_cap: float, lower_weight: float, missing_score: float, label: str) -> tuple[float, str]:
    ug = clean_number(ug_value)
    competitor = clean_number(competitor_value)
    if ug is None or competitor is None or ug <= 0:
        return missing_score, f"{label}_missing"
    if abs(competitor - ug) < 0.000001:
        return full, f"{label}_same"
    if competitor > ug:
        penalty = min(higher_cap, (competitor - ug) / ug * higher_weight)
        return full - penalty, f"{label}_competitor_higher"
    penalty = min(lower_cap, (ug - competitor) / ug * lower_weight)
    return full - penalty, f"{label}_competitor_lower"


def score_regions(ug_regions, competitor_regions) -> tuple[float, str]:
    ug_set = parse_region_set(ug_regions)
    competitor_set = parse_region_set(competitor_regions)
    if not ug_set or not competitor_set:
        return 5, "region_missing"
    intersection_count = len(ug_set & competitor_set)
    if intersection_count == 0:
        return 0, "region_no_overlap"
    return min(10, 10 * intersection_count / len(ug_set)), "region_overlap"


def score_duration(ug_days, competitor_days) -> tuple[float, str]:
    ug = clean_number(ug_days)
    competitor = clean_number(competitor_days)
    if ug is None or competitor is None or ug <= 0:
        return 0, "duration_missing"
    diff_ratio = abs(competitor - ug) / ug
    if diff_ratio < 0.000001:
        return 10, "duration_same"
    if diff_ratio <= 0.15:
        return 7, "duration_diff_within_15pct"
    if diff_ratio <= 0.30:
        return 4, "duration_diff_within_30pct"
    return 1, "duration_diff_over_30pct"


def comparability_level(score: float, config: dict) -> str:
    thresholds = config.get("similarity_thresholds", {})
    if score >= thresholds.get("strong_match", 90):
        return "strong_match"
    if score >= thresholds.get("adjusted_match", 75):
        return "adjusted_match"
    if score >= thresholds.get("weak_match", 60):
        return "weak_match"
    return "not_comparable"


def compute_similarity(ug_row: pd.Series | dict, competitor_row: pd.Series | dict, config: dict) -> tuple[float, str, str]:
    parts = []
    notes = []
    score, note = score_android(ug_row.get("android_version"), competitor_row.get("android_version"))
    parts.append(score)
    notes.append(note)
    score, note = score_numeric(ug_row.get("cpu"), competitor_row.get("cpu"), 25, 12, 20, 20, 30, 8, "cpu")
    parts.append(score)
    notes.append(note)
    score, note = score_numeric(ug_row.get("ram"), competitor_row.get("ram"), 25, 10, 15, 22, 35, 8, "ram")
    parts.append(score)
    notes.append(note)
    score, note = score_numeric(ug_row.get("storage"), competitor_row.get("storage"), 15, 6, 10, 12, 20, 5, "storage")
    parts.append(score)
    notes.append(note)
    score, note = score_regions(ug_row.get("supported_server_regions"), competitor_row.get("supported_server_regions"))
    parts.append(score)
    notes.append(note)
    score, note = score_duration(ug_row.get("duration_days"), competitor_row.get("duration_days"))
    parts.append(score)
    notes.append(note)
    total = round(sum(parts), 2)
    return total, comparability_level(total, config), "; ".join(notes)


def quality_score(row: pd.Series | dict) -> tuple[float | None, str]:
    cpu = row.get("_cpu_num")
    ram = row.get("_ram_gb")
    storage = row.get("_storage_gb")
    android = row.get("_android_num")
    missing_fields = [
        name
        for name, value in [("cpu", cpu), ("ram", ram), ("storage", storage), ("android", android)]
        if value is None or missing(value)
    ]
    if missing_fields:
        return None, "quality_adjustment_missing_fields:" + ",".join(missing_fields)
    return 0.35 * float(cpu) + 0.35 * float(ram) + 0.20 * math.sqrt(float(storage)) + 0.10 * float(android), ""


def quality_adjustment(ug_row: pd.Series | dict, competitor_row: pd.Series | dict, level: str, config: dict) -> tuple[float | None, float | None, str]:
    if level == "not_comparable":
        return None, None, "not_comparable_excluded_from_quality_adjustment"
    competitor_effective = competitor_row.get("effective_price_30d")
    if competitor_effective is None or missing(competitor_effective):
        return None, None, "quality_adjustment_missing_fields:competitor_effective_price_30d"
    ug_score, ug_note = quality_score(ug_row)
    competitor_score, competitor_note = quality_score(competitor_row)
    if ug_score is None or competitor_score is None or competitor_score == 0:
        notes = [note for note in [ug_note, competitor_note] if note]
        return None, None, "; ".join(notes) or "quality_adjustment_missing_fields"
    factor = ug_score / competitor_score
    factor = max(config.get("quality_adjustment_factor_min", 0.75), min(config.get("quality_adjustment_factor_max", 1.35), factor))
    adjusted = float(competitor_effective) * factor
    return round_or_none(factor), round_or_none(adjusted), ""


def manual_mapping_for_ug(ug_row: pd.Series | dict, config: dict) -> dict | None:
    ug_model = normalize_token(ug_row.get("product_model"))
    for mapping in config.get("manual_pairings", []):
        aliases = [normalize_token(alias) for alias in mapping.get("ug_product_models", [])]
        if any(alias and alias in ug_model for alias in aliases):
            return mapping
    return None


def candidate_matches_manual(candidate_row: pd.Series | dict, manual_rule: dict) -> bool:
    """Match manual product aliases exactly, not by substring.

    The old substring match made alias "VIP" match "KVIP", "SVIP", and "XVIP".
    That is why UgPhone GVIP still paired to VSPhone KVIP even after the
    manual rule was changed to VIP.  Compare against normalized row-level
    product/model fields exactly, and only fall back to tokenized text for
    genuinely non-plan aliases.
    """
    fields = [
        normalize_token(candidate_row.get("product_model")),
        normalize_token(candidate_row.get("device_model")),
        normalize_token(candidate_row.get("product_name")),
    ]
    fields = [field for field in fields if field]
    haystack = product_text(candidate_row)
    for alias in manual_rule.get("aliases", []):
        token = normalize_token(alias)
        if not token:
            continue
        if token in fields:
            return True
        # For non-plan descriptive aliases, allow fallback text matching.
        # Never allow VIP to match KVIP/SVIP/XVIP by substring.
        if token not in {"vip", "kvip", "svip", "xvip", "mvip", "uvip", "basic"} and token in haystack:
            return True
    return False


def select_pairings_for_platform(
    ug_row: pd.Series,
    candidates: pd.DataFrame,
    platform: str,
    config: dict,
) -> list[dict]:
    if candidates.empty:
        return []
    manual_mapping = manual_mapping_for_ug(ug_row, config)
    manual_rules = []
    if manual_mapping:
        manual_rules = manual_mapping.get("competitors", {}).get(platform, [])

    scored = []
    for _, candidate in candidates.iterrows():
        score, level, notes = compute_similarity(ug_row, candidate, config)
        manual_notes = []
        source = "auto_top_score"
        if manual_rules:
            matched_rules = [rule for rule in manual_rules if candidate_matches_manual(candidate, rule)]
            if matched_rules:
                source = "manual_mapping"
                manual_notes = [as_text(rule.get("notes")) for rule in matched_rules if as_text(rule.get("notes"))]
            else:
                continue
        scored.append(
            {
                "score": score,
                "level": level,
                "source": source,
                "notes": "; ".join([*manual_notes, notes]).strip("; "),
                "candidate": candidate,
            }
        )

    if not scored and manual_rules:
        for _, candidate in candidates.iterrows():
            score, level, notes = compute_similarity(ug_row, candidate, config)
            scored.append(
                {
                    "score": score,
                    "level": level,
                    "source": "auto_top_score",
                    "notes": "manual_mapping_candidate_not_found; " + notes,
                    "candidate": candidate,
                }
            )

    top_n = int(config.get("auto_top_n", 3))
    scored.sort(key=lambda item: (item["score"], -abs((item["candidate"].get("duration_days") or 0) - (ug_row.get("duration_days") or 0))), reverse=True)
    return scored[:top_n]


def pairing_row(ug_row: pd.Series, competitor_row: pd.Series, score: float, level: str, source: str, notes: str) -> dict:
    return {
        "_ug_row_id": ug_row.get("_row_id"),
        "_competitor_row_id": competitor_row.get("_row_id"),
        "ug_platform": as_text(ug_row.get("platform")),
        "ug_product_model": as_text(ug_row.get("product_model")),
        "ug_device_model": as_text(ug_row.get("device_model")),
        "ug_android_version": as_text(ug_row.get("android_version")),
        "ug_cpu": as_text(ug_row.get("cpu")),
        "ug_ram": as_text(ug_row.get("ram")),
        "ug_storage": as_text(ug_row.get("storage")),
        "ug_duration": as_text(ug_row.get("duration")),
        "competitor_platform": as_text(competitor_row.get("platform")),
        "competitor_product_model": as_text(competitor_row.get("product_model")),
        "competitor_device_model": as_text(competitor_row.get("device_model")),
        "competitor_android_version": as_text(competitor_row.get("android_version")),
        "competitor_cpu": as_text(competitor_row.get("cpu")),
        "competitor_ram": as_text(competitor_row.get("ram")),
        "competitor_storage": as_text(competitor_row.get("storage")),
        "competitor_duration": as_text(competitor_row.get("duration")),
        "config_similarity_score": score,
        "comparability_level": level,
        "recommended_pairing_source": source,
        "pairing_notes": notes,
    }


def build_pairing_rows(enriched_current: pd.DataFrame, config: dict) -> pd.DataFrame:
    if enriched_current.empty:
        return pd.DataFrame(columns=PAIRING_COLUMNS)
    base_platform = normalize_platform_name(config.get("base_platform", BASE_PLATFORM))
    competitor_platforms = [normalize_platform_name(platform) for platform in config.get("competitor_platforms", COMPETITOR_PLATFORMS)]
    platform_series = enriched_current["platform"].map(normalize_platform_name)
    ug_rows = enriched_current[platform_series == base_platform].copy()
    if not ug_rows.empty:
        ug_rows.loc[:, "platform"] = base_platform
    rows = []
    for _, ug_row in ug_rows.iterrows():
        for platform in competitor_platforms:
            candidates = enriched_current[platform_series == platform].copy()
            if not candidates.empty:
                candidates.loc[:, "platform"] = platform
            selected = select_pairings_for_platform(ug_row, candidates, platform, config)
            for item in selected:
                rows.append(
                    pairing_row(
                        ug_row,
                        item["candidate"],
                        item["score"],
                        item["level"],
                        item["source"],
                        item["notes"],
                    )
                )
    columns = ["_ug_row_id", "_competitor_row_id", *PAIRING_COLUMNS]
    return pd.DataFrame(rows, columns=columns)


def build_quality_adjusted_price_rows(pairings: pd.DataFrame, enriched_current: pd.DataFrame, config: dict) -> pd.DataFrame:
    if pairings.empty or enriched_current.empty:
        return pd.DataFrame(columns=QUALITY_DETAIL_COLUMNS)
    by_id = {row["_row_id"]: row for _, row in enriched_current.iterrows()}
    rows = []
    for _, pair in pairings.iterrows():
        ug_row = by_id.get(pair.get("_ug_row_id"))
        competitor_row = by_id.get(pair.get("_competitor_row_id"))
        if ug_row is None or competitor_row is None:
            continue
        factor, adjusted_price, adjustment_note = quality_adjustment(
            ug_row,
            competitor_row,
            as_text(pair.get("comparability_level")),
            config,
        )
        ug_effective = ug_row.get("effective_price_30d")
        adjusted_delta = None
        adjusted_delta_pct = None
        if adjusted_price is not None and ug_effective is not None and not missing(ug_effective):
            adjusted_delta = adjusted_price - float(ug_effective)
            adjusted_delta_pct = adjusted_delta / float(ug_effective) if float(ug_effective) else None
        notes = "; ".join(
            item
            for item in [
                as_text(pair.get("pairing_notes")),
                adjustment_note,
                as_text(competitor_row.get("notes")),
            ]
            if item
        )
        rows.append(
            {
                "ug_product_model": as_text(ug_row.get("product_model")),
                "ug_config": config_text(ug_row),
                "ug_duration_days": ug_row.get("duration_days"),
                "ug_device_count": ug_row.get("device_count"),
                "ug_effective_price_30d": ug_effective,
                "ug_list_price_30d": ug_row.get("list_price_30d"),
                "ug_discount_rate": ug_row.get("discount_rate"),
                "ug_price_basis": ug_row.get("price_basis"),
                "competitor_platform": as_text(competitor_row.get("platform")),
                "competitor_product_model": as_text(competitor_row.get("product_model")),
                "competitor_config": config_text(competitor_row),
                "competitor_duration_days": competitor_row.get("duration_days"),
                "competitor_device_count": competitor_row.get("device_count"),
                "competitor_effective_price_30d": competitor_row.get("effective_price_30d"),
                "competitor_list_price_30d": competitor_row.get("list_price_30d"),
                "competitor_discount_rate": competitor_row.get("discount_rate"),
                "competitor_price_basis": competitor_row.get("price_basis"),
                "config_similarity_score": pair.get("config_similarity_score"),
                "quality_adjustment_factor": factor,
                "quality_adjusted_price_30d": adjusted_price,
                "adjusted_delta": round_or_none(adjusted_delta),
                "adjusted_delta_pct": round_or_none(adjusted_delta_pct),
                "comparability_level": pair.get("comparability_level"),
                "recommended_pairing_source": pair.get("recommended_pairing_source"),
                "promotion_text": as_text(competitor_row.get("promotion_text")),
                "supported_server_regions": as_text(competitor_row.get("supported_server_regions")),
                "notes": notes,
            }
        )
    return pd.DataFrame(rows, columns=QUALITY_DETAIL_COLUMNS)


def price_position_label(index_value, config: dict) -> str:
    if index_value is None or missing(index_value):
        return "unknown"
    thresholds = config.get("relative_index_thresholds", {})
    value = float(index_value)
    if value < thresholds.get("below_market", 90):
        return "below_market"
    if value <= thresholds.get("competitive", 105):
        return "competitive"
    if value <= thresholds.get("slightly_high", 115):
        return "slightly_high"
    return "high"


def build_relative_index_rows(detail_rows: pd.DataFrame, config: dict) -> pd.DataFrame:
    if detail_rows.empty:
        return pd.DataFrame(columns=RELATIVE_INDEX_COLUMNS)
    rows = []
    group_columns = ["ug_product_model", "ug_config", "ug_duration_days", "ug_effective_price_30d"]
    for key, group in detail_rows.groupby(group_columns, dropna=False, sort=False):
        ug_model, ug_config, ug_days, ug_effective = key
        core = group[
            group["comparability_level"].isin(["strong_match", "adjusted_match"])
            & group["quality_adjusted_price_30d"].notna()
        ]
        weak = group[
            (group["comparability_level"] == "weak_match")
            & group["quality_adjusted_price_30d"].notna()
        ]
        core_prices = [float(value) for value in core["quality_adjusted_price_30d"].dropna().tolist()]
        weak_prices = [float(value) for value in weak["quality_adjusted_price_30d"].dropna().tolist()]
        competitor_median = median(core_prices) if core_prices else None
        weak_median = median(weak_prices) if weak_prices else None
        relative_index = None
        if competitor_median and ug_effective is not None and not missing(ug_effective):
            relative_index = float(ug_effective) / competitor_median * 100
        label = price_position_label(relative_index, config)
        if label == "high":
            alert = "critical"
            reason = "abnormal_unexplained"
        elif label == "slightly_high":
            alert = "warning"
            reason = "abnormal_unexplained"
        elif competitor_median is None and weak_median is not None:
            alert = "info"
            reason = "weak_match_only"
        elif competitor_median is None:
            alert = "info"
            reason = "not_enough_core_competitors"
        else:
            alert = "none"
            reason = "unchanged"
        rows.append(
            {
                "ug_product_model": ug_model,
                "ug_config": ug_config,
                "ug_duration_days": ug_days,
                "ug_effective_price_30d": ug_effective,
                "competitor_median_quality_adjusted_price_30d": round_or_none(competitor_median),
                "competitor_count_core": int(len(core)),
                "competitor_count_weak": int(len(weak)),
                "weak_median_quality_adjusted_price_30d": round_or_none(weak_median),
                "ugphone_relative_index": round_or_none(relative_index),
                "price_position_label": label,
                "alert_level": alert,
                "reason_code": reason,
                "notes": "core uses strong_match and adjusted_match only; weak_match median is informational.",
            }
        )
    return pd.DataFrame(rows, columns=RELATIVE_INDEX_COLUMNS)


def aggregate_for_reason(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    work = df.copy()
    work["_identity_key"] = work.apply(identity_key, axis=1)
    rows = []
    for key, group in work.groupby("_identity_key", dropna=False, sort=False):
        first = group.iloc[0]
        effective_values = pd.to_numeric(group.get("effective_price_30d"), errors="coerce").dropna()
        list_values = pd.to_numeric(group.get("list_price_30d"), errors="coerce").dropna()
        discount_values = pd.to_numeric(group.get("discount_rate"), errors="coerce").dropna()
        row = {col: first.get(col) for col in work.columns if not col.startswith("_")}
        row["_identity_key"] = key
        row["effective_price_30d"] = float(effective_values.min()) if not effective_values.empty else None
        row["list_price_30d"] = float(list_values.min()) if not list_values.empty else None
        row["discount_rate"] = float(discount_values.max()) if not discount_values.empty else None
        row["promotion_text"] = unique_text(group.get("promotion_text", []))
        row["supported_server_regions"] = unique_text(group.get("supported_server_regions", []))
        row["stock_status"] = unique_text(group.get("stock_status", []))
        rows.append(row)
    return pd.DataFrame(rows)


def unique_text(values: Iterable, sep: str = "; ") -> str:
    seen = []
    for value in values:
        text = as_text(value)
        if text and text not in seen:
            seen.append(text)
    return sep.join(seen)


def build_duration_sets(df: pd.DataFrame) -> dict[str, set[str]]:
    sets: dict[str, set[str]] = {}
    if df.empty:
        return sets
    for _, row in df.iterrows():
        key = config_without_duration_key(row)
        sets.setdefault(key, set()).add(as_text(row.get("duration")))
    return sets


def build_config_sets(df: pd.DataFrame) -> dict[str, set[str]]:
    sets: dict[str, set[str]] = {}
    if df.empty:
        return sets
    for _, row in df.iterrows():
        key = product_duration_key(row)
        sets.setdefault(key, set()).add(config_signature(row))
    return sets


def ratio_index(current, baseline) -> float | None:
    current_num = clean_number(current)
    baseline_num = clean_number(baseline)
    if current_num is None or baseline_num is None or baseline_num == 0:
        return None
    return current_num / baseline_num * 100


def change_reason_and_alert(current_row: pd.Series | None, baseline_row: pd.Series | None, helpers: dict) -> tuple[str, str, str]:
    notes = []
    codes = []
    if current_row is None:
        return "stock_status_change", "info", "current_row_missing_from_latest_collection"
    if baseline_row is None:
        return "abnormal_unexplained", "warning", "baseline_row_missing_for_current_product"

    own_index = ratio_index(current_row.get("effective_price_30d"), baseline_row.get("effective_price_30d"))
    list_index = ratio_index(current_row.get("list_price_30d"), baseline_row.get("list_price_30d"))
    discount_change = None
    if current_row.get("discount_rate") is not None and baseline_row.get("discount_rate") is not None:
        discount_change = float(current_row.get("discount_rate")) - float(baseline_row.get("discount_rate"))

    if product_duration_key(current_row) in helpers["config_changed_keys"]:
        codes.append("config_change")
    if config_without_duration_key(current_row) in helpers["duration_changed_keys"]:
        codes.append("duration_structure_change")
    if as_text(current_row.get("stock_status")) != as_text(baseline_row.get("stock_status")):
        codes.append("stock_status_change")
    if parse_region_set(current_row.get("supported_server_regions")) != parse_region_set(
        baseline_row.get("supported_server_regions")
    ):
        codes.append("region_supply_change")
    if list_index is not None and abs(list_index - 100) > 0.0001:
        codes.append("list_price_change")
    promo_text_changed = as_text(current_row.get("promotion_text")) != as_text(baseline_row.get("promotion_text"))
    if promo_text_changed or (list_index is not None and abs(list_index - 100) <= 0.0001 and discount_change is not None and abs(discount_change) >= 0.01):
        codes.append("promo_change")
    if own_index is not None and abs(own_index - 100) > 10 and not codes:
        codes.append("abnormal_unexplained")
        notes.append("effective_price_30d_changed_without_known_explanation")
    if not codes:
        codes.append("unchanged")

    if list_index is not None and abs(list_index - 100) > 0.0001:
        alert = "critical"
    elif own_index is not None and own_index > 120:
        alert = "critical"
    elif own_index is not None and abs(own_index - 100) > 10:
        alert = "warning"
    elif discount_change is not None and abs(discount_change) >= 0.10:
        alert = "warning"
    elif any(code in codes for code in ["promo_change", "region_supply_change", "stock_status_change"]):
        alert = "info"
    elif "config_change" in codes or "duration_structure_change" in codes:
        alert = "warning"
    else:
        alert = "none"

    return "; ".join(dict.fromkeys(codes)), alert, "; ".join(notes)


def build_rationality_rows(current: pd.DataFrame, baseline: pd.DataFrame | None) -> pd.DataFrame:
    if baseline is None or baseline.empty:
        return pd.DataFrame(
            [
                {
                    "reason_code": "baseline_missing",
                    "alert_level": "info",
                    "notes": "baseline missing or empty; baseline-dependent price rationality fields are intentionally blank.",
                }
            ],
            columns=REASON_COLUMNS,
        )

    current_summary = aggregate_for_reason(current)
    baseline_summary = aggregate_for_reason(baseline)
    current_by_key = {row["_identity_key"]: row for _, row in current_summary.iterrows()}
    baseline_by_key = {row["_identity_key"]: row for _, row in baseline_summary.iterrows()}
    current_duration_sets = build_duration_sets(current)
    baseline_duration_sets = build_duration_sets(baseline)
    current_config_sets = build_config_sets(current)
    baseline_config_sets = build_config_sets(baseline)
    helpers = {
        "duration_changed_keys": {
            key
            for key in set(current_duration_sets) | set(baseline_duration_sets)
            if current_duration_sets.get(key, set()) != baseline_duration_sets.get(key, set())
        },
        "config_changed_keys": {
            key
            for key in set(current_config_sets) | set(baseline_config_sets)
            if current_config_sets.get(key, set()) != baseline_config_sets.get(key, set())
        },
    }

    rows = []
    for key in sorted(set(current_by_key) | set(baseline_by_key)):
        current_row = current_by_key.get(key)
        baseline_row = baseline_by_key.get(key)
        source_row = current_row if current_row is not None else baseline_row
        reason_code, alert, notes = change_reason_and_alert(current_row, baseline_row, helpers)
        own_index = ratio_index(
            current_row.get("effective_price_30d") if current_row is not None else None,
            baseline_row.get("effective_price_30d") if baseline_row is not None else None,
        )
        list_index = ratio_index(
            current_row.get("list_price_30d") if current_row is not None else None,
            baseline_row.get("list_price_30d") if baseline_row is not None else None,
        )
        discount_change = None
        if (
            current_row is not None
            and baseline_row is not None
            and current_row.get("discount_rate") is not None
            and baseline_row.get("discount_rate") is not None
        ):
            discount_change = float(current_row.get("discount_rate")) - float(baseline_row.get("discount_rate"))
        rows.append(
            {
                "platform": as_text(source_row.get("platform")),
                "product_model": as_text(source_row.get("product_model")),
                "device_model": as_text(source_row.get("device_model")),
                "android_version": as_text(source_row.get("android_version")),
                "cpu": as_text(source_row.get("cpu")),
                "ram": as_text(source_row.get("ram")),
                "storage": as_text(source_row.get("storage")),
                "duration_days": source_row.get("duration_days"),
                "baseline_effective_price_30d": baseline_row.get("effective_price_30d") if baseline_row is not None else None,
                "current_effective_price_30d": current_row.get("effective_price_30d") if current_row is not None else None,
                "own_price_index": round_or_none(own_index),
                "baseline_list_price_30d": baseline_row.get("list_price_30d") if baseline_row is not None else None,
                "current_list_price_30d": current_row.get("list_price_30d") if current_row is not None else None,
                "list_price_index": round_or_none(list_index),
                "baseline_discount_rate": baseline_row.get("discount_rate") if baseline_row is not None else None,
                "current_discount_rate": current_row.get("discount_rate") if current_row is not None else None,
                "discount_rate_change": round_or_none(discount_change),
                "baseline_promotion_text": as_text(baseline_row.get("promotion_text")) if baseline_row is not None else "",
                "current_promotion_text": as_text(current_row.get("promotion_text")) if current_row is not None else "",
                "baseline_supported_server_regions": as_text(baseline_row.get("supported_server_regions")) if baseline_row is not None else "",
                "current_supported_server_regions": as_text(current_row.get("supported_server_regions")) if current_row is not None else "",
                "reason_code": reason_code,
                "alert_level": alert,
                "notes": notes,
            }
        )
    return pd.DataFrame(rows, columns=REASON_COLUMNS)


def to_chinese_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={col: QUALITY_HEADER_CN.get(col, col) for col in df.columns})


def build_explanation_sheet() -> pd.DataFrame:
    rows = [
        ("为什么不能只按套餐名配对", "不同平台的 VIP/KVIP/SVIP 命名并不等价，套餐名只能作为推荐映射线索，不能作为价格主键。"),
        ("为什么使用30天等效价", "1天、3天、7天、15天、30天、60天、90天、180天、365天和小时套餐需要先归一到同一周期，才能比较真实月化成本。"),
        ("为什么需要质量调整价", "竞品 CPU、内存、存储、安卓版本可能高于或低于 UgPhone，直接比裸价会误判贵或便宜。"),
        ("strong_match", "配置相似度分数 >= 90，可作为核心定价参考。"),
        ("adjusted_match", "配置相似度分数 75-90，可进入核心定价参考，但应结合备注看调整原因。"),
        ("weak_match", "配置相似度分数 60-75，只作辅助观察，不进入 UG 相对竞品核心中位数。"),
        ("not_comparable", "配置相似度分数 < 60，不进入核心判断，质量调整价也默认留空。"),
        ("ugphone_relative_index", "UgPhone 30天等效实付价 / 核心竞品质量调整价中位数 * 100；低于90明显低于竞品，90-105有竞争力，105-115略高，高于115明显偏高。"),
        ("reason_code", "用于解释价格变化来源，如 promo_change、list_price_change、config_change、region_supply_change、duration_structure_change、stock_status_change、abnormal_unexplained。"),
    ]
    return pd.DataFrame(rows, columns=["项目", "说明"])


def write_quality_workbook(
    path: Path,
    pairings: pd.DataFrame,
    details: pd.DataFrame,
    relative_index: pd.DataFrame,
    rationality: pd.DataFrame,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    visible_pairings = pairings[[col for col in PAIRING_COLUMNS if col in pairings.columns]].copy()
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        to_chinese_columns(visible_pairings).to_excel(writer, sheet_name="配置配对建议", index=False)
        to_chinese_columns(details).to_excel(writer, sheet_name="质量调整价格明细", index=False)
        to_chinese_columns(relative_index).to_excel(writer, sheet_name="UG相对竞品指数", index=False)
        to_chinese_columns(rationality).to_excel(writer, sheet_name="变价合理性判断", index=False)
        build_explanation_sheet().to_excel(writer, sheet_name="说明", index=False)


def build_daily_near_config_comparison(details: pd.DataFrame) -> pd.DataFrame:
    if details.empty:
        return pd.DataFrame(columns=DAILY_NEAR_CONFIG_COLUMNS)
    cols = [col for col in DAILY_NEAR_CONFIG_COLUMNS if col in details.columns]
    return details[cols].copy()


def write_quality_price_report(
    output_dir: Path,
    current_df: pd.DataFrame,
    baseline_df: pd.DataFrame | None = None,
    config_path: Path | None = None,
) -> tuple[dict, pd.DataFrame]:
    config = load_quality_price_config(config_path)
    if not config.get("enabled", True):
        return {"enabled": False, "reason": "disabled_by_config"}, pd.DataFrame(columns=DAILY_NEAR_CONFIG_COLUMNS)

    current = add_standardized_price_fields(current_df, int(config.get("effective_period_days", EFFECTIVE_PERIOD_DAYS)))
    current["_row_id"] = list(range(len(current)))
    base_platform = normalize_platform_name(config.get("base_platform", BASE_PLATFORM))
    platform_series = current["platform"].map(normalize_platform_name) if "platform" in current else pd.Series(dtype=object)
    ug_rows = current[platform_series == base_platform].copy()
    if ug_rows.empty:
        return {"enabled": False, "reason": "missing_ugphone_rows"}, pd.DataFrame(columns=DAILY_NEAR_CONFIG_COLUMNS)

    baseline = None
    if baseline_df is not None and not baseline_df.empty:
        baseline = add_standardized_price_fields(
            baseline_df,
            int(config.get("effective_period_days", EFFECTIVE_PERIOD_DAYS)),
        )

    pairings = build_pairing_rows(current, config)
    details = build_quality_adjusted_price_rows(pairings, current, config)
    relative_index = build_relative_index_rows(details, config)
    rationality = build_rationality_rows(current, baseline)
    report_path = output_dir / "quality_price_report.xlsx"
    write_quality_workbook(report_path, pairings, details, relative_index, rationality)
    daily_near = build_daily_near_config_comparison(details)

    critical_alerts = 0
    warning_alerts = 0
    for frame in [relative_index, rationality]:
        if not frame.empty and "alert_level" in frame.columns:
            critical_alerts += int((frame["alert_level"] == "critical").sum())
            warning_alerts += int((frame["alert_level"] == "warning").sum())

    ug_config_count = int(
        ug_rows[["product_model", "device_model", "android_version", "cpu", "ram", "storage", "duration"]]
        .drop_duplicates()
        .shape[0]
    )
    return (
        {
            "enabled": True,
            "report_path": str(report_path),
            "ug_config_count": ug_config_count,
            "pairing_rows": int(len(pairings)),
            "quality_adjusted_rows": int(len(details)),
            "relative_index_rows": int(len(relative_index)),
            "critical_alerts": critical_alerts,
            "warning_alerts": warning_alerts,
            "not_comparable_rows": int((pairings["comparability_level"] == "not_comparable").sum()) if not pairings.empty else 0,
        },
        daily_near,
    )
