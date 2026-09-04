from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from cloud_phone_monitor.ai_context import AI_CONTEXT_SCHEMA_VERSION

from .config import Settings


class ContextUnavailable(RuntimeError):
    pass


class ContextStore:
    FILES = (
        "manifest.json",
        "market_summary.json",
        "config_index.json",
        "price_events.json",
        "pairing_index.json",
        "trend_index.json",
        "metric_dictionary.json",
        "question_examples.json",
    )

    def __init__(self, settings: Settings):
        self.settings = settings
        self._cache: dict[str, Any] = {}

    def _load_local(self, name: str) -> Any:
        return json.loads((self.settings.context_dir / name).read_text(encoding="utf-8"))

    def _load_remote(self, name: str) -> Any:
        url = f"{self.settings.context_base_url}/{name}"
        request = Request(url, headers={"User-Agent": "Cloud-Phone-Pricing-Intelligence/2.0"})
        with urlopen(request, timeout=self.settings.request_timeout_seconds) as response:  # nosec - operator configured URL
            return json.loads(response.read().decode("utf-8"))

    def load(self, name: str, *, refresh: bool = False) -> Any:
        if name not in self.FILES:
            raise KeyError(name)
        if name != "manifest.json" and "manifest.json" not in self._cache:
            self.manifest
        if not refresh and name in self._cache:
            return self._cache[name]
        errors: list[str] = []
        local_path = self.settings.context_dir / name
        if local_path.is_file():
            try:
                value = self._load_local(name)
                self._cache[name] = value
                return value
            except Exception as exc:
                errors.append(f"local:{type(exc).__name__}:{exc}")
        if self.settings.context_base_url:
            try:
                value = self._load_remote(name)
                self._cache[name] = value
                return value
            except Exception as exc:
                errors.append(f"remote:{type(exc).__name__}:{exc}")
        if name in {"trend_index.json", "pairing_index.json"}:
            value: list[Any] = []
            self._cache[name] = value
            return value
        raise ContextUnavailable(f"AI context unavailable for {name}; {'; '.join(errors) or 'no local file or remote base URL'}")

    @property
    def manifest(self) -> dict[str, Any]:
        value = self.load("manifest.json")
        if not isinstance(value, dict):
            raise ContextUnavailable("AI context manifest must be a JSON object")
        if value.get("schema_version") != AI_CONTEXT_SCHEMA_VERSION:
            raise ContextUnavailable(f"unsupported AI context schema: {value.get('schema_version')}")
        if value.get("safe_data_only") is not True:
            raise ContextUnavailable("AI context manifest does not assert safe_data_only=true")
        return value

    @property
    def configs(self) -> list[dict[str, Any]]:
        value = self.load("config_index.json")
        return value if isinstance(value, list) else []

    @property
    def changes(self) -> list[dict[str, Any]]:
        value = self.load("price_events.json")
        return value if isinstance(value, list) else []

    @property
    def pairings(self) -> list[dict[str, Any]]:
        value = self.load("pairing_index.json")
        return value if isinstance(value, list) else []

    @property
    def trends(self) -> list[dict[str, Any]]:
        value = self.load("trend_index.json")
        return value if isinstance(value, list) else []

    @property
    def metrics(self) -> list[dict[str, Any]]:
        value = self.load("metric_dictionary.json")
        return value if isinstance(value, list) else []

    @property
    def market_summary(self) -> dict[str, Any]:
        value = self.load("market_summary.json")
        return value if isinstance(value, dict) else {}

    def refresh(self) -> None:
        self._cache.clear()
        self.load("manifest.json", refresh=True)
