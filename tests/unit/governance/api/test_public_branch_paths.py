from __future__ import annotations

from inspect import unwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.governance.api.v1 import public


class _RowsResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


def _unwrap_discovery():
    return unwrap(public.discover_sso_federation)


@pytest.mark.asyncio
async def test_normalize_email_domain_handles_invalid_and_normalizes() -> None:
    assert public._normalize_email_domain("not-an-email") == ""
    assert public._normalize_email_domain(" User@Example.COM. ") == "example.com"


@pytest.mark.asyncio
async def test_discover_sso_federation_returns_invalid_email_domain_when_normalized_empty() -> None:
    endpoint = _unwrap_discovery()
    db = SimpleNamespace(execute=AsyncMock())

    with patch.object(public, "_normalize_email_domain", return_value=""):
        response = await endpoint(
            request=SimpleNamespace(),
            payload=SimpleNamespace(email="user@example.com"),
            _turnstile=None,
            db=db,
        )

    assert response.available is False
    assert response.reason == "invalid_email_domain"
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_discover_sso_federation_returns_not_configured_when_no_rows() -> None:
    endpoint = _unwrap_discovery()
    db = SimpleNamespace(execute=AsyncMock(return_value=_RowsResult([])))

    response = await endpoint(
        request=SimpleNamespace(),
        payload=SimpleNamespace(email="user@example.com"),
        _turnstile=None,
        db=db,
    )

    assert response.available is False
    assert response.reason == "sso_not_configured_for_domain"


@pytest.mark.asyncio
async def test_discover_sso_federation_returns_ambiguous_mapping_when_multiple_rows() -> None:
    endpoint = _unwrap_discovery()
    rows = [
        (SimpleNamespace(federation_mode="domain", provider_id=None), "pro"),
        (SimpleNamespace(federation_mode="domain", provider_id=None), "pro"),
    ]
    db = SimpleNamespace(execute=AsyncMock(return_value=_RowsResult(rows)))

    response = await endpoint(
        request=SimpleNamespace(),
        payload=SimpleNamespace(email="user@example.com"),
        _turnstile=None,
        db=db,
    )

    assert response.available is False
    assert response.reason == "ambiguous_tenant_domain_mapping"


@pytest.mark.asyncio
async def test_discover_sso_federation_single_row_tier_ineligible() -> None:
    endpoint = _unwrap_discovery()
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=_RowsResult(
                [(SimpleNamespace(federation_mode="domain", provider_id=None), "starter")]
            )
        )
    )

    with patch.object(public, "normalize_tier", return_value=public.PricingTier.STARTER):
        response = await endpoint(
            request=SimpleNamespace(),
            payload=SimpleNamespace(email="user@example.com"),
            _turnstile=None,
            db=db,
        )

    assert response.available is False
    assert response.reason == "tier_not_eligible_for_sso_federation"


@pytest.mark.asyncio
async def test_discover_sso_federation_single_row_provider_id_missing_and_success() -> None:
    endpoint = _unwrap_discovery()

    with patch.object(public, "normalize_tier", return_value=public.PricingTier.ENTERPRISE):
        missing_db = SimpleNamespace(
            execute=AsyncMock(
                return_value=_RowsResult(
                    [
                        (
                            SimpleNamespace(
                                federation_mode="provider_id",
                                provider_id="   ",
                            ),
                            "enterprise",
                        )
                    ]
                )
            )
        )
        missing_response = await endpoint(
            request=SimpleNamespace(),
            payload=SimpleNamespace(email="user@example.com"),
            _turnstile=None,
            db=missing_db,
        )
        assert missing_response.available is False
        assert missing_response.reason == "sso_provider_id_not_configured"

        success_db = SimpleNamespace(
            execute=AsyncMock(
                return_value=_RowsResult(
                    [
                        (
                            SimpleNamespace(
                                federation_mode="provider_id",
                                provider_id="sso-provider-123",
                            ),
                            "enterprise",
                        )
                    ]
                )
            )
        )
        success_response = await endpoint(
            request=SimpleNamespace(),
            payload=SimpleNamespace(email="user@example.com"),
            _turnstile=None,
            db=success_db,
        )

    assert success_response.available is True
    assert success_response.mode == "provider_id"
    assert success_response.provider_id == "sso-provider-123"


@pytest.mark.asyncio
async def test_discover_sso_federation_single_row_invalid_mode_falls_back_to_domain() -> None:
    endpoint = _unwrap_discovery()
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=_RowsResult(
                [
                    (
                        SimpleNamespace(federation_mode="invalid-mode", provider_id=None),
                        "pro",
                    )
                ]
            )
        )
    )

    with patch.object(public, "normalize_tier", return_value=public.PricingTier.PRO):
        response = await endpoint(
            request=SimpleNamespace(),
            payload=SimpleNamespace(email="user@example.com"),
            _turnstile=None,
            db=db,
        )

    assert response.available is True
    assert response.mode == "domain"
    assert response.domain == "example.com"

