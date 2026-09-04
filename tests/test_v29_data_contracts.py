from pathlib import Path
import json

import pandas as pd

from cloud_phone_monitor.data_contracts import (
    AvailabilityStatus,
    DataOrigin,
    SCHEMA_VERSION,
    canonical_product_key,
)
from cloud_phone_monitor.utils.migrations import migrate_products_frame


def test_legacy_android_duplicates_collapse_to_one_product_key() -> None:
    path = Path(__file__).parent / "fixtures" / "v29" / "legacy_android_duplicates.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    migrated = migrate_products_frame(pd.DataFrame(rows), role="historical")
    assert migrated["android_version"].tolist() == ["10", "10"]
    assert migrated["canonical_product_key"].nunique() == 1
    assert set(migrated["schema_version"]) == {SCHEMA_VERSION}
    assert set(migrated["data_origin"]) == {DataOrigin.HISTORY_OBSERVED.value}


def test_dataset_roles_do_not_promote_baseline_to_current() -> None:
    row = pd.DataFrame([{
        "platform": "VSPhone", "product_model": "VIP", "android_version": "12.0",
        "cpu": "4 cores", "ram": "4GB", "storage": "64GB", "duration": "30 day",
        "purchase_mode": "subscription", "price": "5.99", "stock_status": "available",
    }])
    current = migrate_products_frame(row, role="current")
    baseline = migrate_products_frame(row, role="baseline")
    assert current.iloc[0]["dataset_role"] == "current"
    assert current.iloc[0]["data_origin"] == DataOrigin.CURRENT_OBSERVED.value
    assert baseline.iloc[0]["dataset_role"] == "baseline"
    assert baseline.iloc[0]["data_origin"] == DataOrigin.BASELINE_REFERENCE.value
    assert current.iloc[0]["canonical_product_key"] == baseline.iloc[0]["canonical_product_key"]


def test_product_key_is_stable_for_region_order_and_android_integer_format() -> None:
    base = {
        "platform": "UgPhone", "product_model": "GVIP", "cpu": "4 cores", "ram": "4GB",
        "storage": "64GB", "duration": "30 day", "purchase_mode": "subscription",
    }
    a = {**base, "android_version": "13.0", "supported_server_regions": "Singapore; Hong Kong"}
    b = {**base, "android_version": "13", "supported_server_regions": "Hong Kong; Singapore"}
    assert canonical_product_key(a) == canonical_product_key(b)


def test_unavailable_stock_has_explicit_status() -> None:
    frame = migrate_products_frame(pd.DataFrame([{
        "platform": "UgPhone", "product_model": "KVIP", "duration": "30 day",
        "price": "9.99", "stock_status": "sold_out",
    }]), role="current")
    assert frame.iloc[0]["availability_status"] == AvailabilityStatus.UNAVAILABLE.value
