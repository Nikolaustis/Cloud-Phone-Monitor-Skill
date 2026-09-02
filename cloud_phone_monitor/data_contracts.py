"""Canonical data contracts for Cloud Phone Monitor.

Product identity and missing-data semantics are centralized here so collection,
baseline, history and Dashboard exports use the same vocabulary.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from cloud_phone_monitor.utils.normalize import canonical_android_version

SCHEMA_VERSION = 9
SKILL_RELEASE = "current"


class AvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    MISSING_COLLECTION = "missing_collection"
    UNAVAILABLE = "unavailable"
    DISCONTINUED = "discontinued"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class DataOrigin(str, Enum):
    CURRENT_OBSERVED = "current_observed"
    HISTORY_OBSERVED = "history_observed"
    CARRY_FORWARD = "carry_forward"
    BASELINE_REFERENCE = "baseline_reference"
    SYNTHETIC = "synthetic"


class DatasetRole(str, Enum):
    CURRENT = "current"
    HISTORICAL = "historical"
    BASELINE = "baseline"


def _clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if isinstance(value, float) and math.isnan(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def _number_token(value: Any) -> str:
    text = _clean(value)
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return text.lower()
    try:
        return f"{float(match.group(0)):g}"
    except Exception:
        return match.group(0)


def duration_days(value: Any) -> str:
    text = _clean(value).lower()
    if not text:
        return ""
    match = re.search(r"(\d+(?:\.\d+)?)\s*(day|days|d|天|日|week|weeks|month|months|year|years)", text)
    if match:
        number = float(match.group(1))
        unit = match.group(2)
        if unit in {"week", "weeks"}:
            number *= 7
        elif unit in {"month", "months"}:
            number *= 30
        elif unit in {"year", "years"}:
            number *= 365
        return f"{number:g}"
    try:
        return f"{float(text):g}"
    except Exception:
        return _number_token(text)


def normalize_platform(value: Any) -> str:
    text = _clean(value)
    return "UgPhone" if text.lower() == "ugphone" else text


def normalize_purchase_mode(value: Any) -> str:
    text = _clean(value).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "subscribe": "subscription",
        "subscribed": "subscription",
        "auto_renew": "subscription",
        "autorenew": "subscription",
        "non_subscription": "non_subscription",
        "nonsubscription": "non_subscription",
        "one_time": "non_subscription",
        "oneoff": "non_subscription",
    }
    return aliases.get(text, text or "unspecified")


def infer_availability_status(stock_status: Any, price: Any = None) -> str:
    stock = _clean(stock_status).lower().replace(" ", "_")
    if stock in {"sold_out", "soldout", "out_of_stock", "unavailable", "disabled"}:
        return AvailabilityStatus.UNAVAILABLE.value
    if stock in {"available", "in_stock", "instock"}:
        return AvailabilityStatus.AVAILABLE.value
    if _clean(price):
        return AvailabilityStatus.AVAILABLE.value
    return AvailabilityStatus.UNKNOWN.value


@dataclass(frozen=True)
class ProductKey:
    platform: str
    product_model: str
    android_version: str
    cpu: str
    ram: str
    storage: str
    region: str
    duration_days: str
    purchase_mode: str

    def as_dict(self) -> dict[str, str]:
        return {
            "platform": self.platform,
            "product_model": self.product_model,
            "android_version": self.android_version,
            "cpu": self.cpu,
            "ram": self.ram,
            "storage": self.storage,
            "region": self.region,
            "duration_days": self.duration_days,
            "purchase_mode": self.purchase_mode,
        }

    def token(self) -> str:
        # Human-readable prefix keeps diagnostics useful; short hash keeps the key compact.
        material = json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
        return f"pk{SCHEMA_VERSION}:{digest}"


def product_key_from_mapping(row: Mapping[str, Any]) -> ProductKey:
    region = row.get("server_region") or row.get("supported_server_regions") or row.get("region_selected")
    regions = sorted({part.strip() for part in re.split(r"[;,|]", _clean(region)) if part.strip()})
    return ProductKey(
        platform=normalize_platform(row.get("platform")),
        product_model=_clean(row.get("product_model")).upper(),
        android_version=canonical_android_version(row.get("android_version")) or "",
        cpu=_number_token(row.get("cpu")),
        ram=_number_token(row.get("ram")),
        storage=_number_token(row.get("storage")),
        region=";".join(regions),
        duration_days=duration_days(row.get("duration_days") or row.get("duration")),
        purchase_mode=normalize_purchase_mode(row.get("purchase_mode")),
    )


def canonical_product_key(row: Mapping[str, Any]) -> str:
    return product_key_from_mapping(row).token()
