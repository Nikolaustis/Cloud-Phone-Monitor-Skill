from __future__ import annotations

from pathlib import Path
from typing import Any


def pending_path(final_path: Path, session_id: str) -> Path:
    return final_path.with_name(f"{final_path.name}.pending.{session_id}")


def remove_file(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _validate_pending(pending: Path | None) -> None:
    if pending is None:
        return
    if not pending.is_file() or pending.stat().st_size <= 2:
        raise RuntimeError(f"pending auth artifact missing or empty: {pending}")


def _backup_path(final: Path, session_id: str) -> Path:
    return final.with_name(f"{final.name}.previous.{session_id}")


def commit_auth_artifacts(
    *,
    session_id: str,
    artifacts: list[tuple[Path | None, Path | None]],
) -> dict[str, Any]:
    """Commit pending auth files with best-effort rollback across the file set."""
    active = [(pending, final) for pending, final in artifacts if pending is not None and final is not None]
    for pending, _ in active:
        _validate_pending(pending)

    backups: dict[Path, Path | None] = {}
    committed: list[Path] = []
    try:
        for pending, final in active:
            assert pending is not None and final is not None
            final.parent.mkdir(parents=True, exist_ok=True)
            backup = _backup_path(final, session_id)
            remove_file(backup)
            if final.exists():
                final.replace(backup)
                backups[final] = backup
            else:
                backups[final] = None
            pending.replace(final)
            committed.append(final)
    except Exception:
        for final in reversed(committed):
            try:
                remove_file(final)
                backup = backups.get(final)
                if backup is not None and backup.exists():
                    backup.replace(final)
            except Exception:
                pass
        for final, backup in backups.items():
            if final in committed:
                continue
            try:
                if backup is not None and backup.exists() and not final.exists():
                    backup.replace(final)
            except Exception:
                pass
        raise
    else:
        for backup in backups.values():
            remove_file(backup)

    return {
        "session_id": session_id,
        "committed": [str(final) for _, final in active if final is not None],
        "rollback_backups_cleaned": True,
    }
