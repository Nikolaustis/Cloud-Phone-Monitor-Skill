from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import os
from pathlib import Path

try:
    from tools.public_release_policy import (
        CONCRETE_GITHUB_REMOTE,
        FORBIDDEN_DIR_NAMES,
        FORBIDDEN_FILE_NAMES,
        FORBIDDEN_SUFFIXES,
        SENSITIVE_NAME_RE,
        is_public_source_path,
        required_public_paths,
    )
except ModuleNotFoundError:
    from public_release_policy import (
        CONCRETE_GITHUB_REMOTE,
        FORBIDDEN_DIR_NAMES,
        FORBIDDEN_FILE_NAMES,
        FORBIDDEN_SUFFIXES,
        SENSITIVE_NAME_RE,
        is_public_source_path,
        required_public_paths,
    )

TEXT_SUFFIXES = {".py", ".ps1", ".js", ".jsx", ".json", ".md", ".txt", ".sh", ".bat", ".yml", ".yaml"}


def _require_markers(problems: list[str], path: Path, markers: tuple[str, ...], label: str) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return
    for marker in markers:
        if marker not in text:
            problems.append(f"{label} missing required marker: {marker}")


def validate(root: Path, *, allow_local_runtime: bool = False, require_exact_public_tree: bool = False) -> list[str]:
    root = root.resolve()
    problems: list[str] = []

    for rel in sorted(required_public_paths()):
        if not (root / rel).is_file():
            problems.append(f"required public file missing: {rel}")

    login_path = root / "LOGIN.ps1"
    if login_path.is_file():
        _require_markers(
            problems,
            login_path,
            (
                "$PSScriptRoot",
                "cloud_phone_monitor.login_controller",
                ".venv\\Scripts\\python.exe",
                "LOGIN_AGENT_STATE=WAITING_FOR_USER",
                "LOGIN_AGENT_STATE=SAVED_AND_VERIFIED",
            ),
            "LOGIN.ps1",
        )

    controller = root / "cloud_phone_monitor" / "login_controller.py"
    if controller.is_file():
        _require_markers(
            problems,
            controller,
            (
                "LOGIN_PROTOCOL_VERSION",
                "normalize_session_id",
                "cloud_phone_monitor.login_helper_session_entry",
                "commit_auth_artifacts",
                "acquire_profile_lock",
            ),
            "login_controller.py",
        )

    profile_lock = root / "cloud_phone_monitor" / "profile_lock.py"
    if profile_lock.is_file():
        _require_markers(
            problems,
            profile_lock,
            (
                "O_CREAT",
                "O_EXCL",
                "ProfileLockError",
                "process_identity",
                "lock_owner_matches_process",
            ),
            "profile_lock.py",
        )

    for current, dirs, files in os.walk(root):
        cur = Path(current)
        rel_dir = cur.relative_to(root)
        rel_parts = set(rel_dir.parts)
        if rel_parts & FORBIDDEN_DIR_NAMES:
            if not allow_local_runtime:
                problems.append(f"forbidden directory included: {rel_dir}")
            dirs[:] = []
            continue

        kept_dirs = []
        for directory in dirs:
            if directory in FORBIDDEN_DIR_NAMES:
                if not allow_local_runtime:
                    problems.append(f"forbidden directory included: {(cur / directory).relative_to(root)}")
            else:
                kept_dirs.append(directory)
        dirs[:] = kept_dirs

        for name in files:
            path = cur / name
            rel = path.relative_to(root)
            rel_text = rel.as_posix()
            if path.is_symlink():
                problems.append(f"symlink is not allowed in public source: {rel_text}")
                continue
            if name in FORBIDDEN_FILE_NAMES:
                problems.append(f"maintainer/private file must not be public: {rel_text}")
            if path.suffix.lower() in FORBIDDEN_SUFFIXES:
                problems.append(f"forbidden generated/private file: {rel_text}")
            if SENSITIVE_NAME_RE.search(name) and rel_text not in {
                "cloud_phone_monitor/auth_session_contract.py",
                "cloud_phone_monitor/auth_file_transaction.py",
                "cloud_phone_monitor/login_controller.py",
                "cloud_phone_monitor/login_helper_session_entry.py",
                "cloud_phone_monitor/login_wait_for_signal.py",
                "deployment/windows/check_skill_login_state.py",
            }:
                problems.append(f"possible runtime credential artifact: {rel_text}")
            if require_exact_public_tree and name != "MANIFEST_SHA256.txt" and not is_public_source_path(rel_text):
                problems.append(f"file is outside explicit public allowlist: {rel_text}")
            if path.suffix.lower() in TEXT_SUFFIXES:
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if CONCRETE_GITHUB_REMOTE.search(text):
                    problems.append(f"concrete GitHub remote found in public source: {rel_text}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--working-tree", action="store_true", help="Ignore local runtime directories excluded from release staging.")
    parser.add_argument("--exact-public-tree", action="store_true", help="Reject any source file outside the explicit public release allowlist.")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    problems = validate(
        root,
        allow_local_runtime=args.working_tree,
        require_exact_public_tree=args.exact_public_tree,
    )
    if problems:
        print("Source package validation failed:")
        for item in problems:
            print("-", item)
        return 2
    print("Source package validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
