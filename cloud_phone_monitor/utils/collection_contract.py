"""Collection completeness contract and run manifest for v29."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from cloud_phone_monitor.data_contracts import SCHEMA_VERSION, SKILL_RELEASE

PLATFORMS = ("UgPhone", "VSPhone", "Redfinger", "LDCloud")


def _platform(value: Any) -> str:
    text = str(value or "").strip()
    return "UgPhone" if text.lower() == "ugphone" else text


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _artifact_summaries(output_dir: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    artifacts = output_dir / "page_artifacts"
    if not artifacts.exists():
        return result
    for path in artifacts.glob("*_collection_summary.json"):
        payload = _read_json(path)
        platform = _platform(payload.get("platform") or path.stem.replace("_collection_summary", ""))
        if platform.upper() == "UGPHONE":
            platform = "UgPhone"
        if platform.lower() == "vsphone":
            platform = "VSPhone"
        if platform.lower() == "redfinger":
            platform = "Redfinger"
        if platform.lower() == "ldcloud":
            platform = "LDCloud"
        result[platform] = payload
    return result


def _ratio(success: Any, target: Any) -> float | None:
    try:
        t = int(target or 0)
        s = int(success or 0)
    except Exception:
        return None
    if t <= 0:
        return None
    return max(0.0, min(1.0, s / t))


def _summary_components(summary: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        ("plans", "dom_matrix_plan_successes", "dom_matrix_plan_targets"),
        ("variants", "dom_matrix_variant_successes", "dom_matrix_variant_targets"),
        ("regions", "dom_matrix_region_resolved", "dom_matrix_region_targets"),
        ("purchase_modes", "purchase_mode_successes", "purchase_mode_targets"),
        ("purchase_mode_pairs", "purchase_mode_pair_successes", "purchase_mode_pair_targets"),
        ("quantity_one", "quantity_one_successes", "quantity_one_targets"),
        ("purchase_mode_context", "purchase_mode_context_successes", "purchase_mode_context_targets"),
        ("auto_renew_confirmation", "auto_renew_confirmation_successes", "auto_renew_confirmation_targets"),
    ]
    components: list[dict[str, Any]] = []
    has_pair_contract = int(summary.get("purchase_mode_pair_targets") or 0) > 0
    for name, success_key, target_key in candidates:
        # UgPhone's raw purchase_mode_targets counts intermediate toggle probes.
        # When a completed pair contract exists, pair coverage is the business
        # invariant and the intermediate probe ratio must not depress coverage.
        if name == "purchase_modes" and has_pair_contract:
            continue
        ratio = _ratio(summary.get(success_key), summary.get(target_key))
        if ratio is None:
            continue
        components.append({
            "name": name,
            "successes": int(summary.get(success_key) or 0),
            "targets": int(summary.get(target_key) or 0),
            "coverage_ratio": round(ratio, 4),
        })
    return components



def _platform_slice(frame: pd.DataFrame, platform: str) -> pd.DataFrame:
    if frame is None or frame.empty or "platform" not in frame.columns:
        return pd.DataFrame()
    mask = frame["platform"].map(_platform).eq(platform)
    return frame.loc[mask].copy()

def build_collection_contract(
    output_dir: Path,
    current_df: pd.DataFrame,
    baseline_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    current_df = current_df if current_df is not None else pd.DataFrame()
    baseline_df = baseline_df if baseline_df is not None else pd.DataFrame()
    summaries = _artifact_summaries(output_dir)
    rows: list[dict[str, Any]] = []
    for platform in PLATFORMS:
        current = _platform_slice(current_df, platform)
        baseline = _platform_slice(baseline_df, platform)
        summary = summaries.get(platform, {})
        components = _summary_components(summary)
        ratios = [float(item["coverage_ratio"]) for item in components]
        coverage = min(ratios) if ratios else (1.0 if len(current) else 0.0)
        if len(current) == 0:
            status = "failed"
        elif coverage < 1.0:
            status = "warning"
        else:
            status = "ok"
        priced = 0
        if not current.empty and "price" in current.columns:
            priced = int(pd.to_numeric(current["price"], errors="coerce").notna().sum())
        missing = summary.get("dom_matrix_skipped") or summary.get("purchase_mode_failures") or []
        rows.append({
            "platform": platform,
            "status": status,
            "coverage_ratio": round(coverage, 4),
            "current_rows": int(len(current)),
            "priced_rows": priced,
            "baseline_reference_rows": int(len(baseline)),
            "baseline_row_delta": int(len(current) - len(baseline)) if len(baseline) else None,
            "contract_components": components,
            "missing_cells": missing[:200] if isinstance(missing, list) else [],
            "collector_status": summary.get("collection_status"),
            "collector_coverage_status": summary.get("coverage_status"),
            "collector_coverage_note": summary.get("coverage_note"),
        })
    overall = min((float(row["coverage_ratio"]) for row in rows), default=0.0)
    return {
        "schema_version": SCHEMA_VERSION,
        "skill_release": SKILL_RELEASE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "overall_coverage_ratio": round(overall, 4),
        "overall_status": "ok" if rows and all(row["status"] == "ok" for row in rows) else "warning",
        "platforms": rows,
        "contract_rule": "current observations determine collection health; baseline counts are reference-only and never satisfy current coverage",
    }


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL, timeout=2).strip()
    except Exception:
        return None


def build_run_manifest(output_dir: Path, run_summary: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "skill_release": SKILL_RELEASE,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_id": output_dir.name,
        "source_output_dir": str(output_dir),
        "git_commit": _git_commit(),
        "start_time_utc": run_summary.get("start_time_utc"),
        "end_time_utc": run_summary.get("end_time_utc"),
        "records_by_platform": run_summary.get("records_by_platform", {}),
        "collection_contract": {
            "overall_status": contract.get("overall_status"),
            "overall_coverage_ratio": contract.get("overall_coverage_ratio"),
        },
        "data_roles": {
            "current": "products.csv/products.xlsx from this run only",
            "historical": "prior real product observations plus explicit carry-forward",
            "baseline": "reference/comparison only; prohibited from becoming a current observation",
        },
        "availability_states": [
            "available", "missing_collection", "unavailable", "discontinued", "not_applicable", "unknown"
        ],
    }
