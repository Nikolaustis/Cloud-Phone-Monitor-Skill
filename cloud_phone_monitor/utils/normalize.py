import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo


PRICE_RE = re.compile(
    r"(?P<currency>US\$|USD|HK\$|NT\$|SGD|RMB|CNY|￥|¥|\$|€|£)\s*(?P<price>\d+(?:[.,]\d+)?)"
    r"|(?P<price2>\d+(?:[.,]\d+)?)\s*(?P<currency2>USD|USDT|CNY|RMB|元|美元)",
    re.I,
)
ANDROID_RE = re.compile(r"\bAndroid\s*(?:version)?\s*[:：]?\s*(?P<ver>\d+(?:\.\d+)?)\b", re.I)
RAM_RE = re.compile(r"\b(?P<ram>\d+(?:\.\d+)?)\s*(?:GB|G)\s*(?:RAM|Memory|内存)?\b", re.I)
STORAGE_RE = re.compile(r"\b(?P<storage>\d+(?:\.\d+)?)\s*(?:GB|G|TB|T)\s*(?:Storage|ROM|Disk|存储|容量)?\b", re.I)
CPU_RE = re.compile(r"\b(?P<cpu>\d+\s*[- ]?core|Snapdragon\s*\w+|MTK\s*\w+|Dimensity\s*\w+|Exynos\s*\w+)\b", re.I)
DURATION_RE = re.compile(
    r"\b(?P<num>\d+)\s*(?P<unit>minute|minutes|min|hour|hours|day|days|week|weeks|month|months|year|years|个月|月|天|日|周|年)\b",
    re.I,
)
PLAN_RE = re.compile(r"\b(?P<plan>VIP|KVIP|SVIP|XVIP|VIP\s*\d+|KVIP\s*\d+|SVIP\s*\d+|XVIP\s*\d+|V\d{2,4}|A\d{2,4})\b", re.I)
REGION_RE = re.compile(
    r"\b(?P<region>US|USA|United States|Taiwan|TW|Singapore|SG|Hong Kong|HK|Japan|JP|Korea|KR|Thailand|TH|Vietnam|VN|Malaysia|MY|Indonesia|ID|Brazil|BR|Europe|EU)\b"
    r"|(?P<region_cn>美国|台湾|新加坡|香港|日本|韩国|泰国|越南|马来西亚|印尼|巴西|欧洲)",
    re.I,
)
DEVICE_RE = re.compile(
    r"\b(?P<device>(?:Samsung|Galaxy|Google Pixel|Pixel|Redmi|Xiaomi|OPPO|Vivo|OnePlus|Huawei|Honor|Realme|Nubia|ROG|Asus|S23|S24|S25|Poco)[\w\s+\-./]{0,35})\b",
    re.I,
)

SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "x-csrf-token", "x-xsrf-token", "token"}


def now_pair(local_tz: str = "Asia/Shanghai") -> tuple[str, str]:
    utc = datetime.now(timezone.utc)
    local = utc.astimezone(ZoneInfo(local_tz))
    return utc.isoformat(timespec="seconds"), local.isoformat(timespec="seconds")


def safe_filename(value: str, max_len: int = 80) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("_")
    return cleaned[:max_len] or "file"


def compact_text(text: str | None, max_len: int = 4000) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def redact_headers(headers: Dict[str, str] | None) -> Dict[str, str]:
    if not headers:
        return {}
    out = {}
    for key, val in headers.items():
        if key.lower() in SENSITIVE_HEADERS or "token" in key.lower():
            out[key] = "[REDACTED]"
        else:
            out[key] = val
    return out


def redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            lk = str(k).lower()
            if lk in SENSITIVE_HEADERS or "token" in lk or "password" in lk:
                result[k] = "[REDACTED]"
            else:
                result[k] = redact_payload(v)
        return result
    if isinstance(value, list):
        return [redact_payload(v) for v in value]
    return value


def first_match(regex: re.Pattern, text: str, group: str) -> Optional[str]:
    m = regex.search(text or "")
    if not m:
        return None
    return m.groupdict().get(group)


