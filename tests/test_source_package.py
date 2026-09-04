from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _build_public_stage(tmp_path: Path) -> Path:
    builder = _load(ROOT / "tools" / "build_release_staging.py", "release_builder")
    source = tmp_path / "working-tree"
    shutil.copytree(
        ROOT,
        source,
        ignore=shutil.ignore_patterns(
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
            "*.pyc",
        ),
    )
    private_tool = source / "tools" / "patch_external_ugphone_preflight.py"
    private_tool.write_text("PRIVATE MAINTAINER SCRIPT\n", encoding="utf-8")
    contract = source / "deployment_contract.json"
    value = json.loads(contract.read_text(encoding="utf-8"))
    value["dashboard_site_remote"] = "https://" + "github.com/private-owner/private-repo.git"
    contract.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    stage = tmp_path / "public-stage"
    builder.build(source, stage)
    return stage


def test_public_release_is_built_from_explicit_allowlist(tmp_path: Path) -> None:
    validator = _load(ROOT / "tools" / "validate_source_package.py", "source_validator")
    stage = _build_public_stage(tmp_path)

    assert not (stage / "tools" / "patch_external_ugphone_preflight.py").exists()
    staged_contract = json.loads((stage / "deployment_contract.json").read_text(encoding="utf-8"))
    assert "dashboard_site_remote" not in staged_contract
    assert "private-owner/private-repo" not in (stage / "deployment_contract.json").read_text(encoding="utf-8")
    assert validator.validate(stage, require_exact_public_tree=True) == []


def test_staged_validator_does_not_create_python_bytecode(tmp_path: Path) -> None:
    stage = _build_public_stage(tmp_path)
    env = os.environ.copy()
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    result = subprocess.run(
        [
            sys.executable,
            str(stage / "tools" / "validate_source_package.py"),
            str(stage),
            "--exact-public-tree",
        ],
        cwd=stage,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not list(stage.rglob("__pycache__"))
    assert not list(stage.rglob("*.pyc"))
