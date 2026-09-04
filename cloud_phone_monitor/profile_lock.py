from __future__ import annotations

import contextlib
import ctypes
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

LOCK_SCHEMA_VERSION = 1


class ProfileLockError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def profile_lock_path(profile: Path) -> Path:
    profile = profile.resolve()
    return profile.parent / f"{profile.name}.lock.json"


def _windows_process_identity(pid: int) -> dict[str, Any]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        err = ctypes.get_last_error()
        if err in {87, 1168}:  # invalid parameter / not found
            return {"alive": False, "pid": int(pid), "query_error": err}
        return {"alive": True, "pid": int(pid), "identity_complete": False, "query_error": err}
    try:
        size = ctypes.c_ulong(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        executable = None
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            executable = str(buffer.value)

        creation = ctypes.c_ulonglong()
        exit_time = ctypes.c_ulonglong()
        kernel = ctypes.c_ulonglong()
        user = ctypes.c_ulonglong()
        start_token = None
        if kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            start_token = str(int(creation.value))
        return {
            "alive": True,
            "pid": int(pid),
            "executable": executable,
            "start_token": start_token,
            "identity_complete": bool(executable and start_token),
        }
    finally:
        kernel32.CloseHandle(handle)


def _posix_process_identity(pid: int) -> dict[str, Any]:
    proc = Path("/proc") / str(int(pid))
    if not proc.exists():
        return {"alive": False, "pid": int(pid)}
    executable = None
    start_token = None
    try:
        executable = str((proc / "exe").resolve())
    except Exception:
        pass
    try:
        fields = (proc / "stat").read_text(encoding="utf-8").split()
        if len(fields) > 21:
            start_token = fields[21]
    except Exception:
        pass
    return {
        "alive": True,
        "pid": int(pid),
        "executable": executable,
        "start_token": start_token,
        "identity_complete": bool(executable and start_token),
    }


def process_identity(pid: int) -> dict[str, Any]:
    if int(pid) <= 0:
        return {"alive": False, "pid": int(pid)}
    if os.name == "nt":
        return _windows_process_identity(int(pid))
    return _posix_process_identity(int(pid))


def current_process_identity() -> dict[str, Any]:
    identity = process_identity(os.getpid())
    if not identity.get("executable"):
        identity["executable"] = str(Path(sys.executable).resolve())
    return identity


def _norm_path(value: Any) -> str:
    try:
        return os.path.normcase(os.path.abspath(str(value or "")))
    except Exception:
        return str(value or "")


def lock_owner_matches_process(payload: dict[str, Any]) -> bool:
    try:
        pid = int(payload.get("pid") or 0)
    except Exception:
        return False
    actual = process_identity(pid)
    if not actual.get("alive"):
        return False
    expected_exe = payload.get("process_executable")
    expected_start = payload.get("process_start_token")
    actual_exe = actual.get("executable")
    actual_start = actual.get("start_token")
    if not expected_exe or not expected_start or not actual_exe or not actual_start:
        return False
    return _norm_path(expected_exe) == _norm_path(actual_exe) and str(expected_start) == str(actual_start)


def read_lock(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _atomic_create(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(str(path), flags, 0o600)
    try:
        raw = (json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n").encode("utf-8")
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)


def _remove_if_owned(path: Path, lease_id: str) -> bool:
    payload = read_lock(path)
    if not payload or str(payload.get("lease_id") or "") != str(lease_id):
        return False
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return True


@dataclass
class ProfileLock:
    path: Path
    lease_id: str
    payload: dict[str, Any]

    def release(self) -> bool:
        return _remove_if_owned(self.path, self.lease_id)


def acquire_profile_lock(
    profile: Path,
    *,
    platform: str,
    owner_kind: str,
    session_id: str | None = None,
    timeout_seconds: float = 0.0,
    poll_interval: float = 0.25,
) -> ProfileLock:
    profile = profile.resolve()
    path = profile_lock_path(profile)
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))

    while True:
        identity = current_process_identity()
        lease_id = str(uuid.uuid4())
        payload = {
            "schema_version": LOCK_SCHEMA_VERSION,
            "lease_id": lease_id,
            "platform": str(platform),
            "profile": str(profile),
            "owner_kind": str(owner_kind),
            "session_id": str(session_id) if session_id else None,
            "pid": os.getpid(),
            "process_executable": identity.get("executable"),
            "process_start_token": identity.get("start_token"),
            "acquired_at_utc": _now(),
        }
        try:
            _atomic_create(path, payload)
            return ProfileLock(path=path, lease_id=lease_id, payload=payload)
        except FileExistsError:
            existing = read_lock(path)
            if existing is None:
                raise ProfileLockError(f"profile lock exists but is unreadable; refusing to remove it: {path}")

            try:
                existing_pid = int(existing.get("pid") or 0)
            except Exception:
                existing_pid = 0
            actual = process_identity(existing_pid)
            if not actual.get("alive"):
                # Only a definitely-dead owner may be cleaned automatically.
                try:
                    path.unlink()
                    continue
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    raise ProfileLockError(f"stale profile lock could not be removed: {path}: {exc}") from exc

            if not lock_owner_matches_process(existing):
                # A live PID with mismatching/unverifiable identity is treated conservatively.
                detail = {
                    "pid": existing_pid,
                    "owner_kind": existing.get("owner_kind"),
                    "session_id": existing.get("session_id"),
                    "identity_verified": False,
                }
            else:
                detail = {
                    "pid": existing_pid,
                    "owner_kind": existing.get("owner_kind"),
                    "session_id": existing.get("session_id"),
                    "identity_verified": True,
                }

            if time.monotonic() >= deadline:
                raise ProfileLockError(
                    f"persistent profile is already locked: {path}; owner={json.dumps(detail, ensure_ascii=False)}"
                )
            time.sleep(max(0.05, float(poll_interval)))


@contextlib.contextmanager
def locked_profile(
    profile: Path,
    *,
    platform: str,
    owner_kind: str,
    session_id: str | None = None,
    timeout_seconds: float = 0.0,
) -> Iterator[ProfileLock]:
    lock = acquire_profile_lock(
        profile,
        platform=platform,
        owner_kind=owner_kind,
        session_id=session_id,
        timeout_seconds=timeout_seconds,
    )
    try:
        yield lock
    finally:
        lock.release()
