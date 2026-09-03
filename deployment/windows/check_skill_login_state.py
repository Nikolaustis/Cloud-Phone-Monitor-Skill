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


def login_command(skill_root: Path, platform: str) -> str:
    return f'cd "{skill_root}" && powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\LOGIN.ps1 {platform}'


def agent_login_command(skill_root: Path, platform: str, phase: str) -> str:
    switch = "-Start" if phase == "start" else "-Complete"
    return (
        f'cd "{skill_root}" && powershell.exe -NoProfile -ExecutionPolicy Bypass '
        f'-File .\\LOGIN.ps1 {platform} {switch}'
    )


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
        "login_entrypoint": str(skill_root / "LOGIN.ps1"),
        "local_login_required": True,
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
            "repair_command": login_command(skill_root, platform),
            "agent_start_command": agent_login_command(skill_root, platform, "start"),
            "agent_complete_command": agent_login_command(skill_root, platform, "complete"),
        }
        print(f"[{ 'OK' if ok else 'FAIL' }] {platform}: {report['platforms'][platform]['status']}")
        if not ok:
            print(f"       Manual repair: .\\LOGIN.ps1 {platform}")
            print(f"       Agent phase 1: .\\LOGIN.ps1 {platform} -Start")

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
        "repair_command": login_command(skill_root, "UgPhone"),
        "agent_start_command": agent_login_command(skill_root, "UgPhone", "start"),
        "agent_complete_command": agent_login_command(skill_root, "UgPhone", "complete"),
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
    if not ug_result["ok"]:
        print("       Manual repair: .\\LOGIN.ps1 UgPhone")
        print("       Agent phase 1: .\\LOGIN.ps1 UgPhone -Start")

    report["all_ok"] = all(bool(row.get("ok")) for row in report["platforms"].values())
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Preflight report: {report_path}")
    print(f"all_ok = {report['all_ok']}")

    if not report["all_ok"]:
        print("")
        print("Collector authentication must be repaired in the LOCAL Playwright Chromium browser.")
        print("Do not use ChatGPT Work / Cloud Browser for collector login; that browser session is isolated from output/auth/.")
        print("For an agent with LOCAL shell access, use LOGIN.ps1 <Platform> -Start; after the user finishes login in local Chromium, use -Complete.")
        print("If LOCAL shell access is unavailable, stop instead of substituting Cloud Browser.")
        print(f'Run the repair command(s) from: {skill_root}')

    return 0 if report["all_ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
