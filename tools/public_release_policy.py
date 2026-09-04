from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

PUBLIC_ROOT_FILES = {
    ".gitattributes",
    ".gitignore",
    ".nvmrc",
    ".python-version",
    "CONTRIBUTING.md",
    "DEPLOYMENT_DATA_GUIDE.md",
    "INSTALL.ps1",
    "INSTALL_GUIDE.md",
    "LICENSE",
    "LOGIN.ps1",
    "MIGRATION_GUIDE.md",
    "PREPARE_RELEASE.ps1",
    "README.md",
    "AI_GUIDE.md",
    "PROJECT_PORTFOLIO.md",
    "RUN_TESTS.ps1",
    "RUN_AI_TESTS.ps1",
    "START_DEMO.ps1",
    "VERIFY_V2.ps1",
    "VERIFY_REAL_COLLECTORS.ps1",
    "PUBLISH_PUBLIC_SOURCE.ps1",
    "SECURITY.md",
    "SKILL.md",
    "VALIDATION.md",
    "config.example.json",
    "constraints-runtime.txt",
    "deployment_contract.json",
    "ai.env.example",
    "install_dependencies_windows.ps1",
    "install_ai_dependencies_windows.ps1",
    "publisher.local.example.json",
    "rebuild_dashboard_history.py",
    "build_ai_context.py",
    "run_ai_api.py",
    "requirements-ai.txt",
    "requirements-dev.txt",
    "requirements.txt",
    "runtime-versions.json",
    "run.py",
    "run_windows.bat",
}

PUBLIC_TOOL_FILES = {
    "tools/build_release_staging.py",
    "tools/build_release_zip.py",
    "tools/generate_manifest.py",
    "tools/public_release_policy.py",
    "tools/prepare_demo_runtime.py",
    "tools/verify_demo_contract.py",
    "tools/verify_ai_selector_inventory.py",
    "tools/validate_git_tracked_files.py",
    "tools/validate_manifest.py",
    "tools/validate_public_release.py",
    "tools/validate_source_package.py",
}

PUBLIC_DEPLOYMENT_FILES = {
    "deployment/windows/check_skill_login_state.py",
    "deployment/windows/install_deployment.ps1",
    "deployment/windows/publish_dashboard.ps1",
    "deployment/windows/resume_dashboard_publish.ps1",
    "deployment/windows/update_cloud_phone_dashboard.ps1",
    "deployment/windows/validate_cloud_phone_dashboard.py",
    "deployment/windows/verify_deployment.ps1",
}

PUBLIC_SCRIPT_FILES = {
    "scripts/setup_daily_monitor_cron.sh",
    "scripts/setup_daily_monitor_windows.ps1",
}

PUBLIC_GITHUB_FILES = {
    ".github/workflows/ci.yml",
}

PUBLIC_DOC_FILES = {
    "docs/ARCHITECTURE.md",
    "docs/AUTHENTICATION_DESIGN.md",
    "docs/RELEASE_PROCESS.md",
    "docs/AI_ARCHITECTURE.md",
    "docs/AI_DEPLOYMENT.md",
    "docs/AI_EVALUATION.md",
    "docs/V2_RELEASE.md",
}

FORBIDDEN_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "output",
    "baselines",
    "logs",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    "dashboard_data",
    ".release_staging",
    "release_staging",
}
FORBIDDEN_FILE_NAMES = {
    "publisher.local.json",
    "PUBLISH_SOURCE_TO_GITHUB.ps1",
    "install_windows.ps1",
    "patch_external_ugphone_preflight.py",
    "ai.env",
}
FORBIDDEN_SUFFIXES = {".pyc", ".log", ".xlsx", ".xls", ".csv", ".jsonl", ".zip", ".7z", ".rar", ".exe", ".dll"}
SENSITIVE_NAME_RE = re.compile(
    r"(?:cookie|token|credential|secret|password|passwd|storage[_-]?state|login[_-]?status|login[_-]?agent[_-]?session|runtime[_-]?context)",
    re.I,
)
CONCRETE_GITHUB_REMOTE = re.compile(
    r"https://github\.com/(?!YOUR_ACCOUNT/)[^/\s\"']+/[^/\s\"']+\.git",
    re.I,
)

