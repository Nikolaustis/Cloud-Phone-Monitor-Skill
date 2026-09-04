from __future__ import annotations

import json
from pathlib import Path

import pytest

from cloud_phone_monitor.profile_lock import (
    ProfileLockError,
    acquire_profile_lock,
    profile_lock_path,
    read_lock,
)


def test_profile_lock_is_exclusive_and_owner_release_is_scoped(tmp_path: Path) -> None:
    profile = tmp_path / "ugphone_profile"
    first = acquire_profile_lock(profile, platform="UgPhone", owner_kind="test", session_id="session-a")
    try:
        assert first.path == profile_lock_path(profile)
        payload = read_lock(first.path)
        assert payload is not None
        assert payload["lease_id"] == first.lease_id
        assert payload["owner_kind"] == "test"
        with pytest.raises(ProfileLockError):
            acquire_profile_lock(profile, platform="UgPhone", owner_kind="second", timeout_seconds=0)
    finally:
        assert first.release() is True
    assert not profile_lock_path(profile).exists()


def test_definitely_dead_lock_is_recovered(tmp_path: Path) -> None:
    profile = tmp_path / "ugphone_profile"
    path = profile_lock_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "lease_id": "stale",
                "platform": "UgPhone",
                "profile": str(profile),
                "owner_kind": "collector",
                "pid": 2147483000,
                "process_executable": "C:/definitely/missing/python.exe",
                "process_start_token": "1",
            }
        ),
        encoding="utf-8",
    )
    lock = acquire_profile_lock(profile, platform="UgPhone", owner_kind="replacement")
    try:
        assert lock.lease_id != "stale"
    finally:
        lock.release()
