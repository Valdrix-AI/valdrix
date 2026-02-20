from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request
from sqlalchemy.exc import IntegrityError

from app.modules.governance.api.v1.settings.onboard import OnboardRequest, onboard
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.exceptions import ConfigurationError


def _request(scheme: str = "https", forwarded_proto: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if forwarded_proto is not None:
        headers.append((b"x-forwarded-proto", forwarded_proto.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/settings/onboard",
        "raw_path": b"/api/v1/settings/onboard",
        "query_string": b"",
        "headers": headers,
        "server": ("testserver", 443 if scheme == "https" else 80),
        "scheme": scheme,
    }
    return Request(scope)


def _current_user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        email=f"owner-{uuid4().hex[:8]}@example.com",
        role=UserRole.MEMBER,
    )


def _db(
    existing_user: bool = False, commit_error: Exception | None = None
) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = (
        SimpleNamespace(id=uuid4()) if existing_user else None
    )
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()

    async def _flush() -> None:
        for call in db.add.call_args_list:
            obj = call.args[0]
            if obj.__class__.__name__ == "Tenant" and getattr(obj, "id", None) is None:
                obj.id = uuid4()

    db.flush = AsyncMock(side_effect=_flush)
    db.rollback = AsyncMock()
    if commit_error is not None:
        db.commit = AsyncMock(side_effect=commit_error)
    else:
        db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform", "cloud_config"),
    [
        (
            "aws",
            {"platform": "aws", "role_arn": "arn:aws:iam::123456789012:role/TestRole"},
        ),
        (
            "azure",
            {
                "platform": "azure",
                "client_id": "client-id",
                "client_secret": "client-secret",
                "azure_tenant_id": "tenant-id",
                "subscription_id": "subscription-id",
            },
        ),
        (
            "gcp",
            {
                "platform": "gcp",
                "project_id": "project-id",
                "service_account_json": '{"type":"service_account"}',
            },
        ),
        (
            "saas",
            {
                "platform": "saas",
                "vendor": "stripe",
                "auth_method": "manual",
                "spend_feed": [
                    {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "cost_usd": 12.3,
                        "service": "Stripe",
                    }
                ],
            },
        ),
        (
            "license",
            {
                "platform": "license",
                "vendor": "microsoft_365",
                "auth_method": "manual",
                "license_feed": [
                    {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "cost_usd": 8.4,
                        "service": "Microsoft 365",
                    }
                ],
            },
        ),
        (
            "platform",
            {
                "platform": "platform",
                "vendor": "datadog",
                "auth_method": "manual",
                "spend_feed": [
                    {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "cost_usd": 19.0,
                        "service": "Datadog",
                    }
                ],
            },
        ),
        (
            "hybrid",
            {
                "platform": "hybrid",
                "vendor": "vmware",
                "auth_method": "manual",
                "spend_feed": [
                    {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "cost_usd": 23.7,
                        "service": "vSphere",
                    }
                ],
            },
        ),
    ],
)
async def test_onboard_cloud_platform_paths(
    platform: str, cloud_config: dict[str, str]
) -> None:
    db = _db()
    req = OnboardRequest(tenant_name=f"{platform}-tenant", cloud_config=cloud_config)
    user = _current_user()
    mock_settings = SimpleNamespace(ENVIRONMENT="production")
    mock_adapter = AsyncMock()
    mock_adapter.verify_connection.return_value = True

    with (
        patch(
            "app.modules.governance.api.v1.settings.onboard.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "app.shared.adapters.factory.AdapterFactory.get_adapter",
            return_value=mock_adapter,
        ) as get_adapter,
        patch("app.modules.governance.api.v1.settings.onboard.audit_log"),
    ):
        response = await onboard(
            _request(scheme="http", forwarded_proto="https, http"),
            req,
            user,
            db,
        )

    assert response.status == "onboarded"
    assert isinstance(response.tenant_id, UUID)
    assert get_adapter.called
    mock_adapter.verify_connection.assert_awaited_once()