PUBLIC_DEPLOYMENT_CONTRACT_KEYS = (
    "schema_version",
    "history_storage",
    "publisher_capability",
)


def _parts(rel: str | PurePosixPath) -> tuple[str, ...]:
    p = PurePosixPath(str(rel).replace("\\", "/"))
    return tuple(p.parts)


def _is_cloud_phone_source(parts: tuple[str, ...]) -> bool:
    return len(parts) >= 2 and parts[0] == "cloud_phone_monitor" and parts[-1].endswith(".py")


def _is_dashboard_source(parts: tuple[str, ...]) -> bool:
    if not parts or parts[0] != "dashboard":
        return False
    rel = "/".join(parts)
    if rel in {
        "dashboard/index.html",
        "dashboard/package.json",
        "dashboard/package-lock.json",
        "dashboard/postcss.config.js",
        "dashboard/tailwind.config.js",
        "dashboard/vite.config.js",
        "dashboard/.env.example",
    }:
        return True
    if len(parts) >= 3 and parts[1] == "src":
        return parts[-1].endswith((".js", ".jsx", ".css", ".json"))
    return False


def _is_ai_backend_source(parts: tuple[str, ...]) -> bool:
    return len(parts) >= 2 and parts[0] == "ai_backend" and parts[-1].endswith(".py")


def _is_eval_source(parts: tuple[str, ...]) -> bool:
    if not parts or parts[0] != "evals":
        return False
    rel = "/".join(parts)
    return rel in {
        "evals/README.md",
        "evals/benchmark_questions.json",
        "evals/demo_report.json",
        "evals/run_eval.py",
    }


def _is_demo_source(parts: tuple[str, ...]) -> bool:
    if len(parts) < 3 or parts[0] != "demo":
        return False
    if parts[1] == "dashboard_data":
        return parts[-1].endswith(".json")
    if parts[1] == "ai_context":
        return parts[-1].endswith(".json") or parts[-1] == "market_brief.txt"
    return False


def _is_test_source(parts: tuple[str, ...]) -> bool:
    if not parts or parts[0] != "tests":
        return False
    name = parts[-1]
    if name.endswith((".py", ".ps1")):
        return True
    if "fixtures" in parts and name.endswith(".json"):
        return True
    return False


def is_public_source_path(rel: str | PurePosixPath) -> bool:
    parts = _parts(rel)
    if not parts:
        return False
    demo_dashboard_data = len(parts) >= 2 and parts[0] == "demo" and parts[1] == "dashboard_data"
    if any(part in FORBIDDEN_DIR_NAMES for part in parts[:-1]) and not demo_dashboard_data:
        return False
    name = parts[-1]
    if name in FORBIDDEN_FILE_NAMES or Path(name).suffix.lower() in FORBIDDEN_SUFFIXES:
        return False
    rel_text = "/".join(parts)
    if len(parts) == 1:
        return name in PUBLIC_ROOT_FILES
    if rel_text in PUBLIC_TOOL_FILES | PUBLIC_DEPLOYMENT_FILES | PUBLIC_SCRIPT_FILES | PUBLIC_GITHUB_FILES | PUBLIC_DOC_FILES:
        return True
    return (
        _is_cloud_phone_source(parts)
        or _is_ai_backend_source(parts)
        or _is_dashboard_source(parts)
        or _is_eval_source(parts)
        or _is_demo_source(parts)
        or _is_test_source(parts)
    )


