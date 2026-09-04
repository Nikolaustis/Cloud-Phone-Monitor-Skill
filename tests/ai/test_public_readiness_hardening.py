from __future__ import annotations

import os
import subprocess
import tempfile
import json
from pathlib import Path

import pytest

from ai_backend.config import Settings
from tools.prepare_demo_runtime import validate_output_root
from tools.validate_git_tracked_files import validate_tracked_tree

ROOT = Path(__file__).resolve().parents[2]


def test_demo_output_guard_rejects_source_and_sensitive_subtrees(tmp_path: Path) -> None:
    for unsafe in (ROOT, ROOT.parent, ROOT / "dashboard", ROOT / "output", ROOT / "output" / "auth"):
        with pytest.raises(RuntimeError):
            validate_output_root(ROOT, unsafe)

    # The OS temp root itself is never a legal deletion target.
    with pytest.raises(RuntimeError):
        validate_output_root(ROOT, Path(tempfile.gettempdir()))

    # A fresh dedicated temp child is valid, but a pre-existing unowned temp
    # directory is rejected to avoid deleting another process's files.
    fresh = tmp_path / "fresh-demo"
    assert validate_output_root(ROOT, fresh) == fresh.resolve()
    unowned = tmp_path / "existing-unowned"
    unowned.mkdir()
    (unowned / "foreign.tmp").write_text("foreign", encoding="utf-8")
    with pytest.raises(RuntimeError):
        validate_output_root(ROOT, unowned)

    owned = tmp_path / "owned-demo"
    owned.mkdir()
    (owned / "demo_runtime_manifest.json").write_text(
        json.dumps({"schema_version": "demo-runtime-v1", "safe_data_only": True, "source_root": str(ROOT.resolve())}),
        encoding="utf-8",
    )
    assert validate_output_root(ROOT, owned) == owned.resolve()

    # Only explicit local demo sandboxes are writable inside the source tree.
    assert validate_output_root(ROOT, ROOT / "output" / "demo_runtime") == (ROOT / "output" / "demo_runtime").resolve()


def _git(repo: Path, *args: str) -> None:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_tracked_validator_rejects_forbidden_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "README.md").write_text("public\n", encoding="utf-8")
    private = repo / "output" / "auth"
    private.mkdir(parents=True)
    (private / "token.json").write_text('{"token":"not-a-real-secret"}\n', encoding="utf-8")
    _git(repo, "add", "-A")
    problems = validate_tracked_tree(repo)
    assert any("outside explicit public allowlist" in item for item in problems)
    assert any("tracked forbidden" in item or "credential/runtime state" in item for item in problems)


def test_tracked_validator_rejects_secret_content(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    readme = repo / "README.md"
    readme.write_text("token = " + "sk-" + "abcdefghijklmnopqrstuvwxyz123456" + "\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    # Change the worktree after staging; the validator must still inspect the
    # indexed bytes that would actually be committed.
    readme.write_text("safe worktree content\n", encoding="utf-8")
    problems = validate_tracked_tree(repo)
    assert any("OpenAI-style secret" in item for item in problems)


def test_ai_env_file_is_loaded_without_overriding_process_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / "ai.env"
    env_file.write_text(
        "AI_ENABLE_LLM=1\n"
        "AI_LLM_PROVIDER=file-provider\n"
        "AI_LLM_MODEL=file-model\n"
        "AI_RATE_LIMIT_PER_MINUTE=17\n"
        "AI_PORT=19090\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_ENV_FILE", str(env_file))
    monkeypatch.setenv("AI_LLM_PROVIDER", "process-provider")
    for name in ("AI_ENABLE_LLM", "AI_LLM_MODEL", "AI_RATE_LIMIT_PER_MINUTE"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()
    assert settings.llm_enabled is True
    assert settings.provider == "process-provider"
    assert settings.llm_model == "file-model"
    assert settings.max_requests_per_minute == 17
    assert settings.port == 19090


def test_service_health_and_launch_scripts_bind_identity_and_revision() -> None:
    app = (ROOT / "ai_backend" / "app.py").read_text(encoding="utf-8")
    verify = (ROOT / "VERIFY_V2.ps1").read_text(encoding="utf-8")
    demo = (ROOT / "START_DEMO.ps1").read_text(encoding="utf-8")
    for marker in ("service_pid", "service_launch_token", "data_revision", "service_instance_id"):
        assert marker in app
    for script in (verify, demo):
        assert "AI_SERVICE_LAUNCH_TOKEN" in script
        assert "service_pid" in script
        assert "data_revision" in script
        assert "Assert-TcpPortAvailable" in script
        assert "-m\", \"uvicorn" in script


def test_runtime_policy_keeps_recommended_baseline_but_supports_newer_lts_versions() -> None:
    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.12"
    assert (ROOT / ".nvmrc").read_text(encoding="utf-8").strip() == "22"
    policy = json.loads((ROOT / "runtime-versions.json").read_text(encoding="utf-8"))
    assert policy["recommended_runtime"]["python"] == "3.12.x"
    assert policy["recommended_runtime"]["node"] == "22.x"
    assert policy["supported_runtime"]["python"] == ["3.12.x", "3.13.x", "3.14.x"]
    assert policy["supported_runtime"]["node"] == ["22.x", "24.x"]

    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "pandas==2.3.3" in requirements
    assert "openpyxl==" in requirements
    assert "pydantic==" in requirements
    assert "python-dateutil==" in requirements

    package = json.loads((ROOT / "dashboard" / "package.json").read_text(encoding="utf-8"))
    assert package["engines"]["node"] == "22.x || 24.x"
    installer = (ROOT / "install_dependencies_windows.ps1").read_text(encoding="utf-8")
    verify = (ROOT / "VERIFY_V2.ps1").read_text(encoding="utf-8")
    assert "3.14" in installer and "3.13" in installer and "3.12" in installer
    assert "v(22|24)" in installer
    assert "v(22|24)" in verify
