import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError

from cloud_phone_monitor.config import MonitorConfig
from cloud_phone_monitor.utils.browser import launch_browser


def write_status(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Open a platform login page and wait for a local signal file.")
    parser.add_argument("--platform", required=True, choices=["VSPhone", "Redfinger", "LDCloud"])
    parser.add_argument("--storage-state", default=None)
    parser.add_argument("--save-storage-state", required=True)
    parser.add_argument("--signal-file", required=True)
    parser.add_argument("--status-file", required=True)
    args = parser.parse_args()

    config = MonitorConfig.default()
    target = config.targets[args.platform]
    storage_state = Path(args.storage_state) if args.storage_state else None
    save_storage_state = Path(args.save_storage_state)
    signal_file = Path(args.signal_file)
    status_file = Path(args.status_file)

    signal_file.parent.mkdir(parents=True, exist_ok=True)
    if signal_file.exists():
        signal_file.unlink()

    status = {
        "platform": args.platform,
        "target_url": target.url,
        "status": "starting",
        "started_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "signal_file": str(signal_file),
        "save_storage_state": str(save_storage_state),
    }
    write_status(status_file, status)

    try:
        with launch_browser(headless=False, storage_state=storage_state) as (_, _, context):
            page = context.new_page()
            page.set_default_timeout(config.browser_timeout_ms)
            page.goto(target.url, wait_until="domcontentloaded", timeout=config.browser_timeout_ms)
            status["status"] = "waiting_for_user_signal"
            status["opened_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            write_status(status_file, status)

            while not signal_file.exists():
                page.wait_for_timeout(1000)

            save_storage_state.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(save_storage_state))
            status["status"] = "saved"
            status["saved_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            write_status(status_file, status)
    except PlaywrightError as exc:
        status["status"] = "failed"
        status["error"] = f"{type(exc).__name__}: {exc}"
        status["failed_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        write_status(status_file, status)
        raise


if __name__ == "__main__":
    main()
