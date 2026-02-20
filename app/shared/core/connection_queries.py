from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.models.hybrid_connection import HybridConnection
from app.models.license_connection import LicenseConnection
from app.models.platform_connection import PlatformConnection
from app.models.saas_connection import SaaSConnection
from app.shared.core.provider import normalize_provider

CONNECTION_MODEL_PAIRS: tuple[tuple[str, Any], ...] = (
    ("aws", AWSConnection),
    ("azure", AzureConnection),
    ("gcp", GCPConnection),
    ("saas", SaaSConnection),
    ("license", LicenseConnection),
    ("platform", PlatformConnection),
    ("hybrid", HybridConnection),
)
CONNECTION_MODEL_BY_PROVIDER: dict[str, Any] = dict(CONNECTION_MODEL_PAIRS)


def _normalize_providers(
    providers: Iterable[str] | None,
) -> set[str] | None:
    if providers is None:
        return None
    normalized = {str(provider).strip().lower() for provider in providers if provider}
    return normalized or None


def _iter_model_pairs(
    providers: Iterable[str] | None = None,
) -> list[tuple[str, Any]]:
    normalized = _normalize_providers(providers)
    if normalized is None:
        return list(CONNECTION_MODEL_PAIRS)
    return [(provider, model) for provider, model in CONNECTION_MODEL_PAIRS if provider in normalized]


def get_connection_model(provider: str) -> Any | None:
    provider_norm = normalize_provider(provider)
    if not provider_norm:
        return None
    return CONNECTION_MODEL_BY_PROVIDER.get(provider_norm)


def _active_clause_for_model(model: Any) -> Any:
    if hasattr(model, "status"):
        return model.status == "active"
    if hasattr(model, "is_active"):
        return model.is_active.is_(True)
    return sa.true()


async def list_connections(
    db: AsyncSession,
    *,
    tenant_id: UUID | None = None,
    active_only: bool = False,
    with_for_update: bool = False,
    skip_locked: bool = False,
    providers: Iterable[str] | None = None,
) -> list[Any]:
    """
    Provider-agnostic connection loader used by scheduler/jobs.
    """
    connections: list[Any] = []
    for _provider, model in _iter_model_pairs(providers):
        stmt = select(model)
        if tenant_id is not None:
            stmt = stmt.where(model.tenant_id == tenant_id)
        if active_only:
            stmt = stmt.where(_active_clause_for_model(model))
        if with_for_update:
            stmt = stmt.with_for_update(skip_locked=skip_locked)
        result = await db.execute(stmt)
        connections.extend(result.scalars().all())
    return connections


async def list_tenant_connections(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    active_only: bool = False,
    providers: Iterable[str] | None = None,
) -> list[Any]:
    return await list_connections(
        db,
        tenant_id=tenant_id,
        active_only=active_only,
        providers=providers,
    )


async def list_active_connections_all_tenants(
    db: AsyncSession,
    *,
    with_for_update: bool = False,
    skip_locked: bool = False,
    providers: Iterable[str] | None = None,
) -> list[Any]:
    return await list_connections(
        db,
        active_only=True,
        with_for_update=with_for_update,
        skip_locked=skip_locked,
        providers=providers,
    )
