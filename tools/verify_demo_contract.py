from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_backend.config import Settings
from ai_backend.store import ContextStore
from ai_backend.tools import PricingTools
from cloud_phone_monitor.ai_context import AI_CONTEXT_SCHEMA_VERSION


def verify(context_dir: Path) -> dict[str, object]:
    context_dir = context_dir.resolve()
    manifest_path = context_dir / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"AI context manifest missing: {manifest_path}")

    os.environ["AI_CONTEXT_DIR"] = str(context_dir)
    os.environ["AI_ENABLE_LLM"] = "0"

    settings = Settings.from_env()
    store = ContextStore(settings)
    manifest = store.manifest
    if manifest.get("schema_version") != AI_CONTEXT_SCHEMA_VERSION:
        raise RuntimeError(f"Unexpected AI context schema: {manifest.get('schema_version')}")
    if manifest.get("safe_data_only") is not True:
        raise RuntimeError("AI context must assert safe_data_only=true")

    tools = PricingTools(store)
    registry = tools.registry()
    expected_tools = {
        "get_market_overview",
        "search_configs",
        "compare_configuration",
        "get_pairing_evidence",
        "get_price_changes",
        "get_price_history",
        "get_metric_definition",
        "simulate_price",
    }
    missing_tools = sorted(expected_tools - set(registry))
    if missing_tools:
        raise RuntimeError("AI tool registry is incomplete: " + ", ".join(missing_tools))

    overview = tools.get_market_overview()
    configs = store.configs
    if not configs:
        raise RuntimeError("Demo AI context contains no configurations")
    first = configs[0]
    config_id = str(first.get("config_id") or "")
    if not config_id:
        raise RuntimeError("Demo configuration is missing config_id")
    duration = first.get("duration_days")
    comparison = tools.compare_configuration(config_id, duration)
    if not comparison.get("result"):
        raise RuntimeError("compare_configuration returned no demo row")

    median = first.get("competitor_median_price")
    proposed = first.get("ugphone_price")
    if isinstance(median, (int, float)) and median > 0 and isinstance(proposed, (int, float)):
        what_if = tools.simulate_price(config_id, float(proposed) * 0.95, duration)
        if not what_if.get("result", {}).get("found"):
            raise RuntimeError("simulate_price did not find the demo configuration")

    app_module = importlib.import_module("ai_backend.app")
    health = app_module.health()
    if health.get("ok") is not True:
        raise RuntimeError(f"FastAPI health contract failed: {health}")
    if health.get("schema_version") != AI_CONTEXT_SCHEMA_VERSION:
        raise RuntimeError(f"FastAPI exposed unexpected schema: {health.get('schema_version')}")
    brief = app_module.market_brief()
    if not brief.get("answer") or brief.get("data_revision") != manifest.get("data_revision"):
        raise RuntimeError("FastAPI market brief is missing answer/revision grounding")
    tool_catalog = app_module.tool_catalog()
    if set(tool_catalog.get("tools", [])) != set(registry):
        raise RuntimeError("FastAPI tool catalog differs from deterministic tool registry")

    return {
        "ok": True,
        "schema_version": manifest.get("schema_version"),
        "safe_data_only": manifest.get("safe_data_only"),
        "data_date": manifest.get("data_date"),
        "data_revision": manifest.get("data_revision"),
        "config_count": len(configs),
        "tool_count": len(registry),
        "overview_evidence_count": len(overview.get("evidence", [])),
        "api_health": True,
        "api_brief_grounded": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the synthetic AI semantic context and FastAPI read-only contract.")
    parser.add_argument("--context-dir", required=True)
    args = parser.parse_args()
    result = verify(Path(args.context_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
