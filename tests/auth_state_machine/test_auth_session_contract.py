from pathlib import Path

from cloud_phone_monitor.auth_session_contract import evaluate_auth_evidence, signal_matches_session


def test_signal_requires_exact_session_id(tmp_path: Path) -> None:
    signal = tmp_path / "login.signal"
    assert not signal_matches_session(signal, "session-a")
    signal.write_text("session-old", encoding="utf-8")
    assert not signal_matches_session(signal, "session-a")
    signal.write_text("session-a\n", encoding="utf-8")
    assert signal_matches_session(signal, "session-a")


def test_non_ugphone_verification_accepts_server_acknowledged_account_plus_business() -> None:
    result = evaluate_auth_evidence(
        platform="VSPhone",
        url="https://cloud.vsphone.com/buy",
        body_text="User Center High-end Real Machine Android 15 Auto Renew US$ 9.99",
        local_keys=["accessToken"],
    )
    assert result["ok"] is True
    assert result["credential_evidence_count"] >= 1
    assert result["weak_server_auth_with_credentials"] is True
    assert result["business_evidence_ok"] is True


def test_authenticated_api_response_can_supply_server_acknowledgement() -> None:
    result = evaluate_auth_evidence(
        platform="Redfinger",
        url="https://www.cloudemulator.net/app/buy",
        body_text="Redfinger Cloud Phone Android US$ 10.00",
        authenticated_api_endpoints=["https://example.invalid/api/user/profile"],
    )
    assert result["ok"] is True
    assert result["server_authenticated"] is True


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
    result = evaluate_auth_evidence(
        platform="LDCloud",
        url="https://www.ldcloud.net/login",
        body_text="LDCloud Cloud Phone US$ 5.00 Sign in",
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
