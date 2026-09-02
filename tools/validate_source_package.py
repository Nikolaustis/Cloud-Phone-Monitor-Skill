from __future__ import annotations

import argparse
import os
from pathlib import Path

FORBIDDEN_DIRS = {"output", "baselines", "node_modules", "dist", "__pycache__", ".pytest_cache", ".git"}
FORBIDDEN_SUFFIXES = {".pyc", ".log", ".xlsx", ".xls", ".csv", ".jsonl"}
REQUIRED = {
    "SKILL.md",
    "README.md",
    "run.py",
    "rebuild_dashboard_history.py",
    "deployment_contract.json",
    "cloud_phone_monitor/main.py",
    "dashboard/src/App.jsx",
    "deployment/windows/update_cloud_phone_dashboard.ps1",
    "deployment/windows/publish_dashboard.ps1",
    "deployment/windows/validate_cloud_phone_dashboard.py",
    "scripts/setup_daily_monitor_windows.ps1",
}


def validate(root: Path) -> list[str]:
    problems: list[str] = []
    for rel in REQUIRED:
        if not (root / rel).is_file():
            problems.append(f"required file missing: {rel}")
    for current, dirs, files in os.walk(root):
        cur = Path(current)
        rel_parts = set(cur.relative_to(root).parts)
        if rel_parts & FORBIDDEN_DIRS:
            problems.append(f"forbidden directory included: {cur.relative_to(root)}")
            dirs[:] = []
            continue
        kept_dirs = []
        for directory in dirs:
            if directory in FORBIDDEN_DIRS:
                problems.append(f"forbidden directory included: {(cur / directory).relative_to(root)}")
            else:
                kept_dirs.append(directory)
        dirs[:] = kept_dirs
        for name in files:
            path = cur / name
            rel = path.relative_to(root)
            if path.suffix.lower() in FORBIDDEN_SUFFIXES:
                problems.append(f"forbidden generated/private file: {rel}")
            low = name.lower()
            if low.endswith("_state.json") or "cookie" in low or "token" in low:
                problems.append(f"possible credential file: {rel}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    problems = validate(root)
    if problems:
        print("Source package validation failed:")
        for item in problems:
            print("-", item)
        return 2
    print("Source package validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
