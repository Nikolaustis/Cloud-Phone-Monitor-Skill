from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cloud_phone_monitor.auth_session_contract import evaluate_auth_evidence, signal_matches_session
from cloud_phone_monitor.config import MonitorConfig
from cloud_phone_monitor.utils.browser import launch_browser


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)



def _pending_path(final_path: Path, session_id: str) -> Path:
    return final_path.with_name(f"{final_path.name}.pending.{session_id}")


def _remove_file(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _replace_file(pending: Path | None, final: Path | None) -> None:
    if pending is None or final is None:
        return
    if not pending.is_file() or pending.stat().st_size <= 2:
        raise RuntimeError(f"pending auth artifact missing or empty: {pending}")
    final.parent.mkdir(parents=True, exist_ok=True)
    pending.replace(final)


IDENTITY_KEY_RE = re.compile(
    r"^(?:user_?id|uid|account_?id|member_?id|username|nickname|email|mobile|phone)$",
    re.I,
)
AUTH_ENDPOINT_RE = re.compile(r"(?:user|profile|account|member|customer|personal|mine|self)", re.I)


def _identity_key_names(value: Any, *, depth: int = 0) -> list[str]:
    if depth > 5:
        return []
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key or "")
            if IDENTITY_KEY_RE.match(key_text):
                if item not in (None, "", [], {}, False):
                    found.add(key_text[:120])
            if isinstance(item, (dict, list)):
                found.update(_identity_key_names(item, depth=depth + 1))
    elif isinstance(value, list):
        for item in value[:50]:
            if isinstance(item, (dict, list)):
                found.update(_identity_key_names(item, depth=depth + 1))
    return sorted(found)[:30]


def _attach_authenticated_api_capture(page):
    captured: list[dict[str, Any]] = []

    def on_response(response) -> None:
        try:
            if int(response.status or 0) < 200 or int(response.status or 0) >= 300:
                return
            url = str(response.url or "")
            if not AUTH_ENDPOINT_RE.search(url):
                return
            payload = response.json()
            identity_keys = _identity_key_names(payload)
            if not identity_keys:
                return
            endpoint = url.split("?", 1)[0]
            captured.append({
                "endpoint": endpoint,
                "status": int(response.status or 0),
                "identity_keys": identity_keys,
            })
            del captured[:-30]
        except Exception:
            return

    page.on("response", on_response)
    return captured, on_response


def _detach_authenticated_api_capture(page, handler) -> None:
    try:
        page.remove_listener("response", handler)
    except Exception:
        pass



