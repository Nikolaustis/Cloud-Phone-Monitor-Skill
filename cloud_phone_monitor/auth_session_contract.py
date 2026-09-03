from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

AUTH_KEY_RE = re.compile(r"(?:token|auth|session|jwt|access.?token|refresh.?token|uid|user.?id|user.?info)", re.I)
PRICE_RE = re.compile(
    r"(?:US\$|USD|\$|R\$|BRL|THB|IDR|PHP|VND|RM|JPY|CNY|¥|￥|₫)\s*[0-9]"
    r"|[0-9]+(?:\.[0-9]{1,2})?\s*(?:/\s*)?(?:day|days|month|months|year|years)\b",
    re.I,
)
STRONG_VISIBLE_AUTH_MARKERS = (
    "logout",
    "log out",
    "sign out",
    "退出登录",
    "登出",
)
WEAK_VISIBLE_ACCOUNT_MARKERS = (
    "my account",
    "account center",
    "user center",
    "个人中心",
)
PLATFORM_BUSINESS_MARKERS = {
    "VSPhone": ("auto renew", "automatic renewal", "high-end real", "game afk", "android"),
    "Redfinger": ("redfinger", "cloud phone", "android"),
    "LDCloud": ("ldcloud", "cloud phone", "android"),
}


def signal_matches_session(path: Path, session_id: str) -> bool:
    if not path.exists():
        return False
    try:
        return path.read_text(encoding="utf-8-sig").strip() == str(session_id).strip()
    except Exception:
        return False


def auth_key_names(keys: Iterable[str]) -> list[str]:
    out: set[str] = set()
    for key in keys:
        normalized = str(key or "").strip()
        if normalized and AUTH_KEY_RE.search(normalized):
            out.add(normalized[:160])
    return sorted(out)[:50]


def evaluate_auth_evidence(
    *,
    platform: str,
    url: str,
    body_text: str,
    local_keys: Iterable[str] = (),
    session_keys: Iterable[str] = (),
    cookie_names: Iterable[str] = (),
    authenticated_api_endpoints: Iterable[str] = (),
    visible_password_inputs: int = 0,
) -> dict[str, Any]:
    body = str(body_text or "")
    lowered = body.lower()
    local_auth_keys = auth_key_names(local_keys)
    session_auth_keys = auth_key_names(session_keys)
    auth_cookie_names = auth_key_names(cookie_names)
    credential_evidence_count = len(local_auth_keys) + len(session_auth_keys) + len(auth_cookie_names)

    strong_visible_auth_markers = [marker for marker in STRONG_VISIBLE_AUTH_MARKERS if marker in lowered]
    weak_visible_account_markers = [marker for marker in WEAK_VISIBLE_ACCOUNT_MARKERS if marker in lowered]
    authenticated_api_endpoints = sorted({str(x) for x in authenticated_api_endpoints if str(x).strip()})[:30]

    business_markers = [marker for marker in PLATFORM_BUSINESS_MARKERS.get(platform, ()) if marker in lowered]
    price_token_count = len(PRICE_RE.findall(body))
    business_ok = bool(business_markers and price_token_count > 0)

    strong_server_auth_count = len(strong_visible_auth_markers) + len(authenticated_api_endpoints)
    weak_server_auth_with_credentials = bool(weak_visible_account_markers and credential_evidence_count > 0)
    server_authenticated = bool(strong_server_auth_count > 0 or weak_server_auth_with_credentials)

    url_lower = str(url or "").lower()
    login_url_detected = any(token in url_lower for token in ("/login", "/signin", "#/login", "sign-in"))
    login_wall_detected = bool((login_url_detected or int(visible_password_inputs or 0) > 0) and not server_authenticated)
    ok = bool(server_authenticated and business_ok and not login_wall_detected)

    reason = None
    if not ok:
        if login_wall_detected:
            reason = "login_wall_detected"
        elif not server_authenticated:
            reason = "no_server_acknowledged_auth_evidence"
        elif not business_ok:
            reason = "authenticated_business_evidence_missing"
        else:
            reason = "saved_auth_verification_failed"

    return {
        "platform": platform,
        "url_after_navigation": url,
        "local_auth_keys": local_auth_keys,
        "session_auth_keys": session_auth_keys,
        "auth_cookie_names": auth_cookie_names,
        "credential_evidence_count": credential_evidence_count,
        "strong_visible_auth_markers": strong_visible_auth_markers,
        "weak_visible_account_markers": weak_visible_account_markers,
        "authenticated_api_endpoints": authenticated_api_endpoints,
        "strong_server_auth_count": strong_server_auth_count,
        "weak_server_auth_with_credentials": weak_server_auth_with_credentials,
        "server_authenticated": server_authenticated,
        "business_markers": business_markers,
        "price_token_count": price_token_count,
        "visible_password_inputs": int(visible_password_inputs or 0),
        "login_url_detected": login_url_detected,
        "business_evidence_ok": business_ok,
        "login_wall_detected": login_wall_detected,
        "ok": ok,
        "reason": reason,
    }
