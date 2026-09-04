from pathlib import Path

from cloud_phone_monitor.auth_session_contract import (
    evaluate_auth_evidence,
    normalize_session_id,
    signal_matches_session,
    verify_ldcloud_auth,
    verify_redfinger_auth,
    verify_vsphone_auth,
)


def test_signal_requires_exact_session_id(tmp_path: Path) -> None:
    signal = tmp_path / "login.signal"
    active = "123e4567-e89b-12d3-a456-426614174000"
    stale = "123e4567-e89b-12d3-a456-426614174001"
    assert not signal_matches_session(signal, active)
    signal.write_text(stale, encoding="utf-8")
    assert not signal_matches_session(signal, active)
    signal.write_text(active + "\n", encoding="utf-8")
    assert signal_matches_session(signal, active)
    signal.write_text("not-a-uuid", encoding="utf-8")
    assert not signal_matches_session(signal, active)


def test_vsphone_verifier_accepts_server_acknowledged_account_plus_business() -> None:
    result = verify_vsphone_auth(
        url="https://cloud.vsphone.com/buy",
        body_text="User Center High-end Real Machine Android 15 Auto Renew US$ 9.99",
        local_keys=["accessToken"],
        session_keys=[],
        cookie_names=[],
        authenticated_api_endpoints=[],
        visible_password_inputs=0,
    )
    assert result["ok"] is True
    assert result["verifier"] == "verify_vsphone_auth"
    assert result["business_evidence_ok"] is True


def test_redfinger_authenticated_api_response_can_supply_server_acknowledgement() -> None:
    result = verify_redfinger_auth(
        url="https://www.cloudemulator.net/app/buy",
        body_text="Redfinger Cloud Phone Android US$ 10.00",
        local_keys=[],
        session_keys=[],
        cookie_names=[],
        authenticated_api_endpoints=["https://example.invalid/api/user/profile"],
        visible_password_inputs=0,
    )
    assert result["ok"] is True
    assert result["server_authenticated"] is True
    assert result["verifier"] == "verify_redfinger_auth"


def test_token_only_on_public_business_page_is_not_verified() -> None:
    result = evaluate_auth_evidence(
        platform="Redfinger",
        url="https://www.cloudemulator.net/app/buy",
        body_text="Redfinger Cloud Phone Android US$ 10.00",
        local_keys=["accessToken"],
    )
    assert result["ok"] is False
    assert result["reason"] == "no_server_acknowledged_auth_evidence"


def test_login_wall_is_not_verified() -> None:
    result = verify_ldcloud_auth(
        url="https://www.ldcloud.net/login",
        body_text="LDCloud Cloud Phone US$ 5.00 Sign in",
        local_keys=[],
        session_keys=[],
        cookie_names=[],
        authenticated_api_endpoints=[],
        visible_password_inputs=1,
    )
    assert result["ok"] is False
    assert result["reason"] == "login_wall_detected"


def test_server_authenticated_without_business_evidence_is_not_verified() -> None:
    result = evaluate_auth_evidence(
        platform="LDCloud",
        url="https://www.ldcloud.net/web/mobile/buy",
        body_text="Logout Welcome back",
    )
    assert result["ok"] is False
    assert result["reason"] == "authenticated_business_evidence_missing"


def test_session_id_requires_uuid() -> None:
    value = "123E4567-E89B-12D3-A456-426614174000"
    assert normalize_session_id(value) == "123e4567-e89b-12d3-a456-426614174000"
    try:
        normalize_session_id("session-a")
    except ValueError:
        pass
    else:
        raise AssertionError("non-UUID session ids must be rejected")
