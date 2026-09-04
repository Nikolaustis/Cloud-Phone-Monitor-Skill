from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_backend.config import Settings
from ai_backend.store import ContextStore, ContextUnavailable
from tools.public_release_policy import is_public_source_path


def _settings(context_dir: Path) -> Settings:
    return Settings(
        context_dir=context_dir,
        context_base_url="",
        provider="disabled",
        llm_endpoint="",
        llm_api_key="",
        llm_model="",
        llm_enabled=False,
        cors_origins=("http://127.0.0.1:5173",),
        max_requests_per_minute=30,
        max_tool_rounds=4,
        request_timeout_seconds=45,
        service_launch_token="",
        host="127.0.0.1",
        port=8787,
    )


def test_public_release_policy_includes_ai_sources_and_synthetic_demo() -> None:
    assert is_public_source_path("ai_backend/tools.py")
    assert is_public_source_path("dashboard/src/components/AICopilot.jsx")
    assert is_public_source_path("dashboard/.env.example")
    assert is_public_source_path("demo/dashboard_data/meta.json")
    assert is_public_source_path("demo/ai_context/manifest.json")
    assert is_public_source_path("evals/benchmark_questions.json")
    assert not is_public_source_path("dashboard/public/dashboard_data/private.json")
    assert not is_public_source_path("output/auth/ugphone_state.json")


def test_context_store_rejects_non_safe_manifest(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"schema_version": "ai-context-v2", "safe_data_only": False}),
        encoding="utf-8",
    )
    store = ContextStore(_settings(tmp_path))
    with pytest.raises(ContextUnavailable, match="safe_data_only"):
        _ = store.manifest


def test_context_store_rejects_unknown_schema(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"schema_version": "ai-context-v999", "safe_data_only": True}),
        encoding="utf-8",
    )
    store = ContextStore(_settings(tmp_path))
    with pytest.raises(ContextUnavailable, match="unsupported AI context schema"):
        _ = store.manifest


def test_default_context_path_is_skill_root_relative(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AI_CONTEXT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    settings = Settings.from_env()
    expected = Path(__file__).resolve().parents[2] / "dashboard" / "public" / "dashboard_data" / "ai"
    assert settings.context_dir == expected.resolve()
