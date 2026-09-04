from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen

from .base import ProviderToolCall, ProviderTurn


class OpenAICompatibleProvider:
    """Small provider adapter for OpenAI-compatible chat-completions endpoints.

    The repository does not hard-code a vendor or model. Operators provide the
    endpoint, model and bearer token through backend-only environment variables.
    """

    name = "openai_compatible"

    def __init__(self, *, endpoint: str, api_key: str, model: str, timeout_seconds: int = 45):
        self.endpoint = endpoint.strip()
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout_seconds = int(timeout_seconds)

    @property
    def available(self) -> bool:
        return bool(self.endpoint and self.api_key and self.model)

    def complete(self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ProviderTurn:
        if not self.available:
            raise RuntimeError("LLM provider is not fully configured")
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.1,
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Cloud-Phone-Pricing-Intelligence/2.0",
            },
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:  # nosec - operator configured HTTPS endpoint
            body = json.loads(response.read().decode("utf-8"))
        choices = body.get("choices") or []
        if not choices:
            raise RuntimeError("LLM provider returned no choices")
        message = choices[0].get("message") or {}
        calls: list[ProviderToolCall] = []
        for item in message.get("tool_calls") or []:
            fn = item.get("function") or {}
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except (json.JSONDecodeError, TypeError, ValueError):
                args = {}
            calls.append(
                ProviderToolCall(
                    call_id=str(item.get("id") or ""),
                    name=str(fn.get("name") or ""),
                    arguments=args,
                )
            )
        return ProviderTurn(
            text=str(message.get("content") or ""),
            tool_calls=calls,
            raw_message=message,
        )
