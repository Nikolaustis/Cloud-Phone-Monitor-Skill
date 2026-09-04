from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai_backend.config import Settings
from ai_backend.store import ContextStore
from ai_backend.tools import PricingTools, answer_question_local


def _contains_number(value, expected: float) -> bool:
    if isinstance(value, dict):
        return any(_contains_number(item, expected) for item in value.values())
    if isinstance(value, list):
        return any(_contains_number(item, expected) for item in value)
    if isinstance(value, (int, float)):
        return abs(float(value) - expected) < 1e-6
    return False


def _settings(context: Path) -> Settings:
    return Settings(
        context_dir=context,
        context_base_url="",
        provider="disabled",
        llm_endpoint="",
        llm_api_key="",
        llm_model="",
        llm_enabled=False,
        cors_origins=(),
        max_requests_per_minute=30,
        max_tool_rounds=4,
        request_timeout_seconds=45,
        service_launch_token="",
        host="127.0.0.1",
        port=8787,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate deterministic routing, numeric retrieval, grounding and abstention.")
    parser.add_argument("--context", default=str(ROOT / "demo" / "ai_context"))
    parser.add_argument("--questions", default=str(ROOT / "evals" / "benchmark_questions.json"))
    parser.add_argument("--output", default=str(ROOT / "evals" / "demo_report.json"))
    args = parser.parse_args()

    tools = PricingTools(ContextStore(_settings(Path(args.context))))
    cases = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        started = time.perf_counter()
        result = answer_question_local(tools, case["question"])
        latency_ms = (time.perf_counter() - started) * 1000
        intent_ok = result.get("intent") == case.get("expected_intent")
        evidence_ok = len(result.get("evidence", [])) >= int(case.get("min_evidence", 0))
        abstained = result.get("intent") == "abstain"
        abstention_ok = abstained == bool(case.get("should_abstain"))
        expected_number = case.get("expected_number")
        numeric_ok = True if expected_number is None else _contains_number(result.get("facts"), float(expected_number))
        rows.append({
            "id": case["id"], "intent_ok": intent_ok, "evidence_ok": evidence_ok,
            "abstention_ok": abstention_ok, "numeric_ok": numeric_ok,
            "latency_ms": round(latency_ms, 3), "intent": result.get("intent"),
            "evidence_count": len(result.get("evidence", [])), "tool_calls": result.get("tool_calls", []),
        })

    total = len(rows) or 1
    latencies = sorted(row["latency_ms"] for row in rows)
    def percentile(p: float) -> float:
        if not latencies:
            return 0.0
        index = min(len(latencies) - 1, max(0, round((len(latencies) - 1) * p)))
        return latencies[index]
    report = {
        "benchmark": "deterministic-evidence-demo-v2",
        "cases": len(rows),
        "intent_accuracy": sum(row["intent_ok"] for row in rows) / total,
        "evidence_coverage": sum(row["evidence_ok"] for row in rows) / total,
        "abstention_accuracy": sum(row["abstention_ok"] for row in rows) / total,
        "numeric_accuracy": sum(row["numeric_ok"] for row in rows) / total,
        "p50_latency_ms": percentile(0.50),
        "p95_latency_ms": percentile(0.95),
        "rows": rows,
        "note": "Synthetic deterministic tool-layer benchmark only. It is not a production LLM quality score.",
    }
    output = Path(args.output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(row["intent_ok"] and row["evidence_ok"] and row["abstention_ok"] and row["numeric_ok"] for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
