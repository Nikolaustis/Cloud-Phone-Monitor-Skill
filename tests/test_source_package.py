from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "validate_source_package.py"


def test_source_tree_is_clean_after_packaging_exclusions(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("source_validator", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    package_root = tmp_path / "source"
    shutil.copytree(
        ROOT,
        package_root,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"),
    )
    assert module.validate(package_root) == []
