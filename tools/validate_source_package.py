from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

FORBIDDEN_DIRS = {
    "output",
    "baselines",
    "logs",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".git",
}

FORBIDDEN_SUFFIXES = {
    ".pyc",
    ".log",
    ".xlsx",
    ".xls",
    ".csv",
    ".jsonl",
}

FORBIDDEN_FILES = {
    "publisher.local.json",
    "PUBLISH_SOURCE_TO_GITHUB.ps1",
    "install_windows.ps1",
    "patch_external_ugphone_preflight.py",
}

REQUIRED = {
    ".gitignore",
    ".gitattributes",
    "SKILL.md",
    "README.md",
    "LOGIN.ps1",
    "run.py",
    "rebuild_dashboard_history.py",
    "deployment_contract.json",
    "publisher.local.example.json",
    "install_dependencies_windows.ps1",
    "cloud_phone_monitor/main.py",
    "dashboard/src/App.jsx",
    "deployment/windows/update_cloud_phone_dashboard.ps1",
    "deployment/windows/publish_dashboard.ps1",
    "deployment/windows/validate_cloud_phone_dashboard.py",
    "scripts/setup_daily_monitor_windows.ps1",
}

TEXT_SUFFIXES = {
    ".py",
    ".ps1",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".txt",
    ".sh",
    ".bat",
    ".yml",
    ".yaml",
}

CONCRETE_GITHUB_REMOTE = re.compile(
    r"https://github\.com/(?!YOUR_ACCOUNT/)[^/\s\"']+/[^/\s\"']+\.git",
    re.IGNORECASE,
)


def validate(root: Path) -> list[str]:
    problems: list[str] = []

    for rel in REQUIRED:
        if not (root / rel).is_file():
            problems.append(f"required file missing: {rel}")

    for forbidden in FORBIDDEN_FILES:
        if (root / forbidden).exists():
            problems.append(f"maintainer/private file must not be public: {forbidden}")

    login_path = root / "LOGIN.ps1"
    if login_path.is_file():
        try:
            login_text = login_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            login_text = ""
        for marker in (
            "cloud_phone_monitor.login_wait_for_signal",
            "[switch]$Start",
            "[switch]$Complete",
            "LOGIN_AGENT_STATE=WAITING_FOR_USER",
            "LOGIN_AGENT_STATE=SAVED_AND_VERIFIED",
        ):
            if marker not in login_text:
                problems.append(f"LOGIN.ps1 missing required local-agent marker: {marker}")

    skill_path = root / "SKILL.md"
    if skill_path.is_file():
        try:
            skill_text = skill_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            skill_text = ""
        for marker in (
            "Authentication execution routing (hard rule)",
            "LOGIN.ps1 <Platform> -Start",
            "LOGIN.ps1 <Platform> -Complete",
            "Do not substitute Cloud Browser",
        ):
            if marker not in skill_text:
                problems.append(f"SKILL.md missing authentication-routing marker: {marker}")

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
                problems.append(
                    f"forbidden directory included: {(cur / directory).relative_to(root)}"
                )
            else:
                kept_dirs.append(directory)
        dirs[:] = kept_dirs

        for name in files:
            path = cur / name
            rel = path.relative_to(root)

            if name in FORBIDDEN_FILES:
                problems.append(f"maintainer/private file must not be public: {rel}")

            if path.suffix.lower() in FORBIDDEN_SUFFIXES:
                problems.append(f"forbidden generated/private file: {rel}")

            low = name.lower()
            if low.endswith("_state.json") or "cookie" in low or "token" in low:
                problems.append(f"possible credential file: {rel}")

            if path.suffix.lower() in TEXT_SUFFIXES:
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if CONCRETE_GITHUB_REMOTE.search(text):
                    problems.append(
                        f"concrete GitHub remote found in public source: {rel}"
                    )

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
