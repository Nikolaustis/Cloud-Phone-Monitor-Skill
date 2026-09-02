from __future__ import annotations

import argparse
import gzip
import json
from datetime import date
from pathlib import Path
from typing import Any

REQUIRED_JSON = (
    "frontend_price_overview.json",
    "pairing_matrix.json",
    "duration_price_comparison.json",
    "price_change_tracking.json",
    "product_text_changes.json",
    "metric_definitions.json",
    "schedule_status.json",
    "meta.json",
    "current_price_snapshot.json",
    "platform_status.json",
    "collection_contract.json",
    "run_manifest.json",
    "history_storage.json",
)
REQUIRED_PLATFORMS = {"UgPhone", "VSPhone", "Redfinger", "LDCloud"}
HARD_FAILURE_TOKENS = (
    "captcha",
    "anti_bot",
    "anti-bot",
    "unauthorized",
    "forbidden",
    "login_failed",
    "session_expired",
    "authentication_failed",
)


def load_json(path: Path) -> Any:
    if path.name.lower().endswith(".json.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def history_asset(data_dir: Path) -> Path:
    for name in ("price_trends.json.gz", "price_trends.json"):
        candidate = data_dir / name
        if candidate.exists():
            return candidate
    raise ValueError("missing compressed price_trends.json.gz and legacy price_trends.json fallback")


def platform_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("platforms", "items", "data", "results"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def hard_failure(row: dict[str, Any]) -> bool:
    # Inspect failure/status *values*, not JSON key names. A harmless key such
    # as ``blocked_reason: null`` must not be treated as an active block.
    fields = (
        "status",
        "collection_status",
        "reason",
        "failure_reason",
        "blocked_reason",
        "ugphone_failure_reason",
        "error",
    )
    text = " ".join(str(row.get(field) or "") for field in fields).lower()
    return any(token in text for token in HARD_FAILURE_TOKENS)


def validate(dist_dir: Path) -> dict[str, Any]:
    if not (dist_dir / "index.html").is_file():
        raise ValueError(f"index.html missing under {dist_dir}")
    assets_dir = dist_dir / "assets"
    if not assets_dir.is_dir() or not any(assets_dir.glob("*.js")):
        raise ValueError("built JS asset missing")

    data_dir = dist_dir / "dashboard_data"
    if not data_dir.is_dir():
        raise ValueError(f"dashboard_data directory missing: {data_dir}")
    for name in REQUIRED_JSON:
        if not (data_dir / name).is_file():
            raise ValueError(f"required Dashboard data file missing: {name}")

    storage = load_json(data_dir / "history_storage.json")
    if not isinstance(storage, dict):
        raise ValueError("history_storage.json must be an object")
    codec = str(storage.get("codec") or "")
    selected_history = history_asset(data_dir)
    if codec == "gzip-json-v1" and selected_history.name != "price_trends.json.gz":
        raise ValueError("history_storage declares gzip-json-v1 but price_trends.json.gz is absent")

    trends = load_json(selected_history)
    if not isinstance(trends, dict):
        raise ValueError("price_trends payload must be an object")
    history_end = str(trends.get("history_end_date") or "")
    if not history_end:
        raise ValueError("price_trends history_end_date missing")
    try:
        date.fromisoformat(history_end)
    except ValueError as exc:
        raise ValueError(f"invalid history_end_date: {history_end}") from exc

    detail_files = trends.get("trend_detail_files") or []
    if not isinstance(detail_files, list):
        raise ValueError("trend_detail_files must be a list")
    for rel in detail_files:
        path = data_dir / str(rel)
        if not path.is_file():
            raise ValueError(f"trend detail chunk missing: {rel}")
        payload = load_json(path)
        if not isinstance(payload, dict) or payload.get("type") != "price_trends_detail_chunk":
            raise ValueError(f"invalid trend detail chunk: {rel}")

    p_rows = platform_rows(load_json(data_dir / "platform_status.json"))
    names = {str(row.get("platform") or row.get("name") or "") for row in p_rows}
    missing_platforms = sorted(REQUIRED_PLATFORMS - names)
    if missing_platforms:
        raise ValueError(f"platform_status missing platforms: {missing_platforms}")
    for row in p_rows:
        name = str(row.get("platform") or row.get("name") or "")
        if name in REQUIRED_PLATFORMS:
            try:
                raw_records = int(float(row.get("raw_records") or 0))
            except Exception:
                raw_records = 0
            if raw_records <= 0:
                raise ValueError(f"{name} raw_records is zero")
            if hard_failure(row):
                raise ValueError(f"{name} contains authentication/block failure evidence")

    contract = load_json(data_dir / "collection_contract.json")
    manifest = load_json(data_dir / "run_manifest.json")
    if not isinstance(contract, dict) or not isinstance(manifest, dict):
        raise ValueError("collection_contract/run_manifest must be JSON objects")

    # Partial coverage is publishable by design because the history layer carries forward the
    # last real observation. We report it as a warning rather than blocking.
    warnings: list[str] = []
    status = str(contract.get("status") or "").lower()
    if status and status not in {"ok", "success", "complete"}:
        warnings.append(f"collection_contract status={status}")

    return {
        "history_asset": selected_history.name,
        "history_codec": codec or "legacy-json",
        "history_end_date": history_end,
        "detail_chunk_count": len(detail_files),
        "platforms": sorted(names & REQUIRED_PLATFORMS),
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a built Cloud Phone Dashboard before GitHub Pages publication.")
    parser.add_argument("--dist-dir", required=True)
    args = parser.parse_args()
    try:
        result = validate(Path(args.dist_dir))
    except Exception as exc:
        print(f"Dashboard validation failed: {exc}")
        return 2
    print("Dashboard validation passed.")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
