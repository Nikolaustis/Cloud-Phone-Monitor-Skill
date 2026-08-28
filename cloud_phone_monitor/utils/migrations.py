"""Schema migration helpers for persisted product tables."""
from __future__ import annotations

from typing import Any

import pandas as pd

from cloud_phone_monitor.data_contracts import (
    AvailabilityStatus,
    DataOrigin,
    DatasetRole,
    SCHEMA_VERSION,
    canonical_product_key,
    infer_availability_status,
)
from cloud_phone_monitor.utils.normalize import canonical_android_version


def migrate_products_frame(
    frame: pd.DataFrame,
    *,
    role: str | DatasetRole = DatasetRole.HISTORICAL,
) -> pd.DataFrame:
    """Upgrade old product rows to the v29 contract without mutating the caller.

    This is intentionally additive: old CSV/XLSX files remain readable and no
    historical file is rewritten in place.
    """
    if frame is None:
        return frame
    out = frame.copy()
    if out.empty:
        for column in ("schema_version", "availability_status", "data_origin", "dataset_role", "canonical_product_key"):
            if column not in out.columns:
                out[column] = pd.Series(dtype=object)
        return out

    if "android_version" in out.columns:
        out["android_version"] = out["android_version"].map(canonical_android_version)
    for column in ("stock_status", "price", "purchase_mode", "server_region", "supported_server_regions"):
        if column not in out.columns:
            out[column] = None

    role_value = role.value if isinstance(role, DatasetRole) else str(role)
    origin = {
        DatasetRole.CURRENT.value: DataOrigin.CURRENT_OBSERVED.value,
        DatasetRole.BASELINE.value: DataOrigin.BASELINE_REFERENCE.value,
        DatasetRole.HISTORICAL.value: DataOrigin.HISTORY_OBSERVED.value,
    }.get(role_value, DataOrigin.HISTORY_OBSERVED.value)

    out["schema_version"] = SCHEMA_VERSION
    out["dataset_role"] = role_value
    if "data_origin" not in out.columns:
        out["data_origin"] = origin
    else:
        out["data_origin"] = out["data_origin"].where(out["data_origin"].notna(), origin)
    out["availability_status"] = out.apply(
        lambda row: infer_availability_status(row.get("stock_status"), row.get("price")), axis=1
    )
    out["canonical_product_key"] = out.apply(lambda row: canonical_product_key(row), axis=1)
    return out
