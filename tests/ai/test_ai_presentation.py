from __future__ import annotations

from pathlib import Path

from ai_backend.config import Settings
from ai_backend.presentation import (
    render_configuration_explanation,
    render_market_brief,
    render_what_if,
)
from ai_backend.store import ContextStore
from ai_backend.tools import PricingTools, answer_question_local

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_USER_ENUMS = (
    "slightly_high",
    "below_market",
    "carry_forward",
    "current_observed",
    "strong_match",
    "adjusted_match",
    "weak_match",
    "manual_mapping",
    "missing_collection",
    "subscription_mode_unavailable",
)


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


def _assert_human_copy(text: str) -> None:
    assert text.strip()
    for token in FORBIDDEN_USER_ENUMS:
        assert token not in text


def test_market_brief_is_business_readable() -> None:
    tools = _tools()
    text = render_market_brief(tools.get_market_overview()["result"])
    _assert_human_copy(text)
    assert "市场概况" in text
    assert "重点关注" in text
    assert "数据提示" in text
    assert "建议" in text
    assert "明显偏高" in text


def test_explain_translates_market_and_pairing_states() -> None:
    tools = _tools()
    row = tools.compare_configuration("demo_kvip_30d", 30)["result"][0]
    pairings = tools.get_pairing_evidence("demo_kvip_30d", 30, 20)["result"]
    text = render_configuration_explanation(row, pairings)
    _assert_human_copy(text)
    assert "明显高于市场" in text
    assert "高可比配置" in text
    assert "近似可比配置" in text


def test_carry_forward_caveat_is_plain_language() -> None:
    result = answer_question_local(_tools(), "SVIP 30天价格怎么样？")
    _assert_human_copy(result["answer"])
    assert "最近一次有效采集价格" in result["answer"]


def test_local_market_and_explain_answers_do_not_leak_internal_enums() -> None:
    tools = _tools()
    for question in ("今天市场整体怎么样？", "为什么 KVIP 30天明显高于市场？", "KVIP 30天价格怎么样？"):
        result = answer_question_local(tools, question)
        _assert_human_copy(result["answer"])


def test_what_if_narrative_uses_business_labels() -> None:
    payload = _tools().simulate_price("demo_kvip_30d", 12.6, 30)["result"]
    text = render_what_if(payload)
    _assert_human_copy(text)
    assert "与市场基本持平" in text
    assert "市场位置将从" in text
