import re
from typing import Any, Iterable, List

from cloud_phone_monitor.schemas import ProductRecord
from cloud_phone_monitor.utils.normalize import compact_text, now_pair


PRICE_TOKEN_RE = re.compile(
    r"(?P<currency>US\$|USD|HK\$|NT\$|SGD|RMB|CNY|\$|￥|¥)\s*(?P<price>\d+(?:[.,]\d+)?)"
    r"|(?P<price2>\d+(?:[.,]\d+)?)\s*(?P<currency2>USD|USDT|CNY|RMB)",
    re.I,
)
DURATION_TOKEN_RE = re.compile(
    r"(?P<num>\d+)\s*(?P<unit>天|日|小时|小時|分钟|分鐘|分|day|days|week|weeks|month|months|year|years|hour|hours|minute|minutes|min|mins|周|月|年)",
    re.I,
)
ANDROID_RE = re.compile(r"\bAndroid\s*(?P<ver>\d+(?:\.\d+)?)\b|安卓\s*(?P<ver_cn>\d+(?:\.\d+)?)")
CPU_RE = re.compile(r"(?P<cpu>\d+)\s*(?:core|cores|核)(?:\s*cpu)?", re.I)
RAM_RE = re.compile(r"(?P<ram>\d+(?:\.\d+)?)\s*(?:G|GB)\s*RAM\b", re.I)
STORAGE_RE = re.compile(r"(?P<storage>\d+(?:\.\d+)?)\s*(?:G|GB)\s*(?:ROM|Storage)\b", re.I)
PROMO_RE = re.compile(r"(off|limited|discount|promo|优惠|折扣|限时|新用户)", re.I)

REGION_ALIASES = {
    "香港": "Hong Kong",
    "hong kong": "Hong Kong",
    "hk": "Hong Kong",
    "新加坡": "Singapore",
    "singapore": "Singapore",
    "sg": "Singapore",
    "泰国": "Thailand",
    "thailand": "Thailand",
    "th": "Thailand",
    "台湾": "Taiwan",
    "台灣": "Taiwan",
    "taiwan": "Taiwan",
    "tw": "Taiwan",
    "美国": "United States",
    "美國": "United States",
    "united states": "United States",
    "usa": "United States",
    "us": "United States",
    "日本": "Japan",
    "japan": "Japan",
    "jp": "Japan",
    "韩国": "Korea",
    "韓國": "Korea",
    "korea": "Korea",
    "kr": "Korea",
}


def records_from_plan_snapshots(
    platform: str,
    source_url: str,
    snapshots: list[dict],
    timezone: str,
) -> List[ProductRecord]:
    records: List[ProductRecord] = []
    crawl_utc, crawl_local = now_pair(timezone)

    for snapshot in snapshots:
        plan = snapshot.get("plan")
        body_text = snapshot.get("body_text") or ""
        active_texts = snapshot.get("active_texts") or []
        specs = parse_specs(body_text, active_texts)
        seen_card_texts = set()
        card_candidates = list(snapshot.get("cards") or [])
        card_candidates.extend(cards_from_body_text(body_text))

        for card in card_candidates:
            card_text = compact_text(card.get("text") if isinstance(card, dict) else str(card), 1400)
            if not card_text or card_text in seen_card_texts:
                continue
            seen_card_texts.add(card_text)

            prices = price_tokens(card_text)
            duration, billing_period = parse_duration(card_text)
            if not prices or not duration:
                continue

            currency, price = prices[0]
            original_price = None
            for _, candidate in prices[1:]:
                if candidate != price:
                    original_price = candidate
                    break

            promotion_text = card_text if PROMO_RE.search(card_text) else None
            records.append(
                ProductRecord(
                    platform=platform,
                    source_url=source_url,
                    crawl_time_utc=crawl_utc,
                    crawl_time_local=crawl_local,
                    region_selected=specs.get("server_region"),
                    server_region=specs.get("server_region"),
                    currency=currency,
                    product_category="cloud_phone",
                    product_name=plan,
                    product_model=plan,
                    android_version=specs.get("android_version"),
                    cpu=specs.get("cpu"),
                    ram=specs.get("ram"),
                    storage=specs.get("storage"),
                    price=price,
                    original_price=original_price,
                    billing_period=billing_period,
                    duration=duration,
                    stock_status="available",
                    promotion_text=promotion_text,
                    raw_text=card_text,
                    extraction_method="dom_plan_tab",
                    confidence="high",
                    screenshot_path=snapshot.get("screenshot_path"),
                    html_path=snapshot.get("html_path"),
                    notes=f"visible_plan_tab={plan}",
                )
            )

    return records


def cards_from_body_text(body_text: str) -> Iterable[dict]:
    matches = list(DURATION_TOKEN_RE.finditer(body_text or ""))
    for idx, match in enumerate(matches):
        start = max(match.start() - 80, 0) if idx == 0 else match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else min(match.end() + 240, len(body_text))
        text = body_text[start:end]
        if price_tokens(text):
            yield {"text": text}


def price_tokens(text: str) -> list[tuple[str | None, str]]:
    out = []
    for match in PRICE_TOKEN_RE.finditer(text or ""):
        currency = match.group("currency") or match.group("currency2")
        price = match.group("price") or match.group("price2")
        if not price:
            continue
        out.append((normalize_currency(currency), price.replace(",", ".")))
    return out


def normalize_currency(currency: str | None) -> str | None:
    if currency in {"$", "US$", "USD"}:
        return "US$"
    if currency in {"￥", "¥", "RMB", "CNY"}:
        return "CNY"
    return currency


def parse_duration(text: str) -> tuple[str | None, str | None]:
    match = DURATION_TOKEN_RE.search(text or "")
    if not match:
        return None, None
    num = match.group("num")
    unit = match.group("unit").lower()
    if unit in {"天", "日", "day", "days"}:
        period = "day"
    elif unit in {"周", "week", "weeks"}:
        period = "week"
    elif unit in {"月", "month", "months"}:
        period = "month"
    elif unit in {"年", "year", "years"}:
        period = "year"
    elif unit in {"小时", "小時", "hour", "hours"}:
        period = "hour"
    elif unit in {"分钟", "分鐘", "分", "minute", "minutes", "min", "mins"}:
        period = "minute"
    else:
        period = unit
    return f"{num} {period}", period


def parse_specs(body_text: str, active_texts: list[str]) -> dict[str, str | None]:
    text = "\n".join([body_text or "", *active_texts])
    android = None
    android_match = ANDROID_RE.search(text)
    if android_match:
        android = android_match.group("ver") or android_match.group("ver_cn")
    if not android:
        android = first_active_version(active_texts)

    cpu = None
    cpu_match = CPU_RE.search(text)
    if cpu_match:
        cpu = f"{cpu_match.group('cpu')} cores"

    ram = None
    ram_match = RAM_RE.search(text)
    if ram_match:
        ram = f"{ram_match.group('ram')}GB"

    storage = None
    storage_match = STORAGE_RE.search(text)
    if storage_match:
        storage = f"{storage_match.group('storage')}GB"

    return {
        "android_version": android,
        "cpu": cpu,
        "ram": ram,
        "storage": storage,
        "server_region": selected_region(active_texts),
    }


def first_active_version(active_texts: list[str]) -> str | None:
    for text in active_texts:
        if re.fullmatch(r"\d+(?:\.\d+)?", text or ""):
            return text
    return None


def selected_region(active_texts: list[str]) -> str | None:
    haystack = " ".join(active_texts).lower()
    for alias, normalized in REGION_ALIASES.items():
        if re.search(rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])", haystack):
            return normalized
    return None