def required_public_paths() -> set[str]:
    required = set(PUBLIC_ROOT_FILES)
    required.update(PUBLIC_TOOL_FILES)
    required.update(PUBLIC_DEPLOYMENT_FILES)
    required.update(PUBLIC_SCRIPT_FILES)
    required.update(PUBLIC_GITHUB_FILES)
    required.update(PUBLIC_DOC_FILES)
    required.update(
        {
            "cloud_phone_monitor/main.py",
            "cloud_phone_monitor/login_wait_for_signal.py",
            "cloud_phone_monitor/login_controller.py",
            "cloud_phone_monitor/login_helper_session_entry.py",
            "cloud_phone_monitor/auth_session_contract.py",
            "cloud_phone_monitor/auth_file_transaction.py",
            "cloud_phone_monitor/profile_lock.py",
            "cloud_phone_monitor/ai_context.py",
            "ai_backend/__init__.py",
            "ai_backend/app.py",
            "ai_backend/config.py",
            "ai_backend/orchestrator.py",
            "ai_backend/presentation.py",
            "ai_backend/schemas.py",
            "ai_backend/store.py",
            "ai_backend/tools.py",
            "ai_backend/providers/__init__.py",
            "ai_backend/providers/base.py",
            "ai_backend/providers/openai_compatible.py",
            "dashboard/src/components/AICopilot.jsx",
            "dashboard/src/lib/aiClient.js",
            "dashboard/src/lib/aiPresentation.js",
            "dashboard/src/main.jsx",
            "tests/ai/test_ai_context.py",
            "tests/ai/test_ai_tools.py",
            "tests/ai/test_ai_frontend_contract.py",
            "tests/ai/test_ai_presentation.py",
            "tests/ai/test_ai_release_contract.py",
            "tests/ai/test_v2_readiness_contract.py",
            "evals/benchmark_questions.json",
            "evals/run_eval.py",
            "tools/prepare_demo_runtime.py",
            "tools/verify_demo_contract.py",
    "tools/verify_ai_selector_inventory.py",
            "tools/validate_git_tracked_files.py",
            "LICENSE",
            "MIGRATION_GUIDE.md",
            "runtime-versions.json",
            ".python-version",
            ".nvmrc",
            "START_DEMO.ps1",
            "VERIFY_V2.ps1",
            "VERIFY_REAL_COLLECTORS.ps1",
            "PUBLISH_PUBLIC_SOURCE.ps1",
            "publisher.local.example.json",
            "demo/dashboard_data/meta.json",
            "demo/dashboard_data/duration_price_comparison.json",
            "demo/dashboard_data/product_text_changes.json",
            "demo/dashboard_data/schedule_status.json",
            "demo/ai_context/manifest.json",
            "tests/auth_state_machine/test_auth_session_contract.py",
            "tests/auth_state_machine/test_login_source_contract.py",
            "tests/auth_state_machine/test_manifest_contract.py",
            "tests/auth_state_machine/test_profile_lock.py",
            "tests/auth_state_machine/windows_login_smoke.ps1",
        }
    )
    return required


def sanitize_deployment_contract(value: Any) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(value, dict):
        raise RuntimeError("deployment_contract.json must contain a JSON object")
    missing = [key for key in PUBLIC_DEPLOYMENT_CONTRACT_KEYS if key not in value]
    if missing:
        raise RuntimeError("deployment_contract.json missing required public keys: " + ", ".join(missing))
    sanitized = {key: value[key] for key in PUBLIC_DEPLOYMENT_CONTRACT_KEYS}
    removed = sorted(str(key) for key in value if key not in PUBLIC_DEPLOYMENT_CONTRACT_KEYS)
    return sanitized, removed


def load_and_sanitize_deployment_contract(path: Path) -> tuple[dict[str, Any], list[str]]:
    return sanitize_deployment_contract(json.loads(path.read_text(encoding="utf-8")))


def write_sanitized_deployment_contract(source: Path, destination: Path) -> list[str]:
    sanitized, removed = load_and_sanitize_deployment_contract(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return removed
