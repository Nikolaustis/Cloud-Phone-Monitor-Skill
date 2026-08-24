from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from playwright.sync_api import Browser, BrowserContext, Playwright, sync_playwright


# The interactive UgPhone login page is a mobile-first SPA.  Keep a conservative
# desktop viewport for the headed login helper; the application itself renders a
# fixed-width mobile panel inside this desktop page.
DEFAULT_VIEWPORT = {"width": 1280, "height": 720}
INTERACTIVE_WINDOW_SIZE = "1280,820"
INTERACTIVE_WINDOW_POSITION = "50,40"
DEFAULT_LOCALE = "en-US"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
UGPHONE_RUNTIME_SCHEMA_VERSION = 2
UGPHONE_RUNTIME_FILENAME = "ugphone_runtime_context.json"
# Runtime snapshots are a short-lived bridge after a manual login.  The persistent
# Chromium profile remains the long-lived authentication authority.
UGPHONE_RUNTIME_MAX_AGE_SECONDS = 30 * 60
UGPHONE_RUNTIME_HEADER_KEYS = {
    "lang",
    "terminal",
    "access-token",
    "login-id",
    "web-fingerprint",
}

# Retain only browser values required to restore UgPhone purchase pricing.
# Do not copy credential caches (password, MQTT credentials, remembered login form)
# into the runtime artifact.
UGPHONE_RUNTIME_LOCAL_STORAGE_ALLOWLIST = {
    "UGPHONE-Token",
    "UGPHONE-ID",
    "UGPHONE-PUBLICKEY",
    "ugPhoneLang",
    "ugBrowserId",
    "hadAgreePolicy",
    "hasWalletGuide",
}
UGPHONE_RUNTIME_SESSION_STORAGE_DENY_TOKENS = (
    "password",
    "passwd",
    "loginparam",
    "mqtt",
    "secret",
    "credential",
)


def _context_options() -> dict[str, Any]:
    return {
        "viewport": DEFAULT_VIEWPORT,
        "screen": {"width": 1280, "height": 720},
        "device_scale_factor": 1,
        "is_mobile": False,
        "has_touch": False,
        "locale": DEFAULT_LOCALE,
        "user_agent": DEFAULT_USER_AGENT,
    }


def _string_map(value: Any) -> dict[str, str]:
    """Return a bounded string-only storage/header mapping.

    The runtime context is a local authentication artifact.  It can contain
    session material and must remain under ``output/auth``; this helper only
    validates shape so a malformed file can never break browser startup.
    """
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for key, item in value.items():
        key_text = str(key or "").strip()
        if not key_text:
            continue
        if item is None:
            continue
        item_text = str(item)
        if len(key_text) > 200 or len(item_text) > 200_000:
            continue
        out[key_text] = item_text
    return out


def _sanitize_ugphone_local_storage(value: Any) -> dict[str, str]:
    source = _string_map(value)
    return {
        key: item
        for key, item in source.items()
        if key in UGPHONE_RUNTIME_LOCAL_STORAGE_ALLOWLIST
    }


def _sanitize_ugphone_session_storage(value: Any) -> dict[str, str]:
    source = _string_map(value)
    out: dict[str, str] = {}
    for key, item in source.items():
        lowered = key.lower()
        if any(token in lowered for token in UGPHONE_RUNTIME_SESSION_STORAGE_DENY_TOKENS):
            continue
        out[key] = item
    return out


def default_ugphone_runtime_context_path(auth_dir: Path) -> Path:
    return auth_dir / UGPHONE_RUNTIME_FILENAME


def _parse_runtime_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _runtime_context_age_seconds(value: Any) -> int | None:
    captured_at = _parse_runtime_timestamp(value)
    if captured_at is None:
        return None
    age = int((datetime.now(timezone.utc) - captured_at).total_seconds())
    return age if age >= 0 else None


def _runtime_context_is_fresh(raw: dict[str, Any]) -> bool:
    age = _runtime_context_age_seconds(raw.get("captured_at_utc"))
    return age is not None and age <= UGPHONE_RUNTIME_MAX_AGE_SECONDS


