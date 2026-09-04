from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

from cloud_phone_monitor import login_wait_for_signal as helper
from cloud_phone_monitor.auth_session_contract import LOGIN_PROTOCOL_VERSION, normalize_session_id

PROTOCOL_SCHEMA_VERSION = LOGIN_PROTOCOL_VERSION


def _helper_capabilities() -> dict[str, Any]:
    """Discover helper CLI capability without reading/parsing its source code.

    New helpers may expose LOGIN_PROTOCOL_VERSION. Legacy helpers are queried via
    their argparse --help output. The adapter is the only backwards-compatibility
    boundary; controller/status semantics remain on LOGIN_PROTOCOL_VERSION.
    """
    declared = getattr(helper, "LOGIN_PROTOCOL_VERSION", None)
    if declared is not None:
        try:
            declared_int = int(declared)
        except Exception as exc:
            raise RuntimeError(f"invalid helper LOGIN_PROTOCOL_VERSION: {declared!r}") from exc
        if declared_int > LOGIN_PROTOCOL_VERSION:
            raise RuntimeError(
                f"login helper protocol {declared_int} is newer than controller protocol {LOGIN_PROTOCOL_VERSION}"
            )
    proc = subprocess.run(
        [sys.executable, "-m", "cloud_phone_monitor.login_wait_for_signal", "--help"],
        cwd=str(Path(__file__).resolve().parents[1]),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=20,
        check=False,
    )
    help_text = proc.stdout or ""
    if proc.returncode != 0:
        raise RuntimeError(f"unable to query login helper CLI: exit={proc.returncode} output={help_text[-1000:]}")
    return {
        "declared_protocol_version": declared,
        "accepts_session_id": "--session-id" in help_text,
    }


def _build_helper_argv(args: argparse.Namespace) -> list[str]:
    argv = [
        "login_wait_for_signal",
        "--platform",
        args.platform,
        "--save-storage-state",
        args.save_storage_state,
        "--signal-file",
        args.signal_file,
        "--status-file",
        args.status_file,
    ]
    if _helper_capabilities()["accepts_session_id"]:
        argv += ["--session-id", args.session_id]
    if args.storage_state:
        argv += ["--storage-state", args.storage_state]
    if args.persistent_profile:
        argv += ["--persistent-profile", args.persistent_profile]
    if args.runtime_context:
        argv += ["--runtime-context", args.runtime_context]
    if args.entry_url:
        argv += ["--entry-url", args.entry_url]
    return argv


def main() -> int:
    parser = argparse.ArgumentParser(description="Session-bound adapter for login_wait_for_signal.")
    parser.add_argument("--platform", required=True, choices=["VSPhone", "Redfinger", "LDCloud", "UgPhone"])
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--save-storage-state", required=True)
    parser.add_argument("--storage-state", default=None)
    parser.add_argument("--persistent-profile", default=None)
    parser.add_argument("--runtime-context", default=None)
    parser.add_argument("--entry-url", default=None)
    parser.add_argument("--signal-file", required=True)
    parser.add_argument("--status-file", required=True)
    args = parser.parse_args()

    try:
        session_id = normalize_session_id(args.session_id)
    except ValueError as exc:
        raise SystemExit(f"invalid --session-id; canonical UUID required: {exc}") from exc

    original_write_status = helper.write_status
    original_argv = sys.argv[:]

    def session_bound_write_status(path: Path, payload: dict[str, Any]) -> None:
        value = dict(payload or {})
        existing = str(value.get("session_id") or "").strip()
        if existing and existing != session_id:
            raise RuntimeError(
                f"helper attempted to write mismatched session_id: expected={session_id} actual={existing}"
            )
        value["schema_version"] = max(int(value.get("schema_version") or 0), PROTOCOL_SCHEMA_VERSION)
        value["login_protocol_version"] = LOGIN_PROTOCOL_VERSION
        value["session_id"] = session_id
        value["protocol_adapter"] = "login_helper_session_entry"
        original_write_status(path, value)

    helper.write_status = session_bound_write_status
    sys.argv = _build_helper_argv(args)
    try:
        result = helper.main()
        return int(result or 0)
    finally:
        helper.write_status = original_write_status
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
