from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class ProviderToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ProviderTurn:
    text: str = ""
    tool_calls: list[ProviderToolCall] | None = None
    raw_message: dict[str, Any] | None = None


class LLMProvider(Protocol):
    name: str

    @property
    def available(self) -> bool: ...

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderTurn: ...
