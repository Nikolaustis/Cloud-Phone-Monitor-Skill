from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Iterable

LOGIN_PROTOCOL_VERSION = 4
AUTH_CONTRACT_SCHEMA_VERSION = 4
AUTH_KEY_RE = re.compile(r"(?:token|auth|session|jwt|access.?token|refresh.?token|uid|user.?id|user.?info)", re.I)
PRICE_RE = re.compile(
    r"(?:US\$|USD|\$|R\$|BRL|THB|IDR|PHP|VND|RM|JPY|CNY|¥|￥|₫)\s*[0-9]"
    r"|[0-9]+(?:\.[0-9]{1,2})?\s*(?:/\s*)?(?:day|days|month|months|year|years)\b",
    re.I,
)
STRONG_VISIBLE_AUTH_MARKERS = (
    "logout", "log out", "sign out", "退出登录", "退出登入", "登出",
)
WEAK_VISIBLE_ACCOUNT_MARKERS = (
    "my account", "account center", "user center", "member center", "个人中心", "會員中心", "会员中心",
)

PLATFORM_PROFILES: dict[str, dict[str, Any]] = {
    "VSPhone": {
        "login_url_tokens": ("/login", "/signin", "#/login", "sign-in"),
        "business_markers": ("auto renew", "automatic renewal", "high-end real", "game afk", "android"),
        "minimum_price_tokens": 1,
    },
    "Redfinger": {
        "login_url_tokens": ("/login", "/signin", "#/login", "sign-in"),
        "business_markers": ("redfinger", "cloud phone", "android", "buy"),
        "minimum_price_tokens": 1,
    },
    "LDCloud": {
        "login_url_tokens": ("/login", "/signin", "#/login", "sign-in"),
        "business_markers": ("ldcloud", "cloud phone", "android", "buy"),
        "minimum_price_tokens": 1,
    },
}


def normalize_session_id(value: str) -> str:
    """Return a canonical UUID string or raise ValueError."""
    return str(uuid.UUID(str(value or "").strip()))


def signal_matches_session(path: Path, session_id: str) -> bool:
    if not path.exists():
        return False
    try:
        expected = normalize_session_id(session_id)
        actual = normalize_session_id(path.read_text(encoding="utf-8-sig").strip())
        return actual == expected
    except Exception:
        return False


def auth_key_names(keys: Iterable[str]) -> list[str]:
    out: set[str] = set()
    for key in keys:
        normalized = str(key or "").strip()
        if normalized and AUTH_KEY_RE.search(normalized):
            out.add(normalized[:160])
    return sorted(out)[:50]


def _evaluate_platform_profile(
    *,
    platform: str,
    url: str,
    body_text: str,
    local_keys: Iterable[str],
    session_keys: Iterable[str],
    cookie_names: Iterable[str],
    authenticated_api_endpoints: Iterable[str],
    visible_password_inputs: int,
) -> dict[str, Any]:
    profile = PLATFORM_PROFILES.get(platform)
    if not profile:
        return {
            "schema_version": AUTH_CONTRACT_SCHEMA_VERSION,
            "platform": platform,
            "ok": False,
            "reason": "unsupported_platform_auth_verifier",
        }

    body = str(body_text or "")
    lowered = body.lower()
    local_auth_keys = auth_key_names(local_keys)
    session_auth_keys = auth_key_names(session_keys)
    auth_cookie_names = auth_key_names(cookie_names)
    credential_evidence_count = len(local_auth_keys) + len(session_auth_keys) + len(auth_cookie_names)

    strong_visible_auth_markers = [marker for marker in STRONG_VISIBLE_AUTH_MARKERS if marker in lowered]
    weak_visible_account_markers = [marker for marker in WEAK_VISIBLE_ACCOUNT_MARKERS if marker in lowered]
    authenticated_api_endpoints = sorted({str(x) for x in authenticated_api_endpoints if str(x).strip()})[:30]

    business_markers = [marker for marker in profile["business_markers"] if marker in lowered]
    price_token_count = len(PRICE_RE.findall(body))
    minimum_price_tokens = int(profile.get("minimum_price_tokens") or 1)
    business_ok = bool(business_markers and price_token_count >= minimum_price_tokens)

    strong_server_auth_count = len(strong_visible_auth_markers) + len(authenticated_api_endpoints)
    weak_server_auth_with_credentials = bool(weak_visible_account_markers and credential_evidence_count > 0)
    server_authenticated = bool(strong_server_auth_count > 0 or weak_server_auth_with_credentials)

    url_lower = str(url or "").lower()
    login_url_detected = any(token in url_lower for token in profile["login_url_tokens"])
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
        "schema_version": AUTH_CONTRACT_SCHEMA_VERSION,
        "verifier": f"verify_{platform.lower()}_auth",
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
        "minimum_price_tokens": minimum_price_tokens,
        "visible_password_inputs": int(visible_password_inputs or 0),
        "login_url_detected": login_url_detected,
        "business_evidence_ok": business_ok,
        "login_wall_detected": login_wall_detected,
        "ok": ok,
        "reason": reason,
    }


def verify_vsphone_auth(**kwargs: Any) -> dict[str, Any]:
    return _evaluate_platform_profile(platform="VSPhone", **kwargs)


def verify_redfinger_auth(**kwargs: Any) -> dict[str, Any]:
    return _evaluate_platform_profile(platform="Redfinger", **kwargs)


def verify_ldcloud_auth(**kwargs: Any) -> dict[str, Any]:
    return _evaluate_platform_profile(platform="LDCloud", **kwargs)


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
    common = {
        "url": url,
        "body_text": body_text,
        "local_keys": local_keys,
        "session_keys": session_keys,
        "cookie_names": cookie_names,
        "authenticated_api_endpoints": authenticated_api_endpoints,
        "visible_password_inputs": visible_password_inputs,
    }
    if platform == "VSPhone":
        return verify_vsphone_auth(**common)
    if platform == "Redfinger":
        return verify_redfinger_auth(**common)
    if platform == "LDCloud":
        return verify_ldcloud_auth(**common)
    return {
        "schema_version": AUTH_CONTRACT_SCHEMA_VERSION,
        "platform": platform,
        "ok": False,
        "reason": "unsupported_platform_auth_verifier",
    }
