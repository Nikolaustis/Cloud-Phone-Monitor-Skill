from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _file_values(root: Path) -> dict[str, str]:
    explicit = os.getenv("AI_ENV_FILE", "").strip()
    path = Path(explicit).expanduser() if explicit else (root / "ai.env")
    if not path.is_absolute():
        path = root / path
    return _parse_env_file(path.resolve())


def _get(name: str, file_values: dict[str, str], default: str = "") -> str:
    # Process environment always wins. ai.env is a local convenience layer and
    # is intentionally ignored by Git/public release policy.
    if name in os.environ:
        return os.environ[name]
    return file_values.get(name, default)


@dataclass(frozen=True, slots=True)
class Settings:
    context_dir: Path
    context_base_url: str
    provider: str
    llm_endpoint: str
    llm_api_key: str
    llm_model: str
    llm_enabled: bool
    cors_origins: tuple[str, ...]
    max_requests_per_minute: int
    max_tool_rounds: int
    request_timeout_seconds: int
    service_launch_token: str
    host: str
    port: int
    auto_build_context: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(__file__).resolve().parents[1]
        file_values = _file_values(root)
        raw_context_dir = Path(_get("AI_CONTEXT_DIR", file_values, "dashboard/public/dashboard_data/ai"))
        context_dir = raw_context_dir if raw_context_dir.is_absolute() else (root / raw_context_dir)
        context_dir = context_dir.resolve()
        cors = tuple(
            item.strip()
            for item in _get(
                "AI_CORS_ORIGINS",
                file_values,
                "http://127.0.0.1:5173,http://localhost:5173",
            ).split(",")
            if item.strip()
        )
        return cls(
            context_dir=context_dir,
            context_base_url=_get("AI_CONTEXT_BASE_URL", file_values).rstrip("/"),
            provider=_get("AI_LLM_PROVIDER", file_values, "disabled").strip().lower(),
            llm_endpoint=_get("AI_LLM_ENDPOINT", file_values).strip(),
            llm_api_key=_get("AI_LLM_API_KEY", file_values).strip(),
            llm_model=_get("AI_LLM_MODEL", file_values).strip(),
            llm_enabled=_truthy(_get("AI_ENABLE_LLM", file_values, "0"), default=False),
            cors_origins=cors,
            max_requests_per_minute=max(1, int(_get("AI_RATE_LIMIT_PER_MINUTE", file_values, "30"))),
            max_tool_rounds=max(1, min(8, int(_get("AI_MAX_TOOL_ROUNDS", file_values, "4")))),
            request_timeout_seconds=max(5, min(120, int(_get("AI_REQUEST_TIMEOUT_SECONDS", file_values, "45")))),
            service_launch_token=_get("AI_SERVICE_LAUNCH_TOKEN", file_values).strip(),
            auto_build_context=_truthy(_get("AI_AUTO_BUILD_CONTEXT", file_values, "1"), default=True),
            host=_get("AI_HOST", file_values, "127.0.0.1").strip() or "127.0.0.1",
            port=max(1, min(65535, int(_get("AI_PORT", file_values, "8787")))),
        )
