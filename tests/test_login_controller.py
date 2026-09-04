from __future__ import annotations

from cloud_phone_monitor.login_wait_for_signal import _assess_generic_session_evidence


def test_generic_login_verification_rejects_login_page() -> None:
    result = _assess_generic_session_evidence(
        "VSPhone",
        "https://cloud.vsphone.com/login",
        "Login with Google Cloud Phone $9.99",
        {
            "visible_password_input": True,
            "auth_storage_keys": ["accessToken"],
            "auth_cookie_names": [],
            "price_like_count": 1,
        },
    )
    assert result["ok"] is False
    assert result["reason"] == "login_page_detected"


def test_generic_login_verification_requires_auth_evidence() -> None:
    result = _assess_generic_session_evidence(
        "Redfinger",
        "https://www.cloudemulator.net/app/buy",
        "Cloud Phone VIP KVIP",
        {
            "visible_password_input": False,
            "auth_storage_keys": [],
            "auth_cookie_names": [],
            "price_like_count": 4,
        },
    )
    assert result["ok"] is False
    assert result["reason"] == "authenticated_session_evidence_missing"


def test_generic_login_verification_requires_business_evidence() -> None:
    result = _assess_generic_session_evidence(
        "LDCloud",
        "https://www.ldcloud.net/web/mobile/buy",
        "My account",
        {
            "visible_password_input": False,
            "auth_storage_keys": ["access_token"],
            "auth_cookie_names": [],
            "price_like_count": 0,
        },
    )
    assert result["ok"] is False
    assert result["reason"] == "purchase_business_evidence_missing"


def test_generic_login_verification_accepts_auth_and_business_evidence() -> None:
    result = _assess_generic_session_evidence(
        "LDCloud",
        "https://www.ldcloud.net/web/mobile/buy",
        "My account Cloud Phone VIP",
        {
            "visible_password_input": False,
            "auth_storage_keys": ["accessToken"],
            "auth_cookie_names": ["session_id"],
            "price_like_count": 3,
        },
    )
    assert result["ok"] is True
    assert result["reason"] is None
