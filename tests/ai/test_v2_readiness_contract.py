from __future__ import annotations

import json
from pathlib import Path

from tools.prepare_demo_runtime import REQUIRED_DASHBOARD_ASSETS, prepare_demo_runtime
from tools.public_release_policy import is_public_source_path, required_public_paths

ROOT = Path(__file__).resolve().parents[2]


def test_demo_dataset_covers_static_dashboard_loader_contract() -> None:
    demo = ROOT / "demo" / "dashboard_data"
    assert REQUIRED_DASHBOARD_ASSETS <= {path.name for path in demo.glob("*.json")}
    meta = json.loads((demo / "meta.json").read_text(encoding="utf-8"))
    assert meta["safe_data_only"] is True
    assert meta["is_demo_data"] is True


def test_prepare_demo_runtime_is_isolated_and_builds_ai_context(tmp_path: Path) -> None:
    output = tmp_path / "demo-runtime"
    result = prepare_demo_runtime(ROOT, output)
    assert result["safe_data_only"] is True
    assert result["is_demo_data"] is True
    assert (output / "dashboard/public/dashboard_data/ai/manifest.json").is_file()
    assert not (output / "dashboard/node_modules").exists()
    manifest = json.loads((output / "dashboard/public/dashboard_data/ai/manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "ai-context-v2"
    assert manifest["safe_data_only"] is True


def test_release_policy_includes_v2_readiness_entrypoints() -> None:
    required = required_public_paths()
    for path in (
        "START_DEMO.ps1",
        "VERIFY_V2.ps1",
        "PUBLISH_PUBLIC_SOURCE.ps1",
        "publisher.local.example.json",
        "VERIFY_REAL_COLLECTORS.ps1",
        "LICENSE",
        "MIGRATION_GUIDE.md",
        "runtime-versions.json",
        ".python-version",
        ".nvmrc",
        "tools/prepare_demo_runtime.py",
        "tools/validate_git_tracked_files.py",
        "tools/verify_demo_contract.py",
        "demo/dashboard_data/duration_price_comparison.json",
        "demo/dashboard_data/product_text_changes.json",
        "demo/dashboard_data/schedule_status.json",
    ):
        assert path in required
        assert is_public_source_path(path)


def test_public_publisher_uses_validated_staging_and_no_hardcoded_repo() -> None:
    script = (ROOT / "PUBLISH_PUBLIC_SOURCE.ps1").read_text(encoding="utf-8")
    assert "build_release_staging.py" in script
    assert "validate_manifest.py" in script
    assert "VERIFY_V2.ps1" in script
    assert "publisher.local.json" in script
    assert "Cloud-Phone-Monitor-Skill.git" not in script
    assert "Cloud-Phone-Pricing-Monitor.git" not in script


def test_v2_verifier_and_demo_are_release_oriented() -> None:
    verify = (ROOT / "VERIFY_V2.ps1").read_text(encoding="utf-8")
    demo = (ROOT / "START_DEMO.ps1").read_text(encoding="utf-8")
    prepare = (ROOT / "PREPARE_RELEASE.ps1").read_text(encoding="utf-8")
    assert "RELEASE_READY=True" in verify
    assert "FastAPI network smoke" in verify
    assert "prepare_demo_runtime.py" in verify
    assert "DEMO_READY=True" in demo
    assert "output\\demo_runtime" in demo
    assert "RUN_AI_TESTS.ps1" in prepare
    assert "verify_demo_contract.py" in prepare
    assert "AI_SERVICE_LAUNCH_TOKEN" in verify
    assert "service_pid" in verify
    assert "Assert-TcpPortAvailable" in verify
