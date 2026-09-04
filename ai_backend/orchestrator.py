from __future__ import annotations

import json
from typing import Any

from .config import Settings
from .providers import OpenAICompatibleProvider
from .tools import TOOL_DEFINITIONS, PricingTools, answer_question_local, attach_evidence_ids

SYSTEM_INSTRUCTIONS = """You are the Cloud Phone Pricing Intelligence Copilot.
Use deterministic pricing tools for factual and numeric claims. Do not calculate prices, medians, relative indexes, thresholds, or trend values yourself when a tool can provide them.
Never invent a configuration, price, date, source, market position or observation state.
Preserve data-origin caveats: carried-forward or missing observations must not be described as newly collected.
If evidence is insufficient, abstain explicitly.
Write for a pricing/product/business user, not for a database engineer. Do not expose internal enum or schema labels in the narrative. Translate states into natural business language, for example: high -> 明显高于市场, slightly_high -> 略高于市场, competitive -> 与市场基本持平, below_market -> 低于市场; carry_forward -> 沿用最近一次有效价格; strong_match -> 高可比配置; adjusted_match -> 近似可比配置.
Prefer short sections such as 市场概况、重点关注、数据提示、建议 when the question is broad. Explain the business meaning first; technical field names belong only in evidence/debug details.
Keep answers concise and evidence-grounded. Cite evidence IDs such as [E1] when available.
"""


class PricingCopilot:
    def __init__(self, settings: Settings, tools: PricingTools):
        self.settings = settings
        self.tools = tools
        self.provider = None
        if settings.provider == "openai_compatible":
            self.provider = OpenAICompatibleProvider(
                endpoint=settings.llm_endpoint,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                timeout_seconds=settings.request_timeout_seconds,
            )

    @property
    def available(self) -> bool:
        return bool(self.settings.llm_enabled and self.provider and self.provider.available)

    @property
    def mode(self) -> str:
        return "llm" if self.available else "evidence"

    def ask(self, question: str) -> dict[str, Any]:
        if not self.available:
            return answer_question_local(self.tools, question)

        messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
        evidence: list[dict[str, Any]] = []
        used_tools: list[str] = []
        for _ in range(self.settings.max_tool_rounds):
            turn = self.provider.complete(system=SYSTEM_INSTRUCTIONS, messages=messages, tools=TOOL_DEFINITIONS)
            calls = turn.tool_calls or []
            if not calls:
                return {
                    "answer": turn.text or "No answer generated.",
                    "intent": "tool_calling",
                    "confidence": "high" if evidence else "medium",
                    "evidence": attach_evidence_ids(evidence),
                    "tool_calls": used_tools,
                }
            messages.append(turn.raw_message or {"role": "assistant", "content": turn.text, "tool_calls": []})
            for call in calls:
                if not call.name:
                    continue
                result = self.tools.execute(call.name, call.arguments)
                used_tools.append(call.name)
                evidence.extend(result.get("evidence", []))
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.call_id,
                        "name": call.name,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )
        return {
            "answer": "The tool-calling safety limit was reached before a final answer was produced.",
            "intent": "tool_calling_limit",
            "confidence": "low",
            "evidence": attach_evidence_ids(evidence),
            "tool_calls": used_tools,
        }
