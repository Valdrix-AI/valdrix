from __future__ import annotations

import pytest

from scripts import emergency_token


def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("VALDRICS_EMERGENCY_TOKEN_ENABLED", "true")
    monkeypatch.setenv("VALDRICS_ALLOW_NONINTERACTIVE_EMERGENCY_TOKEN", "true")


def test_validate_request_rejects_missing_operator(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)

    with pytest.raises(RuntimeError, match="operator"):
        emergency_token._validate_request(
            email="owner@example.com",
            force=True,
            phrase="VALDRICS_BREAK_GLASS",
            ttl_hours=1,
            operator="",
            reason="Need to recover platform access after SSO outage.",
            confirm_environment="development",
            no_prompt=True,
        )


def test_validate_request_rejects_short_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)

    with pytest.raises(RuntimeError, match="at least"):
        emergency_token._validate_request(
            email="owner@example.com",
            force=True,
            phrase="VALDRICS_BREAK_GLASS",
            ttl_hours=1,
            operator="ops-admin",
            reason="too short",
            confirm_environment="development",
            no_prompt=True,
        )


def test_validate_request_rejects_protected_env_without_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("VALDRICS_ALLOW_PROD_EMERGENCY_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="protected environment"):
        emergency_token._validate_request(
            email="owner@example.com",
            force=True,
            phrase="VALDRICS_BREAK_GLASS",
            ttl_hours=1,
            operator="ops-admin",
            reason="Need to recover platform access after SSO outage.",
            confirm_environment="production",
            no_prompt=True,
        )


def test_validate_request_accepts_explicit_break_glass(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)

    emergency_token._validate_request(
        email="owner@example.com",
        force=True,
        phrase="VALDRICS_BREAK_GLASS",
        ttl_hours=1,
        operator="ops-admin",
        reason="Need to recover platform access after SSO outage.",
        confirm_environment="development",
        no_prompt=True,
    )


@pytest.mark.parametrize("role", ["member", "viewer", ""])
def test_validate_target_role_rejects_non_admin_targets(role: str) -> None:
    with pytest.raises(RuntimeError, match="owner/admin"):
        emergency_token._validate_target_role(role)


@pytest.mark.parametrize("role", ["owner", "admin", "ADMIN", " Owner "])
def test_validate_target_role_accepts_privileged_targets(role: str) -> None:
    emergency_token._validate_target_role(role)
