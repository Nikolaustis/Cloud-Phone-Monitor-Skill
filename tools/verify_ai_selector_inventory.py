from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _duration_rows(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(payload, list):
        rows.extend(item for item in payload if isinstance(item, dict))
    elif isinstance(payload, dict):
        buckets = payload.get("buckets")
        if isinstance(buckets, dict):
            for values in buckets.values():
                if isinstance(values, list):
                    rows.extend(item for item in values if isinstance(item, dict))
        other_rows = payload.get("other_rows")
        if isinstance(other_rows, list):
            rows.extend(item for item in other_rows if isinstance(item, dict))
    return [
        row
        for row in rows
        if row.get("ug_config_id") or str(row.get("platform") or "").strip().lower() == "ugphone"
    ]


def _selector_key(row: dict[str, Any]) -> tuple[str, float] | None:
    config_id = str(row.get("ug_config_id") or row.get("config_id") or row.get("canonical_product_key") or row.get("id") or "").strip()
    duration = _number(row.get("duration_days") or row.get("duration_bucket") or row.get("actual_duration_days"))
    if not config_id or duration is None or duration <= 0:
        return None
    return config_id, duration


def verify_selector_inventory(data_dir: Path) -> dict[str, Any]:
    data_dir = data_dir.resolve()
    source_path = data_dir / "duration_price_comparison.json"
    context_dir = data_dir / "ai"
    manifest_path = context_dir / "manifest.json"
    config_path = context_dir / "config_index.json"

    source = _read_json(source_path, {})
    manifest = _read_json(manifest_path, {})
    configs = _read_json(config_path, [])

    canonical_keys = {key for row in _duration_rows(source) if (key := _selector_key(row)) is not None}
    built_keys = {key for row in configs if isinstance(row, dict) and (key := _selector_key(row)) is not None}
    missing = sorted(canonical_keys - built_keys, key=lambda item: (item[0], item[1]))
    extras = sorted(built_keys - canonical_keys, key=lambda item: (item[0], item[1]))
    blank_duration_rows = [
        row for row in configs if isinstance(row, dict) and row.get("config_id") and _number(row.get("duration_days")) in (None, 0)
    ]

    result = {
        "ok": bool(source_path.is_file() and manifest_path.is_file() and config_path.is_file() and not missing and not blank_duration_rows),
        "schema_version": manifest.get("schema_version"),
        "data_revision": manifest.get("data_revision"),
        "canonical_selector_count": len(canonical_keys),
        "ai_selector_count": len(built_keys),
        "manifest_selector_inventory_count": manifest.get("selector_inventory_count"),
        "missing_count": len(missing),
        "extra_count": len(extras),
        "blank_duration_count": len(blank_duration_rows),
        "missing_preview": [f"{config_id}@{duration:g}d" for config_id, duration in missing[:20]],
        "extra_preview": [f"{config_id}@{duration:g}d" for config_id, duration in extras[:20]],
    }
    if manifest.get("schema_version") != "ai-context-v2":
        result["ok"] = False
        result["error"] = "AI context schema is not ai-context-v2"
    if manifest.get("selector_inventory_count") not in (None, len(canonical_keys)):
        result["ok"] = False
        result["error"] = "manifest selector_inventory_count does not match canonical duration inventory"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify that AI selector periods cover the canonical Dashboard duration inventory.")
    parser.add_argument("--data-dir", required=True)
    args = parser.parse_args()
    result = verify_selector_inventory(Path(args.data_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
