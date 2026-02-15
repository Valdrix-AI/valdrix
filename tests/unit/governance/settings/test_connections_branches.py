from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.governance.api.v1.settings import connections as connections_api
from app.schemas.connections import (
    AWSConnectionCreate,
    AzureConnectionCreate,
    GCPConnectionCreate,
    LicenseConnectionCreate,
    SaaSConnectionCreate,
)
from app.shared.core.auth import CurrentUser
from app.shared.core.pricing import PricingTier


def _scalar_result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_result(values: list[object]) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = values
    result.scalars.return_value = scalars
    return result


@pytest.fixture
def user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        email="member@example.com",
        tenant_id=uuid4(),
        tier=PricingTier.GROWTH,
    )


@pytest.fixture
def db() -> MagicMock:
    mock_db = MagicMock()
    mock_db.scalar = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.delete = AsyncMock()
    mock_db.add = MagicMock()
    return mock_db


def test_require_tenant_id_raises_when_missing() -> None:
    missing_tenant_user = CurrentUser(id=uuid4(), email="u@example.com", tenant_id=None)
    with pytest.raises(HTTPException) as exc:
        connections_api._require_tenant_id(missing_tenant_user)
    assert exc.value.status_code == 404


def test_enforce_growth_tier_rejects_free(user: CurrentUser) -> None:
    with pytest.raises(HTTPException) as exc:
        connections_api._enforce_growth_tier(PricingTier.FREE_TRIAL, user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_check_growth_tier_cache_hit_denied(
    user: CurrentUser, db: MagicMock
) -> None:
    cache = SimpleNamespace(
        get=AsyncMock(return_value=PricingTier.FREE_TRIAL.value), set=AsyncMock()
    )
    with patch("app.shared.core.cache.get_cache_service", return_value=cache):
        with pytest.raises(HTTPException) as exc:
            await connections_api.check_growth_tier(user, db)
    assert exc.value.status_code == 403
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_growth_tier_cache_invalid_and_tenant_missing(
    user: CurrentUser, db: MagicMock
) -> None:
    cache = SimpleNamespace(get=AsyncMock(return_value="invalid-plan"), set=AsyncMock())
    db.execute.return_value = _scalar_result(None)
    with patch("app.shared.core.cache.get_cache_service", return_value=cache):
        with pytest.raises(HTTPException) as exc:
            await connections_api.check_growth_tier(user, db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_check_growth_tier_cache_set_failure_is_non_fatal(
    user: CurrentUser, db: MagicMock
) -> None:
    tenant = SimpleNamespace(plan=PricingTier.GROWTH.value)
    cache = SimpleNamespace(
        get=AsyncMock(return_value=None),
        set=AsyncMock(side_effect=RuntimeError("cache down")),
    )
    db.execute.return_value = _scalar_result(tenant)
    with patch("app.shared.core.cache.get_cache_service", return_value=cache):
        await connections_api.check_growth_tier(user, db)


@pytest.mark.asyncio
async def test_create_aws_connection_duplicate_raises(
    user: CurrentUser, db: MagicMock
) -> None:
    payload = AWSConnectionCreate(
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/TestRole",
        external_id="vx-" + "a" * 32,
        region="us-east-1",
    )
    db.scalar.return_value = uuid4()
    with pytest.raises(HTTPException) as exc:
        await connections_api.create_aws_connection(MagicMock(), payload, user, db)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_aws_connection_not_found(
    user: CurrentUser, db: MagicMock
) -> None:
    db.execute.return_value = _scalar_result(None)
    with pytest.raises(HTTPException) as exc:
        await connections_api.delete_aws_connection(uuid4(), user, db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_sync_aws_org_requires_management_account(
    user: CurrentUser, db: MagicMock
) -> None:
    db.execute.return_value = _scalar_result(
        SimpleNamespace(is_management_account=False)
    )
    with pytest.raises(HTTPException) as exc:
        await connections_api.sync_aws_org(uuid4(), user, db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_discovered_accounts_returns_empty_when_no_management_connection(
    user: CurrentUser, db: MagicMock
) -> None:
    db.execute.return_value = _scalars_result([])
    discovered = await connections_api.list_discovered_accounts(user, db)
    assert discovered == []


@pytest.mark.asyncio
async def test_link_discovered_account_not_authorized(
    user: CurrentUser, db: MagicMock
) -> None:
    row_result = MagicMock()
    row_result.one_or_none.return_value = None
    db.execute.return_value = row_result
    with pytest.raises(HTTPException) as exc:
        await connections_api.link_discovered_account(uuid4(), user, db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_link_discovered_account_existing_connection_path(
    user: CurrentUser, db: MagicMock
) -> None:
    discovered = SimpleNamespace(account_id="123456789012", status="pending")
    mgmt = SimpleNamespace(external_id="vx-" + "a" * 32)
    first = MagicMock()
    first.one_or_none.return_value = (discovered, mgmt)
    second = _scalar_result(SimpleNamespace(id=uuid4()))
    db.execute.side_effect = [first, second]

    response = await connections_api.link_discovered_account(uuid4(), user, db)
    assert response["status"] == "existing"
    assert discovered.status == "linked"
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_create_azure_connection_duplicate_raises(
    user: CurrentUser, db: MagicMock
) -> None:
    payload = AzureConnectionCreate(
        name="Azure Subscription",
        azure_tenant_id="tenant-1",
        client_id="client-1",
        subscription_id="sub-1",
        client_secret="secret",
    )
    db.scalar.return_value = SimpleNamespace(id=uuid4())
    with patch.object(connections_api, "check_growth_tier", new=AsyncMock()):
        with pytest.raises(HTTPException) as exc:
            await connections_api.create_azure_connection(
                MagicMock(), payload, user, db
            )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_azure_connection_not_found(
    user: CurrentUser, db: MagicMock
) -> None:
    db.execute.return_value = _scalar_result(None)
    with pytest.raises(HTTPException) as exc:
        await connections_api.delete_azure_connection(uuid4(), user, db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_gcp_connection_duplicate_raises(
    user: CurrentUser, db: MagicMock
) -> None:
    payload = GCPConnectionCreate(
        name="GCP Project",
        project_id="project-1",
        service_account_json='{"type":"service_account"}',
        auth_method="secret",
    )
    db.scalar.return_value = SimpleNamespace(id=uuid4())
    with patch.object(connections_api, "check_growth_tier", new=AsyncMock()):
        with pytest.raises(HTTPException) as exc:
            await connections_api.create_gcp_connection(MagicMock(), payload, db, user)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_create_gcp_connection_workload_identity_failure(
    user: CurrentUser, db: MagicMock
) -> None:
    payload = GCPConnectionCreate(
        name="GCP Workload Identity",
        project_id="project-2",
        auth_method="workload_identity",
    )
    db.scalar.return_value = None
    with (
        patch.object(connections_api, "check_growth_tier", new=AsyncMock()),
        patch(
            "app.shared.connections.oidc.OIDCService.verify_gcp_access",
            new=AsyncMock(return_value=(False, "not trusted")),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await connections_api.create_gcp_connection(MagicMock(), payload, db, user)
    assert exc.value.status_code == 400
    assert "verification failed" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_delete_gcp_connection_not_found(
    user: CurrentUser, db: MagicMock
) -> None:
    db.execute.return_value = _scalar_result(None)
    with pytest.raises(HTTPException) as exc:
        await connections_api.delete_gcp_connection(uuid4(), user, db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_check_cloud_plus_tier_denied_for_growth(
    user: CurrentUser, db: MagicMock
) -> None:
    cache = SimpleNamespace(
        get=AsyncMock(return_value=PricingTier.GROWTH.value), set=AsyncMock()
    )
    with patch("app.shared.core.cache.get_cache_service", return_value=cache):
        with pytest.raises(HTTPException) as exc:
            await connections_api.check_cloud_plus_tier(user, db)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_check_cloud_plus_tier_allows_pro(
    user: CurrentUser, db: MagicMock
) -> None:
    cache = SimpleNamespace(
        get=AsyncMock(return_value=PricingTier.PRO.value), set=AsyncMock()
    )
    with patch("app.shared.core.cache.get_cache_service", return_value=cache):
        await connections_api.check_cloud_plus_tier(user, db)


@pytest.mark.asyncio
async def test_create_saas_connection_duplicate_raises(
    user: CurrentUser, db: MagicMock
) -> None:
    payload = SaaSConnectionCreate(
        name="Salesforce",
        vendor="salesforce",
        auth_method="manual",
        spend_feed=[],
    )
    db.scalar.return_value = uuid4()
    with patch.object(connections_api, "check_cloud_plus_tier", new=AsyncMock()):
        with pytest.raises(HTTPException) as exc:
            await connections_api.create_saas_connection(MagicMock(), payload, user, db)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_saas_connection_not_found(
    user: CurrentUser, db: MagicMock
) -> None:
    db.execute.return_value = _scalar_result(None)
    with pytest.raises(HTTPException) as exc:
        await connections_api.delete_saas_connection(uuid4(), user, db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_license_connection_duplicate_raises(
    user: CurrentUser, db: MagicMock
) -> None:
    payload = LicenseConnectionCreate(
        name="Microsoft 365",
        vendor="microsoft",
        auth_method="manual",
        license_feed=[],
    )
    db.scalar.return_value = uuid4()
    with patch.object(connections_api, "check_cloud_plus_tier", new=AsyncMock()):
        with pytest.raises(HTTPException) as exc:
            await connections_api.create_license_connection(
                MagicMock(), payload, user, db
            )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_license_connection_not_found(
    user: CurrentUser, db: MagicMock
) -> None:
    db.execute.return_value = _scalar_result(None)
    with pytest.raises(HTTPException) as exc:
        await connections_api.delete_license_connection(uuid4(), user, db)
    assert exc.value.status_code == 404
