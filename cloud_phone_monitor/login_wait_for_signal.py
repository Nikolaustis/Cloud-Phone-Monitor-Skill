from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError, Page, TimeoutError as PlaywrightTimeoutError

from cloud_phone_monitor.config import MonitorConfig
from cloud_phone_monitor.utils.browser import (
    UGPHONE_RUNTIME_HEADER_KEYS,
    default_ugphone_runtime_context_path,
    launch_browser,
    launch_persistent_browser,
    load_ugphone_runtime_context,
    runtime_context_summary,
)


UGPHONE_LOGIN_ENTRY_URL = "https://www.ugphone.com/toc-portal/#/login"
UGPHONE_LOGIN_MARKERS = [
    "通过google登录",
    "通过apple登录",
    "通过facebook登录",
    "手机号登录",
    "sign up with google",
    "sign up with apple",
    "sign up with facebook",
    "login with google",
    "login with apple",
    "login with facebook",
    "phone login",
]
UGPHONE_BUSINESS_SELECTORS = {
    "plan": ".purchase-details-container .config-name",
    "region": ".purchase-details-container .room-item",
    "price": ".purchase-details-container .price-item .card-price-num",
}
UGPHONE_API_TOKENS = ("configlist2", "meallist")
UGPHONE_PURCHASE_ERROR_MARKERS = {
    "language pack error": "language_pack_error",
    "语言包错误": "language_pack_error",
    "language package error": "language_pack_error",
    "系统错误": "purchase_page_error",
}
# Login/authentication readiness is proven by stable purchase-page business data.
# The subscription control is SKU/inventory dependent: sold-out combinations do
# not render it at all, so it must remain diagnostic rather than an auth gate.
UGPHONE_AUTH_MIN_COUNTS = {"plan": 5, "region": 2, "price": 5}
UGPHONE_COMPLETE_MIN_COUNTS = {**UGPHONE_AUTH_MIN_COUNTS, "subscription": 0}
UGPHONE_SUBSCRIPTION_DIAGNOSTIC_MIN = 1
UGPHONE_REQUIRED_API_TOKENS = ("configlist2",)

GENERIC_LOGIN_URL_TOKENS = ("/login", "/signin", "/sign-in", "#/login", "#/signin")
GENERIC_LOGIN_TEXT_MARKERS = (
    "sign in", "log in", "login with", "phone login", "password",
    "登录", "登入", "登錄",
)
GENERIC_AUTH_TEXT_MARKERS = (
    "log out", "sign out", "account center", "my account", "my devices", "wallet",
    "退出登录", "退出登入", "账户中心", "帳戶中心", "我的设备", "我的設備", "钱包", "錢包",
)
PLATFORM_BUSINESS_MARKERS = {
    "VSPhone": ("auto renew", "high-end real", "game afk", "android", "cloud phone", "自动续费", "雲手機", "云手机"),
    "Redfinger": ("cloud phone", "vip", "kvip", "svip", "xvip", "云手机", "雲手機"),
    "LDCloud": ("cloud phone", "vip", "kvip", "svip", "xvip", "mvip", "云手机", "雲手機"),
}
AUTH_KEY_PATTERN = re.compile(r"auth|token|session|user[_-]?id|account[_-]?id|login", re.IGNORECASE)


