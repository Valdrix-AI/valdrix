import pytest
from httpx import AsyncClient
from unittest.mock import MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from unittest.mock import AsyncMock
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta

from app.models.landing_telemetry_rollup import LandingTelemetryDailyRollup
from app.models.tenant import Tenant
from app.models.sso_domain_mapping import SsoDomainMapping


class _FatalTestSignal(BaseException):
    """Sentinel fatal error used to assert broad Exception handlers do not swallow BaseException."""


def _exception_group_contains(
    error: BaseException, exc_type: type[BaseException]
) -> bool:
    if isinstance(error, exc_type):
        return True
    if isinstance(error, BaseExceptionGroup):
        return any(
            _exception_group_contains(nested, exc_type) for nested in error.exceptions
        )
    return False


@pytest.mark.asyncio
async def test_get_csrf_token(async_client: AsyncClient):
    """GET /csrf should return a token and set a cookie."""
    response = await async_client.get("/api/v1/public/csrf")
    assert response.status_code == 200
    data = response.json()
    assert "csrf_token" in data
    # Check for fastapi-csrf-token cookie in headers
    cookie_header = response.headers.get("set-cookie", "")
    assert "fastapi-csrf-token" in cookie_header


@pytest.mark.asyncio
async def test_run_public_assessment(async_client: AsyncClient):
    """POST /assessment should trigger FreeAssessmentService."""
    mock_result = {"potential_savings": 250.0, "zombies_found": 12}

    with patch(
        "app.modules.governance.api.v1.public.assessment_service.run_assessment",
        return_value=mock_result,
    ):
        response = await async_client.post(
            "/api/v1/public/assessment", json={"aws_account_id": "123456789012"}
        )

    assert response.status_code == 200
    assert response.json() == mock_result


@pytest.mark.asyncio
async def test_run_public_assessment_validation_error(async_client: AsyncClient):
    """POST /assessment should return 400 on ValueError."""
    # Valdrics exception format: {"error": "...", "code": "VALUE_ERROR", "message": "..."}
    with patch(
        "app.modules.governance.api.v1.public.assessment_service.run_assessment",
        side_effect=ValueError("Invalid account"),
    ):
        response = await async_client.post(
            "/api/v1/public/assessment", json={"aws_account_id": "invalid"}
        )
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "VALUE_ERROR"
    assert data["message"] == "Invalid account"


@pytest.mark.asyncio
async def test_run_public_assessment_unexpected_error(async_client: AsyncClient):
    with patch(
        "app.modules.governance.api.v1.public.assessment_service.run_assessment",
        side_effect=RuntimeError("unexpected"),
    ):
        response = await async_client.post(
            "/api/v1/public/assessment", json={"aws_account_id": "123456789012"}
        )
    assert response.status_code == 500
    assert "unexpected error occurred during assessment" in str(response.json()).lower()