@pytest.mark.asyncio
async def test_onboard_aws_uses_configured_default_region_when_missing() -> None:
    db = _db()
    req = OnboardRequest(
        tenant_name="aws-tenant",
        cloud_config={
            "platform": "aws",
            "role_arn": "arn:aws:iam::123456789012:role/TestRole",
        },
    )
    user = _current_user()
    mock_settings = SimpleNamespace(
        ENVIRONMENT="development",
        AWS_DEFAULT_REGION="ap-south-1",
    )
    mock_adapter = AsyncMock()
    mock_adapter.verify_connection.return_value = True
    captured: dict[str, str] = {}

    def _capture_adapter(connection: object) -> AsyncMock:
        captured["region"] = str(getattr(connection, "region", ""))
        return mock_adapter

    with (
        patch(
            "app.modules.governance.api.v1.settings.onboard.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "app.shared.adapters.factory.AdapterFactory.get_adapter",
            side_effect=_capture_adapter,
        ),
        patch("app.modules.governance.api.v1.settings.onboard.audit_log"),
    ):
        response = await onboard(_request(), req, user, db)

    assert response.status == "onboarded"
    assert captured["region"] == "ap-south-1"
    mock_adapter.verify_connection.assert_awaited_once()


@pytest.mark.asyncio
async def test_onboard_aws_falls_back_to_multitenant_verifier_when_cur_missing() -> None:
    db = _db()
    req = OnboardRequest(
        tenant_name="aws-fallback-tenant",
        cloud_config={
            "platform": "aws",
            "role_arn": "arn:aws:iam::123456789012:role/TestRole",
            "external_id": "vx-onboard",
            "aws_account_id": "123456789012",
        },
    )
    user = _current_user()
    mock_settings = SimpleNamespace(
        ENVIRONMENT="development",
        AWS_DEFAULT_REGION="eu-west-1",
    )
    mock_mt_adapter = AsyncMock()
    mock_mt_adapter.verify_connection.return_value = True

    with (
        patch(
            "app.modules.governance.api.v1.settings.onboard.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "app.shared.adapters.factory.AdapterFactory.get_adapter",
            side_effect=ConfigurationError("CUR is required for cost ingestion"),
        ),
        patch(
            "app.shared.adapters.aws_multitenant.MultiTenantAWSAdapter",
            return_value=mock_mt_adapter,
        ) as mock_mt_class,
        patch("app.modules.governance.api.v1.settings.onboard.audit_log"),
    ):
        response = await onboard(_request(), req, user, db)

    assert response.status == "onboarded"
    mock_mt_class.assert_called_once()
    mock_mt_adapter.verify_connection.assert_awaited_once()


@pytest.mark.asyncio
async def test_onboard_unexpected_adapter_error_is_translated() -> None:
    db = _db()
    req = OnboardRequest(
        tenant_name="aws-tenant",
        cloud_config={
            "platform": "aws",
            "role_arn": "arn:aws:iam::123456789012:role/TestRole",
        },
    )
    user = _current_user()
    mock_settings = SimpleNamespace(ENVIRONMENT="development")

    with (
        patch(
            "app.modules.governance.api.v1.settings.onboard.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "app.shared.adapters.factory.AdapterFactory.get_adapter",
            side_effect=RuntimeError("adapter exploded"),
        ),
        patch("app.modules.governance.api.v1.settings.onboard.audit_log"),
    ):
        with pytest.raises(HTTPException) as exc:
            await onboard(_request(), req, user, db)

    assert exc.value.status_code == 400
    assert "Error verifying aws connection: adapter exploded" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_onboard_integrity_error_maps_to_already_onboarded() -> None:
    db = _db(
        commit_error=IntegrityError("insert users", {}, Exception("duplicate user"))
    )
    req = OnboardRequest(tenant_name="race-tenant")
    user = _current_user()

    with patch("app.modules.governance.api.v1.settings.onboard.audit_log"):
        with pytest.raises(HTTPException) as exc:
            await onboard(_request(), req, user, db)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Already onboarded"
    db.rollback.assert_awaited_once()
