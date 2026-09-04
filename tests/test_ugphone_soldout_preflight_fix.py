from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LOGIN_HELPER = ROOT / "cloud_phone_monitor" / "login_wait_for_signal.py"
PATCHER = ROOT / "tools" / "patch_external_ugphone_preflight.py"


def _load_count_checker():
    tree = ast.parse(LOGIN_HELPER.read_text(encoding="utf-8"))
    selected = []
    wanted_constants = {
        "UGPHONE_AUTH_MIN_COUNTS",
        "UGPHONE_COMPLETE_MIN_COUNTS",
        "UGPHONE_SUBSCRIPTION_DIAGNOSTIC_MIN",
    }
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if names & wanted_constants:
                selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == "_ugphone_counts_complete":
            selected.append(node)
    namespace = {}
    module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    exec(compile(module, str(LOGIN_HELPER), "exec"), namespace)
    return namespace["_ugphone_counts_complete"]


def test_sold_out_sku_without_subscription_is_authenticated():
    check = _load_count_checker()
    assert check({"plan": 5, "region": 7, "price": 5, "subscription": 0})


def test_missing_business_evidence_still_fails():
    check = _load_count_checker()
    assert not check({"plan": 5, "region": 1, "price": 5, "subscription": 1})


def test_external_patcher_is_idempotent(tmp_path: Path):
    if not PATCHER.is_file():
        pytest.skip(
            "External UgPhone migration patcher is intentionally excluded "
            "from the public release."
        )

    spec = importlib.util.spec_from_file_location("ug_patch", PATCHER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    target = tmp_path / "check_skill_login_state.py"
    target.write_text(
        '''UGPHONE_MIN_COUNTS = {"plan": 5, "region": 2, "price": 5, "subscription": 1}\n''',
        encoding="utf-8",
    )
    _, changes = module.patch(target)
    assert any("subscription" in item for item in changes)
    first = target.read_text(encoding="utf-8")
    assert "'subscription': 0" in first

    _, changes_again = module.patch(target)
    second = target.read_text(encoding="utf-8")
    assert first == second
    assert changes_again == ["already patched or no supported pattern found"]
