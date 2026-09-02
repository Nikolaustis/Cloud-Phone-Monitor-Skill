"""Compatibility patcher for legacy external UgPhone preflight scripts.

keeps this small utility because older C:\\Sites deployments may still contain
an external ``check_skill_login_state.py`` with a strict subscription-count gate.
Sold-out/currently non-subscription-capable SKUs can legitimately render zero
subscription controls, so the legacy minimum must be 0 rather than 1.
"""
from __future__ import annotations

import re
from pathlib import Path


def patch(path: str | Path) -> tuple[Path, list[str]]:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    original = text
    changes: list[str] = []

    # Support both single- and double-quoted dict literals while touching only
    # the UGPHONE_MIN_COUNTS assignment.
    pattern = re.compile(
        r"(?P<prefix>UGPHONE_MIN_COUNTS\s*=\s*\{[^\n}]*?)"
        r"(?P<quote>['\"])(subscription)(?P=quote)\s*:\s*1"
        r"(?P<suffix>[^\n}]*\})",
        flags=re.I,
    )

    def repl(match: re.Match[str]) -> str:
        changes.append("set UgPhone subscription minimum count to 0")
        # Normalize the patched key to the legacy patcher's single-quoted form.
        return f"{match.group('prefix')}'subscription': 0{match.group('suffix')}"

    text, count = pattern.subn(repl, text, count=1)
    if count and text != original:
        target.write_text(text, encoding="utf-8")
        return target, changes

    return target, ["already patched or no supported pattern found"]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    patched, changes = patch(args.path)
    print(patched)
    for item in changes:
        print(item)