def write_status(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _body_text(page: Page) -> str:
    try:
        return (page.locator("body").inner_text(timeout=5_000) or "").lower()
    except Exception:
        return ""


def _assess_generic_session_evidence(
    platform: str,
    current_url: str,
    body_text: str,
    browser_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed unless both authentication and purchase-page evidence exist."""
    lowered_url = str(current_url or "").lower()
    lowered_body = str(body_text or "").lower()
    login_route = any(token in lowered_url for token in GENERIC_LOGIN_URL_TOKENS)
    visible_password = bool(browser_evidence.get("visible_password_input"))
    login_markers = [token for token in GENERIC_LOGIN_TEXT_MARKERS if token in lowered_body]
    auth_text_markers = [token for token in GENERIC_AUTH_TEXT_MARKERS if token in lowered_body]
    auth_storage_keys = list(browser_evidence.get("auth_storage_keys") or [])
    auth_cookie_names = list(browser_evidence.get("auth_cookie_names") or [])
    business_markers = [
        token for token in PLATFORM_BUSINESS_MARKERS.get(platform, ()) if token in lowered_body
    ]
    price_like_count = int(browser_evidence.get("price_like_count") or 0)

    login_gate = bool(login_route or visible_password or (login_markers and not auth_text_markers))
    authenticated = bool(auth_text_markers or auth_storage_keys or auth_cookie_names)
    business_ready = bool(business_markers and price_like_count > 0)
    ok = bool(not login_gate and authenticated and business_ready)
    if login_gate:
        reason = "login_page_detected"
    elif not authenticated:
        reason = "authenticated_session_evidence_missing"
    elif not business_ready:
        reason = "purchase_business_evidence_missing"
    else:
        reason = None
    return {
        "ok": ok,
        "reason": reason,
        "url_after_navigation": current_url,
        "login_route": login_route,
        "visible_password_input": visible_password,
        "login_markers": login_markers,
        "auth_text_markers": auth_text_markers,
        "auth_storage_keys": auth_storage_keys,
        "auth_cookie_names": auth_cookie_names,
        "business_markers": business_markers,
        "price_like_count": price_like_count,
    }


def _generic_browser_evidence(page: Page) -> dict[str, Any]:
    evidence = page.evaluate(
        """() => {
          const visible = (node) => {
            if (!node) return false;
            const style = getComputedStyle(node);
            const rect = node.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
          };
          const keys = [];
          for (const storage of [localStorage, sessionStorage]) {
            for (let i = 0; i < storage.length; i += 1) {
              const key = storage.key(i);
              if (key && storage.getItem(key)) keys.push(key);
            }
          }
          const priceLike = Array.from(document.querySelectorAll('[class*="price"], [data-price], [class*="amount"]'))
            .filter(visible).length;
          return {
            visible_password_input: Array.from(document.querySelectorAll('input[type="password"]')).some(visible),
            storage_keys: Array.from(new Set(keys)).slice(0, 200),
            price_like_count: priceLike
          };
        }"""
    )
    cookies = page.context.cookies([page.url])
    storage_keys = [str(item) for item in (evidence.get("storage_keys") or [])]
    cookie_names = [str(item.get("name") or "") for item in cookies]
    return {
        "visible_password_input": bool(evidence.get("visible_password_input")),
        "price_like_count": int(evidence.get("price_like_count") or 0),
        "auth_storage_keys": sorted({key for key in storage_keys if AUTH_KEY_PATTERN.search(key)})[:50],
        "auth_cookie_names": sorted({key for key in cookie_names if AUTH_KEY_PATTERN.search(key)})[:50],
    }

def _ugphone_purchase_error(text: str) -> str | None:
    lowered = str(text or "").lower()
    for marker, reason in UGPHONE_PURCHASE_ERROR_MARKERS.items():
        if marker in lowered:
            return reason
    return None


def _string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for key, item in value.items():
        key_text = str(key or "").strip()
        if not key_text or item is None:
            continue
        item_text = str(item)
        if len(key_text) > 200 or len(item_text) > 200_000:
            continue
        out[key_text] = item_text
    return out


def _attach_ugphone_request_capture(
    page: Page,
    captured: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], tuple[Any, Any]]:
    """Capture successful purchase API metadata from the *live* login context.

    The raw header values remain only in the private runtime artifact.  Response
    bodies are not retained here; only endpoint/status/business-code summaries
    are recorded so the login helper can prove that pricing initialised before
    it persists the profile.
    """
    captured = captured if isinstance(captured, dict) else {}
    captured.setdefault("headers", {})
    captured.setdefault("endpoints", [])
    captured.setdefault("responses", [])

    def is_purchase_url(value: str) -> bool:
        lowered = str(value or "").lower()
        return any(token in lowered for token in UGPHONE_API_TOKENS)

    def on_request(request) -> None:
        try:
            url = str(request.url or "")
            if not is_purchase_url(url):
                return
            try:
                raw_headers = request.all_headers()
            except Exception:
                raw_headers = request.headers
            normalized = {str(k).lower(): str(v) for k, v in (raw_headers or {}).items()}
            for key in UGPHONE_RUNTIME_HEADER_KEYS:
                value = normalized.get(key)
                if value:
                    captured["headers"][key] = value
            endpoint = url.split("?", 1)[0]
            if endpoint not in captured["endpoints"]:
                captured["endpoints"].append(endpoint)
        except Exception:
            return

    def on_response(response) -> None:
        try:
            url = str(response.url or "")
            if not is_purchase_url(url):
                return
            endpoint = url.split("?", 1)[0]
            code = None
            valid = False
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    code = payload.get("code")
                    data = payload.get("data")
                    if "configlist2" in endpoint.lower():
                        values = (data or {}).get("list") if isinstance(data, dict) else None
                        valid = isinstance(values, list) and len(values) > 0
                    elif "meallist" in endpoint.lower():
                        values = (data or {}).get("list") if isinstance(data, dict) else None
                        valid = isinstance(values, dict) and len(values) > 0
                    valid = bool(valid and code in (0, 200))
            except Exception:
                pass
            captured["responses"].append(
                {
                    "endpoint": endpoint,
                    "status": int(response.status or 0),
                    "code": code,
                    "valid": valid,
                }
            )
            captured["responses"] = captured["responses"][-50:]
        except Exception:
            return

    page.on("request", on_request)
    page.on("response", on_response)
    return captured, (on_request, on_response)

def _detach_request_capture(page: Page, handlers: Any) -> None:
    try:
        request_handler, response_handler = handlers
    except Exception:
        return
    for event_name, handler in (("request", request_handler), ("response", response_handler)):
        try:
            page.remove_listener(event_name, handler)
        except Exception:
            pass

def capture_ugphone_runtime_context(
    page: Page,
    request_capture: dict[str, Any] | None,
) -> dict[str, Any]:
    """Capture only the UgPhone state needed by the scheduled collector.

    Password caches and MQTT credentials are deliberately excluded.  The runtime
    file is still authentication-sensitive because it contains a short-lived
    token and must remain under ``output/auth``.
    """
    snapshot = page.evaluate(
        """() => {
          const dump = (storage) => {
            const out = {};
            for (let index = 0; index < storage.length; index += 1) {
              const key = storage.key(index);
              if (key !== null) out[key] = storage.getItem(key);
            }
            return out;
          };
          return {
            origin: location.origin,
            href: location.href,
            session_storage: dump(window.sessionStorage),
            local_storage: dump(window.localStorage),
            document_language: document.documentElement.lang || '',
            navigator_language: navigator.language || '',
            navigator_languages: Array.from(navigator.languages || []),
            user_agent: navigator.userAgent || ''
          };
        }"""
    )
    request_capture = request_capture or {}
    allowed_local_keys = {
        "UGPHONE-Token",
        "UGPHONE-ID",
        "UGPHONE-PUBLICKEY",
        "ugPhoneLang",
        "ugBrowserId",
        "hadAgreePolicy",
        "hasWalletGuide",
    }
    local_storage = {
        key: value
        for key, value in _string_map(snapshot.get("local_storage")).items()
        if key in allowed_local_keys
    }
    session_storage = {
        key: value
        for key, value in _string_map(snapshot.get("session_storage")).items()
        if not any(token in key.lower() for token in ("password", "passwd", "loginparam", "mqtt", "secret", "credential"))
    }
    response_summary = [
        {
            "endpoint": str(item.get("endpoint") or ""),
            "status": int(item.get("status") or 0),
            "code": item.get("code"),
            "valid": bool(item.get("valid")),
        }
        for item in (request_capture.get("responses") or [])
        if isinstance(item, dict)
    ][-50:]
    return {
        "schema_version": 2,
        "captured_at_utc": _now(),
        "origin": str(snapshot.get("origin") or "https://www.ugphone.com"),
        "captured_href": str(snapshot.get("href") or ""),
        "session_storage": session_storage,
        "local_storage": local_storage,
        "api_request_context": {
            "headers": _string_map(request_capture.get("headers")),
            "endpoints": [str(item) for item in (request_capture.get("endpoints") or []) if item][:20],
            "responses": response_summary,
        },
        "browser_context": {
            "document_language": str(snapshot.get("document_language") or ""),
            "navigator_language": str(snapshot.get("navigator_language") or ""),
            "navigator_languages": [str(item) for item in (snapshot.get("navigator_languages") or []) if item][:10],
            "user_agent": str(snapshot.get("user_agent") or ""),
        },
    }

def write_ugphone_runtime_context(path: Path, runtime_context: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(runtime_context, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def prepare_ugphone_login_view(page: Page) -> dict[str, Any]:
    """Make the manual-login controls usable in a headed desktop window."""
    result: dict[str, Any] = {
        "viewport": {},
        "document": {},
        "login_control_found": False,
        "login_control_text": None,
        "scrolled": False,
    }
    try:
        page.wait_for_timeout(2_500)
        result["viewport"] = page.evaluate(
            "() => ({width: window.innerWidth, height: window.innerHeight, dpr: window.devicePixelRatio})"
        )
        found = page.evaluate(
            """() => {
                const needles = [
                    '通过Google登录', '通过 Google 登录',
                    '通过Apple登录', '通过 Apple 登录',
                    '通过Facebook登录', '通过 Facebook 登录',
                    '手机号登录', 'Sign Up with Google', 'Sign Up with Apple',
                    'Sign Up with Facebook', 'Phone login',
                    'Login with Google', 'Login with Apple', 'Login with Facebook'
                ];
                const clean = (node) => (node.innerText || node.textContent || '').trim();
                const isUseful = (node) => {
                    const rect = node.getBoundingClientRect();
                    if (rect.width < 80 || rect.height < 22) return false;
                    const text = clean(node);
                    return needles.some((needle) => text.includes(needle));
                };
                let candidates = Array.from(document.querySelectorAll('button,a,[role=button]')).filter(isUseful);
                if (!candidates.length) {
                    candidates = Array.from(document.querySelectorAll('div,span')).filter((node) => {
                        if (!isUseful(node)) return false;
                        return !Array.from(node.children || []).some((child) => isUseful(child));
                    });
                }
                candidates.sort((a, b) => {
                    const ar = a.getBoundingClientRect();
                    const br = b.getBoundingClientRect();
                    return (ar.width * ar.height) - (br.width * br.height);
                });
                const target = candidates[0];
                const root = document.scrollingElement || document.documentElement;
                if (!target) {
                    return {found: false, text: null, scrollY: window.scrollY, scrollHeight: root.scrollHeight, clientHeight: root.clientHeight};
                }
                target.scrollIntoView({block: 'center', inline: 'nearest', behavior: 'instant'});
                return {found: true, text: clean(target), scrollY: window.scrollY, scrollHeight: root.scrollHeight, clientHeight: root.clientHeight};
            }"""
        )
        result["login_control_found"] = bool(found.get("found"))
        result["login_control_text"] = found.get("text")
        result["scrolled"] = bool(found.get("found"))
        result["document"] = {
            "scrollY": found.get("scrollY"),
            "scrollHeight": found.get("scrollHeight"),
            "clientHeight": found.get("clientHeight"),
        }
        page.wait_for_timeout(300)
    except Exception as exc:
        result["assist_error"] = f"{type(exc).__name__}: {exc}"
    return result


def _ugphone_capture_summary(capture: dict[str, Any] | None) -> dict[str, Any]:
    capture = capture or {}
    responses = [item for item in (capture.get("responses") or []) if isinstance(item, dict)]
    valid_endpoints = sorted(
        {
            str(item.get("endpoint") or "")
            for item in responses
            if item.get("valid")
        }
    )
    return {
        "header_keys": sorted((capture.get("headers") or {}).keys()),
        "endpoint_count": len(capture.get("endpoints") or []),
        "valid_endpoint_count": len(valid_endpoints),
        "valid_endpoints": valid_endpoints,
        "response_count": len(responses),
    }


def _ugphone_capture_has_required_price_api(capture: dict[str, Any] | None) -> bool:
    summary = _ugphone_capture_summary(capture)
    lowered = " ".join(summary.get("valid_endpoints") or []).lower()
    return all(token in lowered for token in UGPHONE_REQUIRED_API_TOKENS)


def _ugphone_subscription_control_count(page: Page) -> int:
    try:
        return int(page.evaluate(
            r"""
            () => {
              const visible = (node) => {
                if (!node) return false;
                const style = window.getComputedStyle(node);
                const rect = node.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
              };
              const text = (node) => String(node?.innerText || node?.textContent || '').replace(/\s+/g, ' ').trim();
              const matches = (value) => /subscribe|subscription|auto[\s-]*renew|自动续费|自動續費|订阅|訂閱/i.test(String(value || ''));
              const scope = document.body;
              const direct = [
                '.subscription [role="checkbox"]',
                '.purchase-footer [role="checkbox"]',
                '[role="checkbox"][aria-checked]',
                '[role="switch"]',
                'input[type="checkbox"]',
                '.van-checkbox',
                '.el-checkbox',
                '.checkbox',
                '.subscription',
                '.subscription-text',
                '[class*="subscribe"]',
                '[class*="renew"]'
              ].join(', ');
              return Array.from(scope.querySelectorAll(direct))
                .filter(visible)
                .filter((node) => {
                  if (node.matches?.('[role="checkbox"][aria-checked], [role="switch"], input[type="checkbox"]')) {
                    const nearby = node.closest?.('.subscription, .purchase-footer, label') || node.parentElement || node;
                    return matches(text(nearby)) || Boolean(node.closest?.('.subscription, .purchase-footer'));
                  }
                  return matches(text(node.closest?.('label') || node.parentElement || node));
                })
                .length;
            }
            """
        ))
    except Exception:
        return 0


def _ugphone_selector_counts(page: Page) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, selector in UGPHONE_BUSINESS_SELECTORS.items():
        try:
            counts[key] = int(page.locator(selector).count())
        except Exception:
            counts[key] = 0
    counts["subscription"] = _ugphone_subscription_control_count(page)
    return counts


def _ugphone_counts_complete(counts: dict[str, int]) -> bool:
    """Return whether the live page proves an authenticated purchase session.

    Subscription rendering is deliberately excluded: UgPhone omits that control
    for sold-out plan/region combinations even when the account is fully logged
    in and the rest of the purchase page is healthy.
    """
    return all(int(counts.get(key) or 0) >= expected for key, expected in UGPHONE_AUTH_MIN_COUNTS.items())


def verify_ugphone_purchase_page(
    page: Page,
    target_url: str,
    *,
    request_capture: dict[str, Any] | None = None,
    capture_already_attached: bool = False,
    force_navigation: bool = True,
    require_successful_price_api: bool = False,
) -> dict[str, Any]:
    """Verify UgPhone using authenticated purchase-page evidence.

    ``plan / region / price`` are the authentication gate.  The subscription
    control is only a SKU/inventory capability signal because sold-out selections
    omit it from the DOM.  The login helper keeps the request listener attached
    so it can also capture successful price API calls when requested.
    """
    verification: dict[str, Any] = {
        "target_url": target_url,
        "login_markers": [],
        "selector_counts": {},
        "minimum_selector_counts": dict(UGPHONE_AUTH_MIN_COUNTS),
        "diagnostic_selector_counts": {"subscription": UGPHONE_SUBSCRIPTION_DIAGNOSTIC_MIN},
        "warnings": [],
        "subscription_capability": "unknown",
        "url_after_navigation": "",
        "api_request_context": {},
        "purchase_error": None,
        "ok": False,
        "reason": None,
        "reload_attempted": False,
    }
    if capture_already_attached and isinstance(request_capture, dict):
        private_capture = request_capture
        handlers = None
    else:
        private_capture, handlers = _attach_ugphone_request_capture(page, request_capture)

    try:
        if force_navigation or not page.url.startswith(target_url):
            page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)

        for attempt in range(2):
            deadline = time.monotonic() + 35.0
            while time.monotonic() < deadline:
                text = _body_text(page)
                purchase_error = _ugphone_purchase_error(text)
                verification["purchase_error"] = purchase_error
                markers = [marker for marker in UGPHONE_LOGIN_MARKERS if marker in text]
                verification["login_markers"] = markers
                verification["selector_counts"] = _ugphone_selector_counts(page)
                if purchase_error:
                    verification["reason"] = purchase_error
                    return verification
                if markers:
                    verification["reason"] = "login_page_detected"
                    return verification
                if _ugphone_counts_complete(verification["selector_counts"]):
                    break
                page.wait_for_timeout(750)

            if _ugphone_counts_complete(verification["selector_counts"]):
                break
            if attempt == 0:
                verification["reload_attempted"] = True
                try:
                    page.reload(wait_until="domcontentloaded", timeout=45_000)
                except Exception:
                    pass

        verification["url_after_navigation"] = page.url
        final_text = _body_text(page)
        verification["purchase_error"] = _ugphone_purchase_error(final_text)
        if verification["purchase_error"]:
            verification["reason"] = verification["purchase_error"]
            return verification
        if verification["login_markers"]:
            verification["reason"] = "login_page_detected"
            return verification

        counts = verification["selector_counts"]
        if not _ugphone_counts_complete(counts):
            verification["reason"] = "purchase_business_selectors_incomplete"
            return verification

        if int(counts.get("subscription") or 0) < UGPHONE_SUBSCRIPTION_DIAGNOSTIC_MIN:
            verification["warnings"].append("subscription_missing_for_current_sku")
            verification["subscription_capability"] = "not_rendered_for_current_sku"
        else:
            verification["subscription_capability"] = "rendered_for_current_sku"

        if require_successful_price_api and not _ugphone_capture_has_required_price_api(private_capture):
            verification["reason"] = "purchase_price_api_not_observed"
            return verification

        verification["ok"] = True
        return verification
    except Exception as exc:
        verification["reason"] = f"navigation_failed: {type(exc).__name__}: {exc}"
        return verification
    finally:
        if handlers is not None:
            _detach_request_capture(page, handlers)
        verification["api_request_context"] = _ugphone_capture_summary(private_capture)

def verify_platform_session(
    page: Page,
    platform: str,
    target_url: str,
    *,
    request_capture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if platform == "UgPhone":
        return verify_ugphone_purchase_page(page, target_url, request_capture=request_capture)

    try:
        page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(3_000)
        result = _assess_generic_session_evidence(
            platform,
            page.url,
            _body_text(page),
            _generic_browser_evidence(page),
        )
        result["target_url"] = target_url
        return result
    except Exception as exc:
        return {
            "target_url": target_url,
            "ok": False,
            "reason": f"navigation_failed: {type(exc).__name__}: {exc}",
        }


def _default_ugphone_profile(save_state_path: Path) -> Path:
    return save_state_path.parent / "ugphone_profile"


def _run_login_session(
    *,
    platform: str,
    target_url: str,
    entry_url: str,
    storage_state: Path | None,
    persistent_profile: Path | None,
    signal_file: Path,
    status: dict[str, Any],
    status_file: Path,
    save_storage_state: Path,
    runtime_context_path: Path | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Open a visible login browser and capture the *real* purchase API context.

    The capture starts before the user logs in. UgPhone can initialise its
    price API immediately after the login redirect; attaching only after the
    user presses Enter loses the diagnostic evidence needed to distinguish a
    real price response from a page-level error.
    """

    def complete_in_context(context) -> tuple[dict[str, Any], dict[str, Any] | None]:
        page = context.new_page()
        live_capture: dict[str, Any] = {}
        handlers: Any = None
        if platform == "UgPhone":
            live_capture, handlers = _attach_ugphone_request_capture(page, live_capture)
        try:
            page.goto(entry_url, wait_until="domcontentloaded", timeout=45_000)
            if platform == "UgPhone":
                status["login_display_assist"] = prepare_ugphone_login_view(page)
            status["status"] = "waiting_for_user_signal"
            status["opened_at_utc"] = _now()
            write_status(status_file, status)

            while True:
                if signal_file.exists():
                    try:
                        if signal_file.read_text(encoding="utf-8").strip() == str(status["session_id"]):
                            break
                    except OSError:
                        pass
                page.wait_for_timeout(1_000)

            if platform == "UgPhone":
                verification = verify_ugphone_purchase_page(
                    page,
                    target_url,
                    request_capture=live_capture,
                    capture_already_attached=True,
                    force_navigation=True,
                    require_successful_price_api=True,
                )
            else:
                verification = verify_platform_session(page, platform, target_url)

            runtime_context: dict[str, Any] | None = None
            if verification.get("ok"):
                save_storage_state.parent.mkdir(parents=True, exist_ok=True)
                temporary_state = save_storage_state.with_name(save_storage_state.name + ".tmp")
                context.storage_state(path=str(temporary_state))
                temporary_state.replace(save_storage_state)
                if platform == "UgPhone" and runtime_context_path is not None:
                    runtime_context = capture_ugphone_runtime_context(page, live_capture)
                    write_ugphone_runtime_context(runtime_context_path, runtime_context)
            return verification, runtime_context
        finally:
            if handlers is not None:
                _detach_request_capture(page, handlers)

    if persistent_profile is not None:
        with launch_persistent_browser(persistent_profile, headless=False, interactive_login=True) as (_, context):
            status["auth_mode"] = "persistent_profile"
            status["persistent_profile"] = str(persistent_profile)
            return complete_in_context(context)

    with launch_browser(headless=False, storage_state=storage_state) as (_, _, context):
        status["auth_mode"] = "storage_state"
        return complete_in_context(context)

def _reopen_and_verify_persistent_profile(
    platform: str,
    target_url: str,
    profile: Path,
    runtime_context_path: Path | None,
    *,
    headless: bool,
) -> dict[str, Any]:
    """Verify the saved profile in headed and scheduled-task (headless) modes."""
    runtime_context = load_ugphone_runtime_context(runtime_context_path)
    with launch_persistent_browser(
        profile,
        headless=headless,
        ugphone_runtime_context=runtime_context if platform == "UgPhone" else None,
    ) as (_, context):
        page = context.new_page()
        live_capture: dict[str, Any] = {}
        handlers: Any = None
        if platform == "UgPhone":
            live_capture, handlers = _attach_ugphone_request_capture(page, live_capture)
        try:
            if platform == "UgPhone":
                verification = verify_ugphone_purchase_page(
                    page,
                    target_url,
                    request_capture=live_capture,
                    capture_already_attached=True,
                    force_navigation=True,
                    require_successful_price_api=True,
                )
            else:
                verification = verify_platform_session(page, platform, target_url)
            verification["runtime_context_loaded"] = bool(runtime_context)
            verification["runtime_context"] = runtime_context_summary(runtime_context)
            verification["browser_mode"] = "headless" if headless else "headed"
            return verification
        finally:
            if handlers is not None:
                _detach_request_capture(page, handlers)

def main() -> None:
    parser = argparse.ArgumentParser(description="Open a platform login page and wait for a local signal file.")
    parser.add_argument("--platform", required=True, choices=["VSPhone", "Redfinger", "LDCloud", "UgPhone"])
    parser.add_argument("--storage-state", default=None)
    parser.add_argument("--save-storage-state", required=True)
    parser.add_argument("--persistent-profile", default=None)
    parser.add_argument(
        "--entry-url",
        default=None,
        help="Visible browser entry page used for manual login. Purchase page remains verification-only.",
    )
    parser.add_argument("--signal-file", required=True)
    parser.add_argument("--status-file", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--runtime-context", default=None, help="Private local UgPhone session/runtime snapshot path.")
    args = parser.parse_args()

    config = MonitorConfig.default()
    target = config.targets[args.platform]
    entry_url = args.entry_url or (UGPHONE_LOGIN_ENTRY_URL if args.platform == "UgPhone" else target.url)
    storage_state = Path(args.storage_state) if args.storage_state else None
    save_storage_state = Path(args.save_storage_state)
    persistent_profile = Path(args.persistent_profile) if args.persistent_profile else None
    if args.platform == "UgPhone" and persistent_profile is None:
        persistent_profile = _default_ugphone_profile(save_storage_state)
    runtime_context_path = (
        Path(args.runtime_context)
        if args.runtime_context
        else default_ugphone_runtime_context_path(save_storage_state.parent)
    ) if args.platform == "UgPhone" else None
    signal_file = Path(args.signal_file)
    status_file = Path(args.status_file)

    signal_file.parent.mkdir(parents=True, exist_ok=True)
    if signal_file.exists():
        signal_file.unlink()

    status: dict[str, Any] = {
        "schema_version": 2,
        "session_id": args.session_id,
        "platform": args.platform,
        "target_url": target.url,
        "entry_url": entry_url,
        "status": "starting",
        "started_at_utc": _now(),
        "signal_file": str(signal_file),
        "save_storage_state": str(save_storage_state),
        "persistent_profile": str(persistent_profile) if persistent_profile else None,
        "runtime_context_path": str(runtime_context_path) if runtime_context_path else None,
    }
    write_status(status_file, status)

    try:
        verification, runtime_context = _run_login_session(
            platform=args.platform,
            target_url=target.url,
            entry_url=entry_url,
            storage_state=storage_state,
            persistent_profile=persistent_profile,
            signal_file=signal_file,
            status=status,
            status_file=status_file,
            save_storage_state=save_storage_state,
            runtime_context_path=runtime_context_path,
        )
        status["verification_before_save"] = verification
        if runtime_context is not None:
            status["runtime_context_capture"] = runtime_context_summary(runtime_context)
        if not verification.get("ok"):
            status["status"] = "verification_failed"
            status["failed_at_utc"] = _now()
            write_status(status_file, status)
            raise RuntimeError(
                f"{args.platform} login was not persisted in the opened browser context: "
                f"{verification.get('reason')}"
            )

        if persistent_profile is not None:
            # Run a headed reopening first.  It separates an incomplete profile
            # from a page that specifically rejects headless browser execution.
            headed_reopen = _reopen_and_verify_persistent_profile(
                args.platform,
                target.url,
                persistent_profile,
                runtime_context_path,
                headless=False,
            )
            status["verification_after_reopen_headed"] = headed_reopen

            task_reopen = _reopen_and_verify_persistent_profile(
                args.platform,
                target.url,
                persistent_profile,
                runtime_context_path,
                headless=True,
            )
            status["verification_after_reopen_task_equivalent"] = task_reopen
            if not task_reopen.get("ok"):
                status["status"] = "verification_failed_after_reopen"
                if headed_reopen.get("ok") and not task_reopen.get("ok"):
                    status["failure_classification"] = "headless_runtime_incompatible"
                else:
                    status["failure_classification"] = "profile_or_runtime_context_incomplete"
                status["failed_at_utc"] = _now()
                write_status(status_file, status)
                raise RuntimeError(
                    f"{args.platform} persistent profile did not restore in the scheduled-task-equivalent context: "
                    f"{task_reopen.get('reason')}"
                )

        status["status"] = "saved_and_verified"
        status["saved_at_utc"] = _now()
        write_status(status_file, status)
    except PlaywrightError as exc:
        status["status"] = "failed"
        status["error"] = f"{type(exc).__name__}: {exc}"
        status["failed_at_utc"] = _now()
        write_status(status_file, status)
        raise
    except Exception as exc:
        if status.get("status") not in {"verification_failed", "verification_failed_after_reopen"}:
            status["status"] = "failed"
            status["error"] = f"{type(exc).__name__}: {exc}"
            status["failed_at_utc"] = _now()
            write_status(status_file, status)
        raise


if __name__ == "__main__":
    main()