def load_ugphone_runtime_context(path: Path | None) -> dict[str, Any] | None:
    """Load a locally saved UgPhone runtime snapshot without exposing secrets."""
    if path is None or not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    # Never restore a stale runtime snapshot.  A stale token/fingerprint can
    # invalidate an otherwise healthy persistent Chromium profile.
    if not _runtime_context_is_fresh(raw):
        return None

    session_storage = _sanitize_ugphone_session_storage(raw.get("session_storage"))
    local_storage = _sanitize_ugphone_local_storage(raw.get("local_storage"))
    request_headers = _string_map((raw.get("api_request_context") or {}).get("headers"))
    request_headers = {
        key.lower(): value
        for key, value in request_headers.items()
        if key.lower() in UGPHONE_RUNTIME_HEADER_KEYS
    }
    if not session_storage and not local_storage and not request_headers:
        return None
    return {
        "schema_version": int(raw.get("schema_version") or UGPHONE_RUNTIME_SCHEMA_VERSION),
        "origin": str(raw.get("origin") or "https://www.ugphone.com"),
        "session_storage": session_storage,
        "local_storage": local_storage,
        "api_request_context": {
            "headers": request_headers,
            "endpoints": [
                str(item) for item in ((raw.get("api_request_context") or {}).get("endpoints") or [])
                if item
            ][:20],
            "responses": [
                {
                    "endpoint": str(item.get("endpoint") or ""),
                    "status": int(item.get("status") or 0),
                    "code": item.get("code"),
                    "valid": bool(item.get("valid")),
                }
                for item in ((raw.get("api_request_context") or {}).get("responses") or [])
                if isinstance(item, dict)
            ][-50:],
        },
        "browser_context": raw.get("browser_context") if isinstance(raw.get("browser_context"), dict) else {},
        "captured_at_utc": raw.get("captured_at_utc"),
    }


def runtime_context_summary(runtime_context: dict[str, Any] | None) -> dict[str, Any]:
    """Return metadata only; never return local session/header values."""
    runtime_context = runtime_context or {}
    api_context = runtime_context.get("api_request_context") or {}
    responses = [
        {
            "endpoint": str(item.get("endpoint") or ""),
            "status": int(item.get("status") or 0),
            "code": item.get("code"),
            "valid": bool(item.get("valid")),
        }
        for item in (api_context.get("responses") or [])
        if isinstance(item, dict)
    ][-20:]
    return {
        "schema_version": runtime_context.get("schema_version"),
        "captured_at_utc": runtime_context.get("captured_at_utc"),
        "age_seconds": _runtime_context_age_seconds(runtime_context.get("captured_at_utc")),
        "max_age_seconds": UGPHONE_RUNTIME_MAX_AGE_SECONDS,
        "restoration_policy": "fill_missing_only",
        "session_storage_key_count": len(runtime_context.get("session_storage") or {}),
        "local_storage_key_count": len(runtime_context.get("local_storage") or {}),
        "api_header_keys": sorted((api_context.get("headers") or {}).keys()),
        "api_endpoint_count": len(api_context.get("endpoints") or []),
        "api_responses": responses,
    }

def install_ugphone_runtime_context(
    context: BrowserContext,
    runtime_context: dict[str, Any] | None,
) -> bool:
    """Restore saved browser storage before the UgPhone SPA initialises.

    This helper intentionally does *not* intercept or rewrite UgPhone's native
    ``fetch`` / ``XMLHttpRequest`` purchase requests.  The previous approach
    forced ``lang`` / token / fingerprint headers into ``configList2`` and
    ``mealList`` calls; UgPhone can reject that altered context with
    ``Language pack error``.  The site must construct its own request headers
    from the restored browser state.

    API header snapshots remain diagnostic-only and may be used by explicit
    collector-side requests, never by the browser page's own network stack.
    """
    if not runtime_context:
        return False
    local_storage = _sanitize_ugphone_local_storage(runtime_context.get("local_storage"))
    session_storage = _sanitize_ugphone_session_storage(runtime_context.get("session_storage"))
    payload = {
        "session_storage": session_storage,
        "local_storage": local_storage,
    }
    if not any(payload.values()):
        return False

    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    script = f"""
    (() => {{
      const runtime = {serialized};
      const host = String(location.hostname || '').toLowerCase();
      if (!(host === 'ugphone.com' || host.endsWith('.ugphone.com'))) return;

      // Persistent profile and Playwright storage_state are authoritative.
      // Runtime values may fill a missing key only; they must never overwrite a
      // newer token, login id, public key or browser fingerprint already stored
      // by the live browser profile.
      const restoreMissing = (storage, values) => {{
        if (!values || typeof values !== 'object') return;
        for (const [key, value] of Object.entries(values)) {{
          try {{
            const existing = storage.getItem(String(key));
            if (existing !== null && String(existing).trim() !== '') continue;
            storage.setItem(String(key), String(value));
          }} catch (_) {{}}
        }}
      }};
      restoreMissing(window.sessionStorage, runtime.session_storage);
      restoreMissing(window.localStorage, runtime.local_storage);

      // Diagnostic marker only.  Do not mutate fetch/XHR or request headers.
      const bridge = Object.freeze({{ restored_storage: true, restoration_policy: 'fill_missing_only' }});
      try {{
        Object.defineProperty(window, '__UGPHONE_RUNTIME_CONTEXT__', {{
          value: bridge, configurable: true, enumerable: false, writable: false
        }});
      }} catch (_) {{
        try {{ window.__UGPHONE_RUNTIME_CONTEXT__ = bridge; }} catch (_) {{}}
      }}
    }})();
    """
    try:
        context.add_init_script(script=script)
        return True
    except Exception:
        return False

