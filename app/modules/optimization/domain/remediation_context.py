from __future__ import annotations

from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import structlog
from sqlalchemy import select

from app.models.cloud import CloudAccount
from app.models.remediation_settings import RemediationSettings
from app.modules.governance.domain.security.remediation_policy import PolicyConfig
from app.shared.core.provider import normalize_provider

logger = structlog.get_logger()


async def resolve_aws_region_hint(
    service: Any,
    *,
    tenant_id: UUID | None = None,
    connection_id: UUID | None = None,
    connection: Any | None = None,
) -> str:
    """
    Resolve a concrete AWS region from request hint + optional connection context.

    `global` is treated as a non-concrete sentinel for cross-provider API defaults.
    """
    import app.modules.optimization.domain.remediation as remediation_module

    region_hint = str(service.region or "").strip().lower()
    if region_hint and region_hint != "global":
        return region_hint

    if connection is not None:
        connection_region = remediation_module.resolve_connection_region(connection)
        if connection_region != "global":
            return connection_region

    if tenant_id and connection_id:
        connection_model = remediation_module.get_connection_model("aws")
        if connection_model is not None:
            try:
                scoped = await service.get_by_id(connection_model, connection_id, tenant_id)
                if scoped is not None:
                    scoped_region = remediation_module.resolve_connection_region(scoped)
                    if scoped_region != "global":
                        return scoped_region
            except Exception as exc:
                logger.warning(
                    "remediation_aws_region_resolution_failed",
                    tenant_id=str(tenant_id),
                    connection_id=str(connection_id),
                    error=str(exc),
                )

    return (
        str(remediation_module.get_settings().AWS_DEFAULT_REGION or "").strip()
        or "us-east-1"
    )


async def get_remediation_settings(
    service: Any,
    tenant_id: UUID,
) -> RemediationSettings | None:
    if tenant_id in service._remediation_settings_cache:
        return cast(
            RemediationSettings | None,
            service._remediation_settings_cache[tenant_id],
        )

    try:
        result = await service.db.execute(
            select(RemediationSettings).where(
                RemediationSettings.tenant_id == tenant_id
            )
        )
        settings = await service._scalar_one_or_none(result)
        resolved = settings if isinstance(settings, RemediationSettings) else None
        service._remediation_settings_cache[tenant_id] = resolved
        return resolved
    except Exception as exc:
        logger.warning(
            "remediation_settings_lookup_failed",
            tenant_id=str(tenant_id),
            error=str(exc),
        )
        service._remediation_settings_cache[tenant_id] = None
        return None


async def build_policy_config(
    service: Any,
    tenant_id: UUID,
) -> tuple[PolicyConfig, RemediationSettings | None]:
    settings = await get_remediation_settings(service, tenant_id)
    if not settings:
        return PolicyConfig(), None

    threshold_raw = getattr(
        settings, "policy_low_confidence_warn_threshold", Decimal("0.90")
    )
    config = PolicyConfig(
        enabled=bool(getattr(settings, "policy_enabled", True)),
        block_production_destructive=bool(
            getattr(settings, "policy_block_production_destructive", True)
        ),
        require_gpu_override=bool(getattr(settings, "policy_require_gpu_override", True)),
        low_confidence_warn_threshold=Decimal(str(threshold_raw)),
    )
    return config, settings


async def build_system_policy_context(
    service: Any,
    *,
    tenant_id: UUID,
    provider: str,
    connection_id: UUID | None,
) -> dict[str, Any]:
    import app.modules.optimization.domain.remediation as remediation_module

    provider_norm = normalize_provider(provider)
    if not provider_norm:
        return {}

    if connection_id:
        account_context: dict[str, Any] | None = None
        account_result = await service.db.execute(
            select(CloudAccount)
            .where(CloudAccount.tenant_id == tenant_id)
            .where(CloudAccount.id == connection_id)
            .where(CloudAccount.provider == provider_norm)
        )
        account = await service._scalar_one_or_none(account_result)
        if isinstance(account, CloudAccount):
            account_context = {
                "source": "cloud_account",
                "connection_id": str(connection_id),
                "is_production": bool(getattr(account, "is_production", False)),
                "criticality": getattr(account, "criticality", None),
            }
            if account_context["is_production"] or account_context["criticality"]:
                return account_context

        connection_model = remediation_module.get_connection_model(provider_norm)
        if connection_model is not None:
            connection_result = await service.db.execute(
                select(connection_model)
                .where(connection_model.tenant_id == tenant_id)
                .where(connection_model.id == connection_id)
            )
            connection = await service._scalar_one_or_none(connection_result)
            if connection is not None:
                profile = remediation_module.resolve_connection_profile(connection)
                is_production = profile.get("is_production")
                return {
                    "source": str(profile.get("source") or "connection_profile"),
                    "connection_id": str(connection_id),
                    "is_production": (
                        is_production if isinstance(is_production, bool) else None
                    ),
                    "criticality": profile.get("criticality"),
                }

        if account_context is not None:
            return account_context

    return {}
