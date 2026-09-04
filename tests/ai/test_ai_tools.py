from __future__ import annotations

from pathlib import Path

from ai_backend.config import Settings
from ai_backend.store import ContextStore
from ai_backend.tools import PricingTools, answer_question_local

ROOT = Path(__file__).resolve().parents[2]


def _settings() -> Settings:
    return Settings(
        context_dir=ROOT / "demo" / "ai_context",
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


def _tools() -> PricingTools:
    return PricingTools(ContextStore(_settings()))


def test_what_if_uses_deterministic_market_thresholds() -> None:
    payload = _tools().simulate_price("demo_kvip_30d", 12.6, 30)
    result = payload["result"]
    assert result["found"] is True
    assert round(result["new_relative_index"], 2) == 105.0
    assert result["new_market_position"] == "competitive"
    assert round(result["price_change_from_current_pct"], 2) == -0.16
    assert payload["evidence"]


def test_local_answer_abstains_for_missing_configuration() -> None:
    result = answer_question_local(_tools(), "XVIP 999天多少钱？")
    assert result["intent"] == "abstain"
    assert result["evidence"] == []


def test_explain_uses_pairing_evidence() -> None:
    result = answer_question_local(_tools(), "为什么 KVIP 30天被判定为 high？")
    assert result["intent"] == "explain_configuration"
    assert len(result["evidence"]) >= 3
    assert "get_pairing_evidence" in result["tool_calls"]


def test_history_tool_returns_demo_points() -> None:
    payload = _tools().get_price_history("demo_kvip_30d", 30, 30)
    assert payload["result"]
    assert payload["result"][0]["points"][-1]["price"] == 15.0
