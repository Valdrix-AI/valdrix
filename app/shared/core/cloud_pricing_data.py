"""DB-backed cloud resource pricing catalog with safe default seeding."""

from __future__ import annotations

import json
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.shared.core.pricing_defaults import DEFAULT_RATES, REGION_MULTIPLIERS

logger = structlog.get_logger()

CLOUD_PRICING_REFRESH_RECOVERABLE_EXCEPTIONS = (
    SQLAlchemyError,
    RuntimeError,
    TypeError,
    ValueError,
    AttributeError,
    OSError,
    ImportError,
)

_CLOUD_PRICING_CACHE: dict[tuple[str, str, str, str], float] = {}


def _normalize_key(value: Any, *, default: str = "") -> str:
    normalized = str(value or default).strip().lower()
    return normalized or default


def _normalize_size(value: Any) -> str:
    return _normalize_key(value, default="default")


def _safe_rate(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    return float(value or 0.0)


def _cache_key(
    provider: str,
    resource_type: str,
    resource_size: str,
    region: str,
) -> tuple[str, str, str, str]:
    return (
        _normalize_key(provider),
        _normalize_key(resource_type),
        _normalize_size(resource_size),
        _normalize_key(region, default="global"),
    )


def get_cloud_hourly_rate(
    provider: str,
    resource_type: str,
    resource_size: str | None = None,
    region: str = "global",
) -> float:
    normalized_provider = _normalize_key(provider)
    normalized_type = _normalize_key(resource_type)
    normalized_size = _normalize_size(resource_size)
    normalized_region = _normalize_key(region, default="global")

    exact_key = _cache_key(
        normalized_provider, normalized_type, normalized_size, normalized_region
    )
    default_region_key = _cache_key(
        normalized_provider, normalized_type, "default", normalized_region
    )
    global_key = _cache_key(normalized_provider, normalized_type, normalized_size, "global")
    global_default_key = _cache_key(
        normalized_provider, normalized_type, "default", "global"
    )

    if exact_key in _CLOUD_PRICING_CACHE:
        return _CLOUD_PRICING_CACHE[exact_key]
    if default_region_key in _CLOUD_PRICING_CACHE:
        return _CLOUD_PRICING_CACHE[default_region_key]

    base_rate = _CLOUD_PRICING_CACHE.get(global_key)
    if base_rate is None:
        base_rate = _CLOUD_PRICING_CACHE.get(global_default_key)
    if base_rate is None:
        logger.debug(
            "cloud_pricing_missing",
            provider=provider,
            resource_type=resource_type,
            resource_size=resource_size,
            region=region,
        )
        return 0.0

    multiplier = REGION_MULTIPLIERS.get(normalized_region, 1.0)
    return float(base_rate) * float(multiplier)


def _flatten_default_rates() -> list[dict[str, Any]]:
    seed_records: list[dict[str, Any]] = []
    for provider, resource_map in DEFAULT_RATES.items():
        for resource_type, resource_value in resource_map.items():
            if isinstance(resource_value, dict):
                for resource_size, hourly_rate in resource_value.items():
                    seed_records.append(
                        {
                            "provider": _normalize_key(provider),
                            "resource_type": _normalize_key(resource_type),
                            "resource_size": _normalize_size(resource_size),
                            "region": "global",
                            "hourly_rate_usd": _safe_rate(hourly_rate),
                            "source": "default_catalog",
                        }
                    )
            else:
                seed_records.append(
                    {
                        "provider": _normalize_key(provider),
                        "resource_type": _normalize_key(resource_type),
                        "resource_size": "default",
                        "region": "global",
                        "hourly_rate_usd": _safe_rate(resource_value),
                        "source": "default_catalog",
                    }
                )
    return seed_records


async def _upsert_catalog_records(*, db_session: Any, records: Iterable[dict[str, Any]]) -> int:
    from app.models.pricing import CloudResourcePricing

    updated = 0
    for record in records:
        stmt = select(CloudResourcePricing).where(
            CloudResourcePricing.provider == record["provider"],
            CloudResourcePricing.resource_type == record["resource_type"],
            CloudResourcePricing.resource_size == record["resource_size"],
            CloudResourcePricing.region == record["region"],
        )
        existing = (await db_session.execute(stmt)).scalar_one_or_none()
        if existing is None:
            db_session.add(CloudResourcePricing(**record))
            updated += 1
            continue
        existing.hourly_rate_usd = record["hourly_rate_usd"]
        existing.source = record["source"]
        existing.is_active = True
        updated += 1
    return updated


async def seed_default_cloud_pricing_catalog(db_session: Any = None) -> int:
    """Persist the checked-in default cloud pricing catalog to the database."""
    from app.shared.db.session import async_session_maker, mark_session_system_context

    async def _seed(session: Any, *, commit: bool) -> int:
        updated = await _upsert_catalog_records(
            db_session=session,
            records=_flatten_default_rates(),
        )
        if commit:
            await session.commit()
        else:
            await session.flush()
        return updated

    if db_session is None:
        async with async_session_maker() as session:
            await mark_session_system_context(session)
            return await _seed(session, commit=True)
    return await _seed(db_session, commit=False)


def _refresh_cache_from_rows(rows: Iterable[Any]) -> int:
    _CLOUD_PRICING_CACHE.clear()
    count = 0
    for row in rows:
        _CLOUD_PRICING_CACHE[
            _cache_key(
                getattr(row, "provider", None),
                getattr(row, "resource_type", None),
                getattr(row, "resource_size", None),
                getattr(row, "region", None),
            )
        ] = _safe_rate(getattr(row, "hourly_rate_usd", 0.0))
        count += 1
    return count


async def refresh_cloud_resource_pricing(db_session: Any = None) -> int:
    """Refresh the in-memory pricing cache from the persisted catalog, seeding defaults if empty."""
    from app.models.pricing import CloudResourcePricing
    from app.shared.db.session import async_session_maker, mark_session_system_context

    async def _refresh(session: Any) -> int:
        stmt = select(CloudResourcePricing).where(CloudResourcePricing.is_active.is_(True))
        rows = (await session.execute(stmt)).scalars().all()
        if not rows:
            await seed_default_cloud_pricing_catalog(session)
            rows = (await session.execute(stmt)).scalars().all()
        refreshed = _refresh_cache_from_rows(rows)
        logger.info("cloud_pricing_cache_refreshed", record_count=refreshed)
        return refreshed

    try:
        if db_session is None:
            async with async_session_maker() as session:
                await mark_session_system_context(session)
                return await _refresh(session)
        return await _refresh(db_session)
    except CLOUD_PRICING_REFRESH_RECOVERABLE_EXCEPTIONS as exc:
        logger.error("cloud_pricing_refresh_failed", error=str(exc))
        return 0


def _extract_aws_hourly_rate(price_list: list[str]) -> float | None:
    for raw_entry in price_list:
        try:
            payload = json.loads(raw_entry)
        except json.JSONDecodeError:
            continue
        on_demand_terms = payload.get("terms", {}).get("OnDemand", {})
        for term in on_demand_terms.values():
            dimensions = term.get("priceDimensions", {})
            for dimension in dimensions.values():
                usd_value = dimension.get("pricePerUnit", {}).get("USD")
                try:
                    rate = float(usd_value)
                except (TypeError, ValueError):
                    continue
                if rate >= 0:
                    return rate
    return None


async def sync_supported_aws_pricing(db_session: Any = None, *, client: Any = None) -> int:
    """
    Persist supported AWS Pricing API observations into the catalog.

    The repository currently supports a verified NAT Gateway catalog probe because
    that query shape already existed in the codebase before this remediation.
    """
    from app.shared.db.session import async_session_maker, mark_session_system_context

    try:
        import boto3
    except ImportError as exc:
        logger.error("aws_pricing_sync_failed", error=str(exc))
        return 0

    pricing_client = client or boto3.client("pricing", region_name="us-east-1")
    response: dict[str, Any] = pricing_client.get_products(
        ServiceCode="AmazonEC2",
        Filters=[
            {"Type": "TERM_MATCH", "Field": "usageType", "Value": "NatGateway-Hours"},
            {"Type": "TERM_MATCH", "Field": "location", "Value": "US East (N. Virginia)"},
        ],
    )
    rate = _extract_aws_hourly_rate(list(response.get("PriceList", []) or []))
    if rate is None:
        logger.warning("aws_pricing_sync_no_supported_rates_found")
        return 0

    record = {
        "provider": "aws",
        "resource_type": "nat_gateway",
        "resource_size": "default",
        "region": "us-east-1",
        "hourly_rate_usd": rate,
        "source": "aws_pricing_api",
    }

    async def _sync(session: Any, *, commit: bool) -> int:
        updated = await _upsert_catalog_records(db_session=session, records=[record])
        if commit:
            await session.commit()
        else:
            await session.flush()
        await refresh_cloud_resource_pricing(session)
        logger.info(
            "aws_pricing_sync_completed",
            supported_records=updated,
            hourly_rate_usd=rate,
        )
        return updated

    try:
        if db_session is None:
            async with async_session_maker() as session:
                await mark_session_system_context(session)
                return await _sync(session, commit=True)
        return await _sync(db_session, commit=False)
    except CLOUD_PRICING_REFRESH_RECOVERABLE_EXCEPTIONS as exc:
        logger.error("aws_pricing_sync_failed", error=str(exc))
        return 0


__all__ = [
    "CLOUD_PRICING_REFRESH_RECOVERABLE_EXCEPTIONS",
    "get_cloud_hourly_rate",
    "refresh_cloud_resource_pricing",
    "seed_default_cloud_pricing_catalog",
    "sync_supported_aws_pricing",
]