def parse_price(text: str) -> tuple[Optional[str], Optional[str]]:
    m = PRICE_RE.search(text or "")
    if not m:
        return None, None
    currency = m.group("currency") or m.group("currency2")
    price = m.group("price") or m.group("price2")
    if price:
        price = price.replace(",", ".")
    return currency, price


def parse_duration(text: str) -> tuple[Optional[str], Optional[str]]:
    m = DURATION_RE.search(text or "")
    if not m:
        # common package periods without explicit number
        lowered = (text or "").lower()
        for period in ["minute", "day", "week", "month", "year"]:
            if period in lowered:
                return period, period
        return None, None
    num = m.group("num")
    unit = m.group("unit")
    unit_l = unit.lower()
    if unit_l in {"min", "minute", "minutes"}:
        period = "minute"
    elif unit_l in {"hour", "hours"}:
        period = "hour"
    elif unit_l in {"day", "days", "天", "日"}:
        period = "day"
    elif unit_l in {"week", "weeks", "周"}:
        period = "week"
    elif unit_l in {"month", "months", "个月", "月"}:
        period = "month"
    elif unit_l in {"year", "years", "年"}:
        period = "year"
    else:
        period = unit_l
    return f"{num} {period}", period


def parse_stock(text: str) -> Optional[str]:
    lowered = (text or "").lower()
    if any(w in lowered for w in ["sold out", "out of stock", "unavailable", "售罄", "不可用", "无货"]):
        return "sold_out"
    if any(w in lowered for w in ["buy", "purchase", "subscribe", "available", "立即购买", "购买", "订阅"]):
        return "available"
    return None


def parse_product_fields(raw_text: str) -> Dict[str, Optional[str]]:
    text = compact_text(raw_text, 4000)
    currency, price = parse_price(text)
    duration, billing_period = parse_duration(text)

    android_match = ANDROID_RE.search(text)
    android_version = android_match.group("ver") if android_match else None

    plan_match = PLAN_RE.search(text)
    plan = plan_match.group("plan").upper().replace(" ", "") if plan_match else None

    region_match = REGION_RE.search(text)
    region = None
    if region_match:
        region = region_match.group("region") or region_match.group("region_cn")

    device_match = DEVICE_RE.search(text)
    device = device_match.group("device").strip() if device_match else None

    cpu_match = CPU_RE.search(text)
    cpu = cpu_match.group("cpu") if cpu_match else None

    ram_match = RAM_RE.search(text)
    ram = None
    if ram_match:
        token = ram_match.group("ram")
        if token:
            ram = f"{token}GB"

    storage_match = STORAGE_RE.search(text)
    storage = None
    if storage_match:
        token = storage_match.group("storage")
        if token:
            storage = f"{token}GB"

    category = None
    lowered = text.lower()
    if any(k in lowered for k in ["cloud phone", "cloud mobile", "云手机", "cloud emulator"]):
        category = "cloud_phone"
    elif any(k in lowered for k in ["real device", "real phone", "真机"]):
        category = "real_device"

    return {
        "currency": currency,
        "price": price,
        "android_version": android_version,
        "product_model": plan,
        "region_selected": region,
        "server_region": region,
        "device_model": device,
        "cpu": cpu,
        "ram": ram,
        "storage": storage,
        "duration": duration,
        "billing_period": billing_period,
        "stock_status": parse_stock(text),
        "product_category": category,
    }


def looks_like_product_payload(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False, default=str)[:20000].lower()
    keywords = [
        "price", "sku", "product", "goods", "plan", "package", "android", "model",
        "region", "duration", "vip", "svip", "xvip", "cloud", "device", "storage"
    ]
    return sum(1 for k in keywords if k in text) >= 2


def iter_product_like_nodes(value: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        if looks_like_product_payload(value):
            yield path, value
        for key, item in value.items():
            yield from iter_product_like_nodes(item, f"{path}.{key}")
    elif isinstance(value, list):
        if value and looks_like_product_payload(value):
            # Yield individual objects when possible so each product row can be audited.
            if all(isinstance(x, dict) for x in value):
                for idx, item in enumerate(value):
                    if looks_like_product_payload(item):
                        yield f"{path}[{idx}]", item
            else:
                yield path, value
        else:
            for idx, item in enumerate(value):
                yield from iter_product_like_nodes(item, f"{path}[{idx}]")
