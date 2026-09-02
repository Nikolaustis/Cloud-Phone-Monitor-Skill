from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def nonempty_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 2
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate local auth state before the scheduled Cloud Phone Monitor run.")
    parser.add_argument("--skill-root", required=True)
    parser.add_argument("--report", default=None)
    parser.add_argument("--skip-live-ugphone", action="store_true")
    args = parser.parse_args()

    skill_root = Path(args.skill_root).resolve()
    report_path = Path(args.report) if args.report else skill_root / "output" / "scheduler_logs" / "login_preflight_report.json"
    auth_dir = skill_root / "output" / "auth"
    report: dict[str, Any] = {
        "checked_at_utc": now_iso(),
        "skill_root": str(skill_root),
        "auth_dir": str(auth_dir),
        "platforms": {},
        "all_ok": False,
    }

    state_files = {
        "VSPhone": auth_dir / "vsphone_state.json",
        "Redfinger": auth_dir / "redfinger_state.json",
        "LDCloud": auth_dir / "ldcloud_state.json",
    }
    for platform, path in state_files.items():
        ok = nonempty_file(path)
        report["platforms"][platform] = {
            "ok": ok,
            "status": "ok" if ok else "missing_or_empty_storage_state",
            "state_file": str(path),
        }
        print(f"[{ 'OK' if ok else 'FAIL' }] {platform}: {report['platforms'][platform]['status']}")

    ug_state = auth_dir / "ugphone_state.json"
    ug_profile = auth_dir / "ugphone_profile"
    ug_runtime = auth_dir / "ugphone_runtime_context.json"
    ug_base_ok = nonempty_file(ug_state) and ug_profile.is_dir()
    ug_result: dict[str, Any] = {
        "ok": ug_base_ok,
        "status": "local_auth_files_ready" if ug_base_ok else "missing_ugphone_profile_or_state",
        "state_file": str(ug_state),
        "persistent_profile": str(ug_profile),
        "runtime_context": str(ug_runtime),
    }

    if ug_base_ok and not args.skip_live_ugphone:
        try:
            sys.path.insert(0, str(skill_root))
            from cloud_phone_monitor.config import MonitorConfig
            from cloud_phone_monitor.login_wait_for_signal import _reopen_and_verify_persistent_profile

            target = MonitorConfig.default().targets["UgPhone"]
            verification = _reopen_and_verify_persistent_profile(
                "UgPhone",
                target.url,
                ug_profile,
                ug_runtime,
                headless=True,
            )
            ug_result["live_verification"] = verification
            ug_result["ok"] = bool(verification.get("ok"))
            ug_result["status"] = "ok_live_verified_persistent_profile" if ug_result["ok"] else str(
                verification.get("reason") or "live_verification_failed"
            )
        except Exception as exc:  # pragma: no cover - depends on live browser/site state
            ug_result["ok"] = False
            ug_result["status"] = f"live_verification_exception:{type(exc).__name__}"
            ug_result["error"] = str(exc)

    report["platforms"]["UgPhone"] = ug_result
    print(f"[{ 'OK' if ug_result['ok'] else 'FAIL' }] UgPhone: {ug_result['status']}")

    report["all_ok"] = all(bool(row.get("ok")) for row in report["platforms"].values())
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Preflight report: {report_path}")
    print(f"all_ok = {report['all_ok']}")
    return 0 if report["all_ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