def _reset_ugphone_zoom_preferences(user_data_dir: Path) -> None:
    """Remove only UgPhone's persisted Chromium site-zoom entries."""
    prefs = user_data_dir / "Default" / "Preferences"
    if not prefs.exists():
        return
    try:
        payload = json.loads(prefs.read_text(encoding="utf-8"))
        partition = payload.get("partition")
        if not isinstance(partition, dict):
            return
        zoom_levels = partition.get("per_host_zoom_levels")
        if not isinstance(zoom_levels, dict):
            return
        keys = [key for key in zoom_levels if "ugphone.com" in str(key).lower()]
        if not keys:
            return
        for key in keys:
            zoom_levels.pop(key, None)
        tmp = prefs.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, prefs)
    except Exception:
        return


def new_browser_context(
    browser: Browser,
    storage_state: Path | None = None,
    *,
    ugphone_runtime_context: dict[str, Any] | None = None,
) -> BrowserContext:
    state_arg = str(storage_state) if storage_state and storage_state.exists() else None
    context = browser.new_context(storage_state=state_arg, **_context_options())
    install_ugphone_runtime_context(context, ugphone_runtime_context)
    return context


def new_persistent_browser_context(
    pw: Playwright,
    user_data_dir: Path,
    *,
    headless: bool = True,
    interactive_login: bool = False,
    ugphone_runtime_context: dict[str, Any] | None = None,
) -> BrowserContext:
    """Open a Chromium persistent profile with optional UgPhone runtime restore."""
    user_data_dir.mkdir(parents=True, exist_ok=True)
    if interactive_login:
        _reset_ugphone_zoom_preferences(user_data_dir)

    launch_kwargs: dict[str, Any] = {
        "user_data_dir": str(user_data_dir),
        "headless": headless,
        **_context_options(),
    }
    if interactive_login:
        launch_kwargs["args"] = [
            f"--window-size={INTERACTIVE_WINDOW_SIZE}",
            f"--window-position={INTERACTIVE_WINDOW_POSITION}",
            "--force-device-scale-factor=1",
            "--high-dpi-support=1",
        ]
    context = pw.chromium.launch_persistent_context(**launch_kwargs)
    install_ugphone_runtime_context(context, ugphone_runtime_context)
    return context


@contextmanager
def launch_browser(
    headless: bool = True,
    storage_state: Path | None = None,
    *,
    ugphone_runtime_context: dict[str, Any] | None = None,
) -> Iterator[tuple[Playwright, Browser, BrowserContext]]:
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=headless)
    context = new_browser_context(
        browser,
        storage_state,
        ugphone_runtime_context=ugphone_runtime_context,
    )
    try:
        yield pw, browser, context
    finally:
        context.close()
        browser.close()
        pw.stop()


@contextmanager
def launch_persistent_browser(
    user_data_dir: Path,
    *,
    headless: bool = False,
    interactive_login: bool = False,
    ugphone_runtime_context: dict[str, Any] | None = None,
) -> Iterator[tuple[Playwright, BrowserContext]]:
    pw = sync_playwright().start()
    context = new_persistent_browser_context(
        pw,
        user_data_dir,
        headless=headless,
        interactive_login=interactive_login,
        ugphone_runtime_context=ugphone_runtime_context,
    )
    try:
        yield pw, context
    finally:
        context.close()
        pw.stop()
