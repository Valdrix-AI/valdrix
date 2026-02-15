import pytest

from app.shared.core.evidence_capture import redact_secrets, sanitize_bearer_token


def test_redact_secrets_redacts_common_sensitive_keys():
    payload = {
        "ok": True,
        "api_key": "sk_test_should_not_leak",
        "nested": {
            "token": "abc123",
            "client_secret": "shhh",
            "non_sensitive": "value",
            "list": [
                {"refresh_token": "rt-1"},
                {"password": "p@ss"},
                {"name": "safe"},
            ],
        },
    }

    redacted = redact_secrets(payload)
    assert redacted["ok"] is True
    assert redacted["api_key"] == "***REDACTED***"
    assert redacted["nested"]["token"] == "***REDACTED***"
    assert redacted["nested"]["client_secret"] == "***REDACTED***"
    assert redacted["nested"]["non_sensitive"] == "value"
    assert redacted["nested"]["list"][0]["refresh_token"] == "***REDACTED***"
    assert redacted["nested"]["list"][1]["password"] == "***REDACTED***"
    assert redacted["nested"]["list"][2]["name"] == "safe"


def test_sanitize_bearer_token_accepts_blank():
    assert sanitize_bearer_token("") == ""
    assert sanitize_bearer_token(None) == ""


def test_sanitize_bearer_token_accepts_plain_and_bearer_prefix():
    jwt = "abc.def.ghi"
    assert sanitize_bearer_token(jwt) == jwt
    assert sanitize_bearer_token(f"Bearer {jwt}") == jwt
    assert sanitize_bearer_token(f"bearer {jwt}") == jwt


def test_sanitize_bearer_token_extracts_last_jwt_from_noisy_multiline_value():
    jwt1 = "aaa.bbb.ccc"
    jwt2 = "xxx.yyy.zzz"
    noisy = f"2026-02-15 warning something\\n{jwt1}\\nmore logs\\nBearer {jwt2}"
    assert sanitize_bearer_token(noisy) == jwt2


def test_sanitize_bearer_token_rejects_non_jwt():
    with pytest.raises(ValueError):
        sanitize_bearer_token("not-a-jwt")