@pytest.mark.asyncio
async def test_sso_discovery_domain_mode_success(
    async_client: AsyncClient, db: AsyncSession
):
    import uuid

    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Tenant SSO Domain", plan="pro")
    db.add(tenant)
    db.add(
        SsoDomainMapping(
            tenant_id=tenant_id,
            domain="example.com",
            federation_mode="domain",
            provider_id=None,
            is_active=True,
        )
    )
    await db.commit()

    res = await async_client.post(
        "/api/v1/public/sso/discovery",
        json={"email": "user@example.com"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["available"] is True
    assert payload["mode"] == "domain"
    assert payload["domain"] == "example.com"


@pytest.mark.asyncio
async def test_sso_discovery_provider_id_mode_success(
    async_client: AsyncClient, db: AsyncSession
):
    import uuid

    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Tenant SSO Provider", plan="enterprise")
    db.add(tenant)
    db.add(
        SsoDomainMapping(
            tenant_id=tenant_id,
            domain="example.com",
            federation_mode="provider_id",
            provider_id="sso-provider-123",
            is_active=True,
        )
    )
    await db.commit()

    res = await async_client.post(
        "/api/v1/public/sso/discovery",
        json={"email": "user@example.com"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["available"] is True
    assert payload["mode"] == "provider_id"
    assert payload["provider_id"] == "sso-provider-123"


@pytest.mark.asyncio
async def test_sso_discovery_not_configured(async_client: AsyncClient):
    res = await async_client.post(
        "/api/v1/public/sso/discovery",
        json={"email": "user@missing-domain.com"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["available"] is False
    assert payload["reason"] == "sso_not_configured_for_domain"


@pytest.mark.asyncio
async def test_sso_discovery_backend_timeout(async_client: AsyncClient):
    with patch(
        "sqlalchemy.ext.asyncio.session.AsyncSession.execute",
        new_callable=AsyncMock,
        side_effect=TimeoutError,
    ):
        res = await async_client.post(
            "/api/v1/public/sso/discovery",
            json={"email": "user@example.com"},
        )
    assert res.status_code == 200
    payload = res.json()
    assert payload["available"] is False
    assert payload["reason"] == "sso_discovery_backend_timeout"


@pytest.mark.asyncio
async def test_sso_discovery_backend_error(async_client: AsyncClient):
    with patch(
        "sqlalchemy.ext.asyncio.session.AsyncSession.execute",
        new_callable=AsyncMock,
        side_effect=RuntimeError("db unavailable"),
    ):
        res = await async_client.post(
            "/api/v1/public/sso/discovery",
            json={"email": "user@example.com"},
        )
    assert res.status_code == 200
    payload = res.json()
    assert payload["available"] is False
    assert payload["reason"] == "sso_discovery_backend_error"


@pytest.mark.asyncio
async def test_run_public_assessment_does_not_swallow_fatal_exceptions(
    async_client: AsyncClient,
):
    with patch(
        "app.modules.governance.api.v1.public.assessment_service.run_assessment",
        side_effect=_FatalTestSignal(),
    ):
        with pytest.raises(BaseExceptionGroup) as exc_info:
            await async_client.post(
                "/api/v1/public/assessment", json={"aws_account_id": "123456789012"}
            )
    assert _exception_group_contains(exc_info.value, _FatalTestSignal)


@pytest.mark.asyncio
async def test_sso_discovery_does_not_swallow_fatal_backend_exceptions(
    async_client: AsyncClient,
):
    with patch(
        "sqlalchemy.ext.asyncio.session.AsyncSession.execute",
        new_callable=AsyncMock,
        side_effect=_FatalTestSignal(),
    ):
        with pytest.raises(BaseExceptionGroup) as exc_info:
            await async_client.post(
                "/api/v1/public/sso/discovery",
                json={"email": "user@example.com"},
            )
    assert _exception_group_contains(exc_info.value, _FatalTestSignal)


@pytest.mark.asyncio
async def test_sso_discovery_tier_not_eligible(async_client: AsyncClient, db: AsyncSession):
    import uuid

    tenant_id = uuid.uuid4()
    db.add(Tenant(id=tenant_id, name="Tenant Free", plan="starter"))
    db.add(
        SsoDomainMapping(
            tenant_id=tenant_id,
            domain="tier-ineligible.example",
            federation_mode="domain",
            provider_id=None,
            is_active=True,
        )
    )
    await db.commit()

    res = await async_client.post(
        "/api/v1/public/sso/discovery",
        json={"email": "user@tier-ineligible.example"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["available"] is False
    assert payload["reason"] == "tier_not_eligible_for_sso_federation"


@pytest.mark.asyncio
async def test_sso_discovery_provider_id_missing(async_client: AsyncClient, db: AsyncSession):
    import uuid

    tenant_id = uuid.uuid4()
    db.add(Tenant(id=tenant_id, name="Tenant Missing Provider", plan="enterprise"))
    db.add(
        SsoDomainMapping(
            tenant_id=tenant_id,
            domain="provider-missing.example",
            federation_mode="provider_id",
            provider_id=None,
            is_active=True,
        )
    )
    await db.commit()

    res = await async_client.post(
        "/api/v1/public/sso/discovery",
        json={"email": "user@provider-missing.example"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["available"] is False
    assert payload["reason"] == "sso_provider_id_not_configured"


@pytest.mark.asyncio
async def test_marketing_subscribe_accepts_valid_payload(async_client: AsyncClient) -> None:
    with patch(
        "app.modules.governance.api.v1.public_marketing.get_settings",
        return_value=SimpleNamespace(
            MARKETING_SUBSCRIBE_WEBHOOK_URL="",
            WEBHOOK_ALLOWED_DOMAINS=[],
            WEBHOOK_REQUIRE_HTTPS=True,
            WEBHOOK_BLOCK_PRIVATE_IPS=True,
            TRUST_PROXY_HEADERS=False,
            TRUSTED_PROXY_HOPS=1,
            TRUSTED_PROXY_CIDRS=[],
        ),
    ):
        response = await async_client.post(
            "/api/v1/public/marketing/subscribe",
            json={
                "email": "buyer@example.com",
                "company": "Example Inc",
                "role": "FinOps",
                "referrer": "landing-page",
            },
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["ok"] is True
    assert payload["accepted"] is True
    assert len(payload["emailHash"]) == 64


@pytest.mark.asyncio
async def test_marketing_subscribe_delivery_failure_returns_503(async_client: AsyncClient) -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = RuntimeError("webhook failed")
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    with (
        patch(
            "app.modules.governance.api.v1.public_marketing.get_settings",
            return_value=SimpleNamespace(
                MARKETING_SUBSCRIBE_WEBHOOK_URL="https://hooks.example.com/subscribe",
                WEBHOOK_ALLOWED_DOMAINS=["example.com"],
                WEBHOOK_REQUIRE_HTTPS=True,
                WEBHOOK_BLOCK_PRIVATE_IPS=True,
                TRUST_PROXY_HEADERS=False,
                TRUSTED_PROXY_HOPS=1,
                TRUSTED_PROXY_CIDRS=[],
            ),
        ),
        patch(
            "app.modules.governance.api.v1.public_marketing.get_http_client",
            return_value=mock_client,
        ),
    ):
        response = await async_client.post(
            "/api/v1/public/marketing/subscribe",
            json={"email": "buyer@example.com"},
        )

    assert response.status_code == 503
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"] == "delivery_failed"


@pytest.mark.asyncio
async def test_sso_discovery_unknown_mode_falls_back_to_domain(
    async_client: AsyncClient, db: AsyncSession
):
    import uuid

    tenant_id = uuid.uuid4()
    db.add(Tenant(id=tenant_id, name="Tenant Unknown Mode", plan="pro"))
    db.add(
        SsoDomainMapping(
            tenant_id=tenant_id,
            domain="unknown-mode.example",
            federation_mode="invalid-mode",
            provider_id=None,
            is_active=True,
        )
    )
    await db.commit()

    res = await async_client.post(
        "/api/v1/public/sso/discovery",
        json={"email": "user@unknown-mode.example"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["available"] is True
    assert payload["mode"] == "domain"
    assert payload["domain"] == "unknown-mode.example"


@pytest.mark.asyncio
async def test_sso_discovery_ambiguous_mapping_returns_unavailable(async_client: AsyncClient):
    class _Rows:
        def __init__(self, values):
            self._values = values

        def all(self):
            return self._values

    rows = _Rows(
        [
            (SimpleNamespace(federation_mode="domain", provider_id=None), "pro"),
            (SimpleNamespace(federation_mode="domain", provider_id=None), "enterprise"),
        ]
    )

    with patch(
        "sqlalchemy.ext.asyncio.session.AsyncSession.execute",
        new_callable=AsyncMock,
        return_value=rows,
    ):
        res = await async_client.post(
            "/api/v1/public/sso/discovery",
            json={"email": "user@example.com"},
        )

    assert res.status_code == 200
    payload = res.json()
    assert payload["available"] is False
    assert payload["reason"] == "ambiguous_tenant_domain_mapping"


def _turnstile_strict_settings() -> SimpleNamespace:
    return SimpleNamespace(
        TURNSTILE_ENABLED=True,
        TURNSTILE_ENFORCE_IN_TESTING=True,
        TURNSTILE_SECRET_KEY="turnstile-secret-key",
        TURNSTILE_VERIFY_URL="https://challenges.cloudflare.com/turnstile/v0/siteverify",
        TURNSTILE_TIMEOUT_SECONDS=2.0,
        TURNSTILE_FAIL_OPEN=False,
        TURNSTILE_REQUIRE_PUBLIC_ASSESSMENT=True,
        TURNSTILE_REQUIRE_SSO_DISCOVERY=True,
        TURNSTILE_REQUIRE_ONBOARD=True,
        TESTING=True,
        ENVIRONMENT="test",
    )


@pytest.mark.asyncio
async def test_public_assessment_requires_turnstile_token(async_client: AsyncClient):
    with patch(
        "app.shared.core.turnstile.get_settings",
        return_value=_turnstile_strict_settings(),
    ):
        response = await async_client.post(
            "/api/v1/public/assessment",
            json={"aws_account_id": "123456789012"},
        )
    assert response.status_code == 400
    assert response.json()["error"] == "turnstile_token_required"


@pytest.mark.asyncio
async def test_public_assessment_rejects_invalid_turnstile(async_client: AsyncClient):
    with (
        patch(
            "app.shared.core.turnstile.get_settings",
            return_value=_turnstile_strict_settings(),
        ),
        patch(
            "app.shared.core.turnstile._verify_turnstile_with_cloudflare",
            new_callable=AsyncMock,
            return_value={"success": False, "error-codes": ["invalid-input-response"]},
        ),
    ):
        response = await async_client.post(
            "/api/v1/public/assessment",
            json={"aws_account_id": "123456789012"},
            headers={"X-Turnstile-Token": "invalid-token"},
        )
    assert response.status_code == 403
    assert response.json()["error"] == "turnstile_verification_failed"


@pytest.mark.asyncio
async def test_sso_discovery_requires_turnstile_token(async_client: AsyncClient):
    with patch(
        "app.shared.core.turnstile.get_settings",
        return_value=_turnstile_strict_settings(),
    ):
        response = await async_client.post(
            "/api/v1/public/sso/discovery",
            json={"email": "user@example.com"},
        )
    assert response.status_code == 400
    assert response.json()["error"] == "turnstile_token_required"


@pytest.mark.asyncio
async def test_landing_telemetry_ingest_accepts_and_records_metrics(
    async_client: AsyncClient, db: AsyncSession
):
    payload = {
        "eventId": "evt-123",
        "name": "cta_click",
        "section": "hero",
        "value": "start_free",
        "visitorId": "vldx-visitor-01",
        "persona": "cto",
        "funnelStage": "cta",
        "pagePath": "/",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with (
        patch("app.modules.governance.api.v1.public.LANDING_TELEMETRY_EVENTS_TOTAL") as mock_events,
        patch("app.modules.governance.api.v1.public.LANDING_TELEMETRY_INGEST_OUTCOMES_TOTAL") as mock_outcomes,
    ):
        response = await async_client.post("/api/v1/public/landing/events", json=payload)

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["ingest_id"] == "evt-123"
    mock_events.labels.assert_called_once_with(
        event_name="cta_click",
        section="hero",
        funnel_stage="cta",
    )
    mock_events.labels.return_value.inc.assert_called_once()
    mock_outcomes.labels.assert_called_once_with(outcome="accepted")
    mock_outcomes.labels.return_value.inc.assert_called_once()

    rollups = (
        await db.execute(
            select(LandingTelemetryDailyRollup).where(
                LandingTelemetryDailyRollup.utm_campaign == "direct"
            )
        )
    ).scalars().all()
    assert len(rollups) == 1
    assert rollups[0].event_name == "cta_click"
    assert rollups[0].funnel_stage == "cta"
    assert rollups[0].event_count == 1


@pytest.mark.asyncio
async def test_landing_telemetry_ingest_rejects_out_of_window_timestamp(
    async_client: AsyncClient,
):
    payload = {
        "name": "landing_view",
        "section": "landing",
        "funnelStage": "view",
        "timestamp": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
    }
    with patch(
        "app.modules.governance.api.v1.public.LANDING_TELEMETRY_INGEST_OUTCOMES_TOTAL"
    ) as mock_outcomes:
        response = await async_client.post("/api/v1/public/landing/events", json=payload)

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "ignored"
    assert data["reason"] == "timestamp_out_of_bounds"
    mock_outcomes.labels.assert_called_once_with(outcome="rejected_timestamp")
    mock_outcomes.labels.return_value.inc.assert_called_once()