def _collect_saved_auth_evidence(page, context, platform: str, authenticated_api: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    snapshot = page.evaluate(
        """() => {
          const keys = (storage) => {
            const out = [];
            for (let i = 0; i < storage.length; i += 1) {
              const key = storage.key(i);
              if (key) out.push(key);
            }
            return out;
          };
          return {
            local_keys: keys(window.localStorage),
            session_keys: keys(window.sessionStorage),
            body_text: String(document.body?.innerText || '').slice(0, 200000),
            password_inputs: Array.from(document.querySelectorAll('input[type="password"]')).filter((node) => {
              const s = getComputedStyle(node); const r = node.getBoundingClientRect();
              return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
            }).length
          };
        }"""
    )
    cookies = context.cookies()
    return evaluate_auth_evidence(
        platform=platform,
        url=str(page.url or ""),
        body_text=str(snapshot.get("body_text") or ""),
        local_keys=[str(x) for x in snapshot.get("local_keys") or []],
        session_keys=[str(x) for x in snapshot.get("session_keys") or []],
        cookie_names=[str(item.get("name") or "") for item in cookies if isinstance(item, dict)],
        authenticated_api_endpoints=[str(item.get("endpoint") or "") for item in (authenticated_api or []) if isinstance(item, dict)],
        visible_password_inputs=int(snapshot.get("password_inputs") or 0),
    )


def verify_saved_auth_state(platform: str, target_url: str, storage_state: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "platform": platform,
        "target_url": target_url,
        "storage_state": str(storage_state),
        "ok": False,
        "reason": None,
    }
    if not storage_state.is_file() or storage_state.stat().st_size <= 2:
        result["reason"] = "storage_state_missing_or_empty"
        return result

    try:
        with launch_browser(headless=True, storage_state=storage_state) as (_, _, context):
            page = context.new_page()
            authenticated_api, handler = _attach_authenticated_api_capture(page)
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
                deadline = time.monotonic() + 20.0
                evidence = _collect_saved_auth_evidence(page, context, platform, authenticated_api)
                while time.monotonic() < deadline and not evidence.get("ok"):
                    if evidence.get("login_wall_detected"):
                        break
                    page.wait_for_timeout(1_000)
                    evidence = _collect_saved_auth_evidence(page, context, platform, authenticated_api)
            finally:
                _detach_authenticated_api_capture(page, handler)
            result["evidence"] = evidence
            if not evidence.get("ok"):
                result["reason"] = str(evidence.get("reason") or "saved_auth_verification_failed")
                return result
            result["ok"] = True
            return result
    except Exception as exc:
        result["reason"] = f"saved_auth_reopen_failed:{type(exc).__name__}:{exc}"
        return result


def _wait_for_helper_status(path: Path, proc: subprocess.Popen[Any], timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        current = _read_json(path)
        if current is not None:
            last = current
            if current.get("status") == "waiting_for_user_signal":
                return current
            if current.get("status") in {"failed", "verification_failed", "verification_failed_after_reopen"}:
                return current
        if proc.poll() is not None:
            break
        time.sleep(0.25)
    return last or {"status": "helper_status_timeout"}


def _wait_for_signal(path: Path, session_id: str, proc: subprocess.Popen[Any]) -> None:
    while True:
        if signal_matches_session(path, session_id):
            return
        if proc.poll() is not None:
            raise RuntimeError("login helper exited before the matching session signal was received")
        time.sleep(0.25)


def _terminate_process_tree(proc: subprocess.Popen[Any]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
            )
            return
        except Exception:
            pass
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass



def _wait_for_child(proc: subprocess.Popen[Any], timeout: float) -> int:
    try:
        return int(proc.wait(timeout=timeout))
    except subprocess.TimeoutExpired:
        _terminate_process_tree(proc)
        raise RuntimeError("login helper verification timed out")


def main() -> int:
    parser = argparse.ArgumentParser(description="Session-bound local login controller.")
    parser.add_argument("--platform", required=True, choices=["VSPhone", "Redfinger", "LDCloud", "UgPhone"])
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--save-storage-state", required=True)
    parser.add_argument("--persistent-profile", default=None)
    parser.add_argument("--runtime-context", default=None)
    parser.add_argument("--signal-file", required=True)
    parser.add_argument("--status-file", required=True)
    args = parser.parse_args()

    config = MonitorConfig.default()
    target = config.targets[args.platform]
    session_id = str(args.session_id).strip()
    if not session_id:
        raise SystemExit("session id is required")

    final_state = Path(args.save_storage_state).resolve()
    pending_state = _pending_path(final_state, session_id)
    final_runtime = Path(args.runtime_context).resolve() if args.runtime_context else None
    pending_runtime = _pending_path(final_runtime, session_id) if final_runtime else None
    signal_file = Path(args.signal_file).resolve()
    status_file = Path(args.status_file).resolve()
    helper_signal = signal_file.with_name(f"{signal_file.name}.helper.{session_id}")
    helper_status = status_file.with_name(f"{status_file.name}.helper.{session_id}.json")

    for path in (signal_file, helper_signal, helper_status, pending_state, pending_runtime):
        _remove_file(path)

    status: dict[str, Any] = {
        "schema_version": 2,
        "session_id": session_id,
        "platform": args.platform,
        "target_url": target.url,
        "status": "starting",
        "started_at_utc": _now(),
        "final_storage_state": str(final_state),
        "pending_storage_state": str(pending_state),
        "final_runtime_context": str(final_runtime) if final_runtime else None,
        "pending_runtime_context": str(pending_runtime) if pending_runtime else None,
        "signal_file": str(signal_file),
    }
    _write_json(status_file, status)

    cmd = [
        sys.executable,
        "-m",
        "cloud_phone_monitor.login_wait_for_signal",
        "--platform",
        args.platform,
        "--save-storage-state",
        str(pending_state),
        "--signal-file",
        str(helper_signal),
        "--status-file",
        str(helper_status),
    ]
    if final_state.is_file() and args.platform != "UgPhone":
        cmd += ["--storage-state", str(final_state)]
    if args.persistent_profile:
        cmd += ["--persistent-profile", str(Path(args.persistent_profile).resolve())]
    if pending_runtime is not None:
        cmd += ["--runtime-context", str(pending_runtime)]

    proc: subprocess.Popen[Any] | None = None
    try:
        proc = subprocess.Popen(cmd, cwd=str(Path(__file__).resolve().parents[1]))
        status["helper_process_id"] = proc.pid
        helper_ready = _wait_for_helper_status(helper_status, proc, timeout=90.0)
        status["helper_status"] = helper_ready
        if helper_ready.get("status") != "waiting_for_user_signal":
            raise RuntimeError(f"login helper failed before user interaction: {helper_ready.get('status')}")

        status["status"] = "waiting_for_user_signal"
        status["opened_at_utc"] = _now()
        _write_json(status_file, status)

        _wait_for_signal(signal_file, session_id, proc)
        helper_signal.write_text(session_id, encoding="utf-8")
        status["status"] = "verifying"
        status["signal_received_at_utc"] = _now()
        _write_json(status_file, status)

        exit_code = _wait_for_child(proc, timeout=360.0)
        helper_final = _read_json(helper_status) or {}
        status["helper_exit_code"] = exit_code
        status["helper_status"] = helper_final
        if exit_code != 0 or helper_final.get("status") != "saved_and_verified":
            reason = helper_final.get("error") or helper_final.get("failure_classification") or helper_final.get("status")
            raise RuntimeError(f"login helper did not verify the session: {reason}")

        if args.platform == "UgPhone":
            post_verification = {
                "ok": True,
                "verification_source": "ugphone_helper_purchase_api_and_reopen",
                "helper_verification_after_reopen_task_equivalent": helper_final.get(
                    "verification_after_reopen_task_equivalent"
                ),
            }
        else:
            post_verification = verify_saved_auth_state(args.platform, target.url, pending_state)
        status["post_save_verification"] = post_verification
        if not post_verification.get("ok"):
            raise RuntimeError(
                f"post-save authentication verification failed: {post_verification.get('reason')}"
            )

        _replace_file(pending_state, final_state)
        if pending_runtime is not None and pending_runtime.exists():
            _replace_file(pending_runtime, final_runtime)

        status["status"] = "saved_and_verified"
        status["saved_at_utc"] = _now()
        status["reason"] = None
        _write_json(status_file, status)
        return 0
    except Exception as exc:
        status["status"] = "failed"
        status["reason"] = f"{type(exc).__name__}:{exc}"
        status["failed_at_utc"] = _now()
        _write_json(status_file, status)
        return 2
    finally:
        if proc is not None and proc.poll() is None:
            _terminate_process_tree(proc)
        for path in (helper_signal, helper_status, pending_state, pending_runtime):
            _remove_file(path)


if __name__ == "__main__":
    raise SystemExit(main())
