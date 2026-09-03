from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

FORBIDDEN_DIRS = {
    "output", "baselines", "logs", "node_modules", "dist", "__pycache__", ".pytest_cache", ".git",
}
FORBIDDEN_SUFFIXES = {".pyc", ".log", ".xlsx", ".xls", ".csv", ".jsonl"}
FORBIDDEN_FILES = {
    "publisher.local.json", "PUBLISH_SOURCE_TO_GITHUB.ps1", "install_windows.ps1", "patch_external_ugphone_preflight.py",
}
REQUIRED = {
    ".gitignore",
    ".gitattributes",
    "SKILL.md",
    "README.md",
    "LOGIN.ps1",
    "INSTALL.ps1",
    "install_dependencies_windows.ps1",
    "requirements.txt",
    "requirements-dev.txt",
    "RUN_TESTS.ps1",
    "run.py",
    "rebuild_dashboard_history.py",
    "deployment_contract.json",
    "publisher.local.example.json",
    "cloud_phone_monitor/main.py",
    "cloud_phone_monitor/login_wait_for_signal.py",
    "cloud_phone_monitor/login_controller.py",
    "cloud_phone_monitor/auth_session_contract.py",
    "dashboard/src/App.jsx",
    "deployment/windows/update_cloud_phone_dashboard.ps1",
    "deployment/windows/publish_dashboard.ps1",
    "deployment/windows/validate_cloud_phone_dashboard.py",
    "deployment/windows/verify_deployment.ps1",
    "scripts/setup_daily_monitor_windows.ps1",
    "tests/auth_state_machine/test_auth_session_contract.py",
    "tests/auth_state_machine/test_login_source_contract.py",
    "tests/auth_state_machine/windows_login_smoke.ps1",
}
TEXT_SUFFIXES = {".py", ".ps1", ".js", ".jsx", ".json", ".md", ".txt", ".sh", ".bat", ".yml", ".yaml"}
CONCRETE_GITHUB_REMOTE = re.compile(
    r"https://github\.com/(?!YOUR_ACCOUNT/)[^/\s\"']+/[^/\s\"']+\.git", re.IGNORECASE
)


def _require_markers(problems: list[str], path: Path, markers: tuple[str, ...], label: str) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return
    for marker in markers:
        if marker not in text:
            problems.append(f"{label} missing required marker: {marker}")


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
        _require_markers(
            problems,
            login_path,
            (
                "$PSScriptRoot",
                "cloud_phone_monitor.login_controller",
                "Resolve-PlaywrightPython",
                "session_id",
                "process_start_ticks",
                "LOGIN_AGENT_STATE=WAITING_FOR_USER",
                "LOGIN_AGENT_STATE=SAVED_AND_VERIFIED",
            ),
            "LOGIN.ps1",
        )

    installer = root / "INSTALL.ps1"
    if installer.is_file():
        _require_markers(
            problems,
            installer,
            (
                "Validate source package completeness",
                "Required source package file missing",
                "Validate installed Skill completeness",
                "cloud_phone_monitor\\login_controller.py",
            ),
            "INSTALL.ps1",
        )

    controller = root / "cloud_phone_monitor" / "login_controller.py"
    if controller.is_file():
        _require_markers(
            problems,
            controller,
            (
                "signal_matches_session",
                "verify_saved_auth_state",
                ".pending.",
                "session_id",
            ),
            "login_controller.py",
        )


    auth_contract = root / "cloud_phone_monitor" / "auth_session_contract.py"
    if auth_contract.is_file():
        _require_markers(
            problems,
            auth_contract,
            (
                "no_server_acknowledged_auth_evidence",
                "signal_matches_session",
                "server_authenticated",
            ),
            "auth_session_contract.py",
        )

    skill_path = root / "SKILL.md"
    if skill_path.is_file():
        _require_markers(
            problems,
            skill_path,
            (
                "Authentication execution routing (hard rule)",
                "LOGIN.ps1 <Platform> -Start",
                "LOGIN.ps1 <Platform> -Complete",
                "Do not substitute Cloud Browser",
            ),
            "SKILL.md",
        )

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
                    problems.append(f"concrete GitHub remote found in public source: {rel}")
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
