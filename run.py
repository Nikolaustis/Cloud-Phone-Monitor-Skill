from __future__ import annotations

import sys
from pathlib import Path

from cloud_phone_monitor.main import main
from cloud_phone_monitor.profile_lock import ProfileLockError, locked_profile


def _selected_platforms(argv: list[str]) -> list[str]:
    values: list[str] = []
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == "--platform" and index + 1 < len(argv):
            values.append(argv[index + 1])
            index += 2
            continue
        if item.startswith("--platform="):
            values.append(item.split("=", 1)[1])
        index += 1
    return values


def _uses_ugphone_profile(argv: list[str]) -> bool:
    selected = {value.strip().lower() for value in _selected_platforms(argv) if value.strip()}
    # No --platform filter means the normal all-platform run includes UgPhone.
    return not selected or "ugphone" in selected


def _run() -> None:
    if not _uses_ugphone_profile(sys.argv[1:]):
        main()
        return

    skill_root = Path(__file__).resolve().parent
    profile = skill_root / "output" / "auth" / "ugphone_profile"
    try:
        with locked_profile(
            profile,
            platform="UgPhone",
            owner_kind="collector",
            timeout_seconds=0.0,
        ):
            main()
    except ProfileLockError as exc:
        raise SystemExit(
            "UgPhone persistent profile is currently in use by another verified local process. "
            f"Collector stopped before opening Chromium: {exc}"
        ) from exc


if __name__ == "__main__":
    _run()
