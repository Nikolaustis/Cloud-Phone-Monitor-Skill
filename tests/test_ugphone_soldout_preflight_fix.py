from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOGIN_HELPER = ROOT / "cloud_phone_monitor" / "login_wait_for_signal.py"


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
