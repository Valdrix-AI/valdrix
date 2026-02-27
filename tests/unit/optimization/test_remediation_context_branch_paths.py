from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.models.cloud import CloudAccount
from app.models.remediation_settings import RemediationSettings
from app.modules.governance.domain.security.remediation_policy import PolicyConfig
from app.modules.optimization.domain import remediation_context as ctx


class _FakeSelect:
    def __init__(self, model: object) -> None:
        self.model = model
        self.wheres: list[object] = []

    def where(self, condition: object) -> "_FakeSelect":
        self.wheres.append(condition)
        return self


class _FakeField:
    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: object) -> tuple[str, str, object]:  # type: ignore[override]
        return ("eq", self.name, other)


class _FakeConnectionModel:
    tenant_id = _FakeField("tenant_id")
    id = _FakeField("id")


def _fake_select(model: object) -> _FakeSelect:
    return _FakeSelect(model)


def _service(*, region: str = "global") -> SimpleNamespace:
    return SimpleNamespace(
        region=region,
        db=SimpleNamespace(execute=AsyncMock()),
        _scalar_one_or_none=AsyncMock(),
        _remediation_settings_cache={},
        get_by_id=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_resolve_aws_region_hint_prefers_explicit_region_and_connection_region() -> None:
    service = _service(region=" Eu-West-2 ")
    resolved = await ctx.resolve_aws_region_hint(service)
    assert resolved == "eu-west-2"

    service = _service(region="global")
    with patch(
        "app.modules.optimization.domain.remediation.resolve_connection_region",
        return_value="ap-southeast-1",
    ):
        resolved = await ctx.resolve_aws_region_hint(
            service,
            connection=SimpleNamespace(region="ignored"),
        )
    assert resolved == "ap-southeast-1"


@pytest.mark.asyncio
async def test_resolve_aws_region_hint_scoped_lookup_and_fallback_paths() -> None:
    tenant_id = uuid4()
    connection_id = uuid4()

    service = _service(region="global")
    service.get_by_id = AsyncMock(return_value=SimpleNamespace(region="ignored"))
    with (
        patch("app.modules.optimization.domain.remediation.get_connection_model", return_value=object()),
        patch(
            "app.modules.optimization.domain.remediation.resolve_connection_region",
            return_value="us-west-2",
        ),
    ):
        resolved = await ctx.resolve_aws_region_hint(
            service,
            tenant_id=tenant_id,
            connection_id=connection_id,
        )
    assert resolved == "us-west-2"

    service = _service(region="global")
    service.get_by_id = AsyncMock(side_effect=RuntimeError("boom"))
    with (
        patch("app.modules.optimization.domain.remediation.get_connection_model", return_value=object()),
        patch(
            "app.modules.optimization.domain.remediation.get_settings",
            return_value=SimpleNamespace(AWS_DEFAULT_REGION=" "),
        ),
        patch.object(ctx.logger, "warning") as warning,
    ):
        resolved = await ctx.resolve_aws_region_hint(
            service,
            tenant_id=tenant_id,
            connection_id=connection_id,
        )
    assert resolved == "us-east-1"
    warning.assert_called_once()

    service = _service(region="global")
    with (
        patch("app.modules.optimization.domain.remediation.get_connection_model", return_value=None),
        patch(
            "app.modules.optimization.domain.remediation.get_settings",
            return_value=SimpleNamespace(AWS_DEFAULT_REGION="eu-north-1"),
        ),
    ):
        resolved = await ctx.resolve_aws_region_hint(
            service,
            tenant_id=tenant_id,
            connection_id=connection_id,
        )
    assert resolved == "eu-north-1"


@pytest.mark.asyncio
async def test_resolve_aws_region_hint_falls_back_when_connection_or_scoped_regions_are_global() -> None:
    tenant_id = uuid4()
    connection_id = uuid4()

    service = _service(region="global")
    with (
        patch(
            "app.modules.optimization.domain.remediation.resolve_connection_region",
            return_value="global",
        ),
        patch(
            "app.modules.optimization.domain.remediation.get_settings",
            return_value=SimpleNamespace(AWS_DEFAULT_REGION="eu-west-1"),
        ),
    ):
        resolved = await ctx.resolve_aws_region_hint(
            service,
            connection=SimpleNamespace(region="global"),
        )
    assert resolved == "eu-west-1"

    service = _service(region="global")
    service.get_by_id = AsyncMock(return_value=None)
    with (
        patch("app.modules.optimization.domain.remediation.get_connection_model", return_value=object()),
        patch(
            "app.modules.optimization.domain.remediation.get_settings",
            return_value=SimpleNamespace(AWS_DEFAULT_REGION="eu-central-1"),
        ),
    ):
        resolved = await ctx.resolve_aws_region_hint(
            service,
            tenant_id=tenant_id,
            connection_id=connection_id,
        )
    assert resolved == "eu-central-1"

    service = _service(region="global")
    service.get_by_id = AsyncMock(return_value=SimpleNamespace(region="global"))
    with (
        patch("app.modules.optimization.domain.remediation.get_connection_model", return_value=object()),
        patch(
            "app.modules.optimization.domain.remediation.resolve_connection_region",
            return_value="global",
        ),
        patch(
            "app.modules.optimization.domain.remediation.get_settings",
            return_value=SimpleNamespace(AWS_DEFAULT_REGION="ap-northeast-1"),
        ),
    ):
        resolved = await ctx.resolve_aws_region_hint(
            service,
            tenant_id=tenant_id,
            connection_id=connection_id,
        )
    assert resolved == "ap-northeast-1"


@pytest.mark.asyncio
async def test_get_remediation_settings_cache_and_lookup_branches() -> None:
    tenant_id = uuid4()
    cached_settings = RemediationSettings(tenant_id=tenant_id)
    service = _service()
    service._remediation_settings_cache[tenant_id] = cached_settings

    resolved = await ctx.get_remediation_settings(service, tenant_id)
    assert resolved is cached_settings
    service.db.execute.assert_not_called()

    service = _service()
    service.db.execute.return_value = "db-result"
    service._scalar_one_or_none.return_value = cached_settings
    with patch.object(ctx, "select", side_effect=_fake_select):
        resolved = await ctx.get_remediation_settings(service, tenant_id)
    assert resolved is cached_settings
    assert service._remediation_settings_cache[tenant_id] is cached_settings

    tenant_id_non_instance = uuid4()
    service = _service()
    service.db.execute.return_value = "db-result"
    service._scalar_one_or_none.return_value = SimpleNamespace()
    with patch.object(ctx, "select", side_effect=_fake_select):
        resolved = await ctx.get_remediation_settings(service, tenant_id_non_instance)
    assert resolved is None
    assert service._remediation_settings_cache[tenant_id_non_instance] is None


@pytest.mark.asyncio
async def test_get_remediation_settings_logs_and_caches_none_on_db_error() -> None:
    tenant_id = uuid4()
    service = _service()
    service.db.execute = AsyncMock(side_effect=RuntimeError("db down"))

    with (
        patch.object(ctx, "select", side_effect=_fake_select),
        patch.object(ctx.logger, "warning") as warning,
    ):
        resolved = await ctx.get_remediation_settings(service, tenant_id)

    assert resolved is None
    assert service._remediation_settings_cache[tenant_id] is None
    warning.assert_called_once()


@pytest.mark.asyncio
async def test_build_policy_config_default_and_custom_values() -> None:
    tenant_id = uuid4()
    service = _service()

    with patch.object(ctx, "get_remediation_settings", new=AsyncMock(return_value=None)):
        config, settings = await ctx.build_policy_config(service, tenant_id)
    assert config == PolicyConfig()
    assert settings is None

    custom_settings = SimpleNamespace(
        policy_enabled=False,
        policy_block_production_destructive=False,
        policy_require_gpu_override=False,
        policy_low_confidence_warn_threshold="0.77",
    )
    with patch.object(
        ctx,
        "get_remediation_settings",
        new=AsyncMock(return_value=custom_settings),
    ):
        config, settings = await ctx.build_policy_config(service, tenant_id)

    assert settings is custom_settings
    assert config.enabled is False
    assert config.block_production_destructive is False
    assert config.require_gpu_override is False
    assert config.low_confidence_warn_threshold == Decimal("0.77")


def _cloud_account(
    *,
    tenant_id,
    connection_id,
    provider: str = "aws",
    is_production: bool = False,
    criticality: str | None = None,
) -> CloudAccount:
    return CloudAccount(
        id=connection_id,
        tenant_id=tenant_id,
        provider=provider,
        name="acct",
        is_production=is_production,
        criticality=criticality,
    )


@pytest.mark.asyncio
async def test_build_system_policy_context_short_circuits_invalid_provider_and_no_connection() -> None:
    tenant_id = uuid4()
    service = _service()

    with patch.object(ctx, "normalize_provider", return_value=None):
        assert (
            await ctx.build_system_policy_context(
                service,
                tenant_id=tenant_id,
                provider="bad",
                connection_id=None,
            )
            == {}
        )

    with patch.object(ctx, "normalize_provider", return_value="aws"):
        assert (
            await ctx.build_system_policy_context(
                service,
                tenant_id=tenant_id,
                provider="aws",
                connection_id=None,
            )
            == {}
        )


@pytest.mark.asyncio
async def test_build_system_policy_context_prefers_cloud_account_when_production_or_critical() -> None:
    tenant_id = uuid4()
    connection_id = uuid4()
    service = _service()
    service.db.execute.return_value = "account-result"
    service._scalar_one_or_none.return_value = _cloud_account(
        tenant_id=tenant_id,
        connection_id=connection_id,
        is_production=True,
        criticality="high",
    )

    with (
        patch.object(ctx, "normalize_provider", return_value="aws"),
        patch.object(ctx, "select", side_effect=_fake_select),
    ):
        result = await ctx.build_system_policy_context(
            service,
            tenant_id=tenant_id,
            provider="aws",
            connection_id=connection_id,
        )

    assert result == {
        "source": "cloud_account",
        "connection_id": str(connection_id),
        "is_production": True,
        "criticality": "high",
    }


@pytest.mark.asyncio
async def test_build_system_policy_context_returns_account_fallback_when_connection_profile_unavailable() -> None:
    tenant_id = uuid4()
    connection_id = uuid4()
    service = _service()
    account = _cloud_account(
        tenant_id=tenant_id,
        connection_id=connection_id,
        is_production=False,
        criticality=None,
    )
    service.db.execute = AsyncMock(return_value="account-result")
    service._scalar_one_or_none = AsyncMock(return_value=account)

    with (
        patch.object(ctx, "normalize_provider", return_value="aws"),
        patch.object(ctx, "select", side_effect=_fake_select),
        patch("app.modules.optimization.domain.remediation.get_connection_model", return_value=None),
    ):
        result = await ctx.build_system_policy_context(
            service,
            tenant_id=tenant_id,
            provider="aws",
            connection_id=connection_id,
        )

    assert result == {
        "source": "cloud_account",
        "connection_id": str(connection_id),
        "is_production": False,
        "criticality": None,
    }


@pytest.mark.asyncio
async def test_build_system_policy_context_uses_connection_profile_when_account_not_authoritative() -> None:
    tenant_id = uuid4()
    connection_id = uuid4()
    service = _service()
    service.db.execute = AsyncMock(side_effect=["account-result", "connection-result"])
    service._scalar_one_or_none = AsyncMock(
        side_effect=[
            SimpleNamespace(),  # not a CloudAccount instance
            SimpleNamespace(id=connection_id),
        ]
    )

    with (
        patch.object(ctx, "normalize_provider", return_value="aws"),
        patch.object(ctx, "select", side_effect=_fake_select),
        patch("app.modules.optimization.domain.remediation.get_connection_model", return_value=_FakeConnectionModel),
        patch(
            "app.modules.optimization.domain.remediation.resolve_connection_profile",
            return_value={"source": None, "is_production": "yes", "criticality": "medium"},
        ),
    ):
        result = await ctx.build_system_policy_context(
            service,
            tenant_id=tenant_id,
            provider="aws",
            connection_id=connection_id,
        )

    assert result == {
        "source": "connection_profile",
        "connection_id": str(connection_id),
        "is_production": None,
        "criticality": "medium",
    }


@pytest.mark.asyncio
async def test_build_system_policy_context_returns_empty_when_no_account_or_connection_profile() -> None:
    tenant_id = uuid4()
    connection_id = uuid4()
    service = _service()
    service.db.execute = AsyncMock(side_effect=["account-result", "connection-result"])
    service._scalar_one_or_none = AsyncMock(side_effect=[None, None])

    with (
        patch.object(ctx, "normalize_provider", return_value="aws"),
        patch.object(ctx, "select", side_effect=_fake_select),
        patch("app.modules.optimization.domain.remediation.get_connection_model", return_value=_FakeConnectionModel),
    ):
        result = await ctx.build_system_policy_context(
            service,
            tenant_id=tenant_id,
            provider="aws",
            connection_id=connection_id,
        )

    assert result == {}
