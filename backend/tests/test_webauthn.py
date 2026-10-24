"""Unit tests for WebAuthn Biometric Face Lock flow."""

import pytest
from fastapi.testclient import TestClient
from eureka.api.main import app
from eureka.api.routers.webauthn_router import make_challenge_token, parse_challenge_token

client = TestClient(app)


def test_webauthn_register_options():
    """Verify registration options generation with challenge and RP parameters."""
    response = client.post(
        "/api/v1/auth/webauthn/register-options",
        json={"username": "dg_admin", "display_name": "DG Information Admin"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "options" in data
    assert "challenge_token" in data
    assert data["options"]["rp"]["id"] == "localhost"
    assert data["options"]["user"]["name"] == "dg_admin"
    assert "challenge" in data["options"]


def test_webauthn_login_options():
    """Verify login options generation with challenge."""
    response = client.post(
        "/api/v1/auth/webauthn/login-options",
        json={"username": "dg_admin"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "options" in data
    assert "challenge_token" in data
    assert data["options"]["rpId"] == "localhost"
    assert "challenge" in data["options"]


def test_challenge_token_security():
    """Verify challenge token cannot be reused across flows and detects tampering."""
    raw_challenge = b"test-random-challenge-bytes-32"
    user_id = "test_officer"

    token = make_challenge_token(raw_challenge, user_id, "registration")

    # Valid parsing
    ch, uid = parse_challenge_token(token, "registration")
    assert ch == raw_challenge
    assert uid == user_id

    # Flow mismatch should raise HTTPException 400
    with pytest.raises(Exception):
        parse_challenge_token(token, "authentication")

    # Tampered token should raise HTTPException 400
    with pytest.raises(Exception):
        parse_challenge_token(token + "tampered", "registration")


def test_webauthn_verify_login_rejects_unknown_credential():
    """Verify login fails safely when presented with unregistered credential."""
    # Obtain fresh login challenge
    opt_res = client.post(
        "/api/v1/auth/webauthn/login-options",
        json={"username": "dg_admin"},
    )
    challenge_token = opt_res.json()["challenge_token"]

    fake_credential = {
        "id": "unregistered-cred-id-abc123xyz",
        "rawId": "unregistered-cred-id-abc123xyz",
        "response": {
            "authenticatorData": "AAAA",
            "clientDataJSON": "AAAA",
            "signature": "AAAA",
        },
        "type": "public-key",
    }

    res = client.post(
        "/api/v1/auth/webauthn/verify-login",
        json={
            "credential": fake_credential,
            "challenge_token": challenge_token,
            "username": "dg_admin",
        },
    )
    assert res.status_code in (401, 404)


def test_webauthn_credentials_list():
    """Verify listing credentials for a user."""
    res = client.get("/api/v1/auth/webauthn/credentials?username=dg_admin")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "credentials" in data
    assert "total" in data
