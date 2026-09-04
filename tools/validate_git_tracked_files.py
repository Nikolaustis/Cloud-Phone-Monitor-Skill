from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

try:
    from tools.public_release_policy import (
        CONCRETE_GITHUB_REMOTE,
        FORBIDDEN_DIR_NAMES,
        FORBIDDEN_FILE_NAMES,
        FORBIDDEN_SUFFIXES,
        SENSITIVE_NAME_RE,
        is_public_source_path,
    )
except ModuleNotFoundError:
    from public_release_policy import (
        CONCRETE_GITHUB_REMOTE,
        FORBIDDEN_DIR_NAMES,
        FORBIDDEN_FILE_NAMES,
        FORBIDDEN_SUFFIXES,
        SENSITIVE_NAME_RE,
        is_public_source_path,
    )

TEXT_SUFFIXES = {
    ".py", ".ps1", ".js", ".jsx", ".json", ".md", ".txt", ".sh", ".bat",
    ".yml", ".yaml", ".toml", ".ini", ".cfg", ".env", ".example",
}

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("OpenAI-style secret", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("Bearer token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{20,}")),
)

# Source files whose names naturally contain auth/runtime vocabulary but are
# source code rather than credentials. They still must pass the public allowlist.
SENSITIVE_SOURCE_NAME_EXCEPTIONS = {
    "cloud_phone_monitor/auth_session_contract.py",
    "cloud_phone_monitor/auth_file_transaction.py",
    "cloud_phone_monitor/login_controller.py",
    "cloud_phone_monitor/login_helper_session_entry.py",
    "cloud_phone_monitor/login_wait_for_signal.py",
    "deployment/windows/check_skill_login_state.py",
}


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or "git command failed")
    return result.stdout


def tracked_paths(root: Path) -> list[str]:
    raw = _git(root, "ls-files", "-z")
    return sorted(item.decode("utf-8", errors="strict") for item in raw.split(b"\0") if item)


def _looks_text(path: Path) -> bool:
    if path.name in {".gitignore", ".gitattributes", ".nvmrc", ".python-version", "LICENSE"}:
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


def _scan_index_text(root: Path, rel: str, problems: list[str]) -> None:
    try:
        blob = _git(root, "show", f":{rel}")
    except RuntimeError:
        return
    if len(blob) > 5_000_000:
        return
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        return

    if CONCRETE_GITHUB_REMOTE.search(text):
        problems.append(f"concrete GitHub remote found in tracked public source: {rel}")
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            problems.append(f"possible {label} found in tracked file: {rel}")


def validate_tracked_tree(root: Path) -> list[str]:
    root = root.resolve()
    problems: list[str] = []
    for rel in tracked_paths(root):
        normalized = rel.replace("\\", "/")
        path = root / normalized
        parts = Path(normalized).parts
        name = Path(normalized).name

        if normalized != "MANIFEST_SHA256.txt" and not is_public_source_path(normalized):
            problems.append(f"tracked file is outside explicit public allowlist: {normalized}")
        is_demo_dashboard_data = len(parts) >= 2 and parts[0] == "demo" and parts[1] == "dashboard_data"
        if any(part in FORBIDDEN_DIR_NAMES for part in parts[:-1]) and not is_demo_dashboard_data:
            problems.append(f"tracked forbidden directory/file: {normalized}")
        if name in FORBIDDEN_FILE_NAMES:
            problems.append(f"tracked private maintainer file: {normalized}")
        if Path(name).suffix.lower() in FORBIDDEN_SUFFIXES:
            problems.append(f"tracked forbidden generated/private file: {normalized}")
        if SENSITIVE_NAME_RE.search(name) and normalized not in SENSITIVE_SOURCE_NAME_EXCEPTIONS:
            problems.append(f"tracked file name looks like credential/runtime state: {normalized}")
        if path.is_symlink():
            problems.append(f"tracked symlink is not allowed in public repository: {normalized}")
        if _looks_text(path):
            # Scan the Git index blob rather than the working-tree bytes. This
            # makes the check faithful to what would actually be committed.
            _scan_index_text(root, normalized, problems)

    # Deduplicate while preserving deterministic output order.
    return sorted(set(problems))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Git-tracked files against the canonical public allowlist and conservative secret patterns."
    )
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        problems = validate_tracked_tree(root)
    except RuntimeError as exc:
        print(f"Tracked-file validation failed to run: {exc}")
        return 3
    if problems:
        print("Tracked-file validation failed:")
        for item in problems:
            print("-", item)
        return 2
    print("Tracked-file validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
