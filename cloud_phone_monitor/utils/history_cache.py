"""Small local cache primitives used by the v29 incremental history rebuild."""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

from cloud_phone_monitor.data_contracts import SCHEMA_VERSION

CACHE_FORMAT_VERSION = 1


def history_cache_root(current_output_dir: Path) -> Path:
    return current_output_dir.parent / ".history_cache" / f"schema_{SCHEMA_VERSION}"


def source_fingerprint(run_dir: Path) -> str:
    source = run_dir / "products.csv"
    if not source.exists():
        source = run_dir / "products.xlsx"
    if not source.exists():
        source = run_dir / "dashboard_data" / "price_trends.json"
    if not source.exists():
        source = run_dir / "dashboard_data" / "price_trends.json.gz"
    try:
        stat = source.stat()
        return f"{run_dir.name}|{source.name}|{stat.st_size}|{stat.st_mtime_ns}"
    except OSError:
        return f"{run_dir.name}|missing"


def load_daily_cache(path: Path, fingerprint: str) -> dict[str, Any] | None:
    try:
        payload = pickle.loads(path.read_bytes())
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("cache_format_version") != CACHE_FORMAT_VERSION:
        return None
    if payload.get("schema_version") != SCHEMA_VERSION:
        return None
    if payload.get("source_fingerprint") != fingerprint:
        return None
    return payload.get("data") if isinstance(payload.get("data"), dict) else None


def save_daily_cache(path: Path, fingerprint: str, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cache_format_version": CACHE_FORMAT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "source_fingerprint": fingerprint,
        "data": data,
    }
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
    temp.replace(path)
