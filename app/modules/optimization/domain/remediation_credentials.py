from __future__ import annotations

import json
from typing import Any

import structlog
from sqlalchemy import select

from app.models.remediation import RemediationRequest
from app.shared.core.connection_queries import get_connection_model
from app.shared.core.connection_state import resolve_connection_region
from app.shared.core.provider import normalize_provider

logger = structlog.get_logger()


async def resolve_connection_credentials(
    service: Any,
    request: RemediationRequest,
) -> dict[str, Any]:
    """
    Resolve provider credentials from the tenant connection bound to the request.

    `service` is a `RemediationService` instance (passed as `Any` to avoid import cycles).
    """
    provider = normalize_provider(getattr(request, "provider", None))
    tenant_id = getattr(request, "tenant_id", None)
    connection_id = getattr(request, "connection_id", None)
    fallback_credentials = dict(service.credentials or {})
    missing_connection_result = fallback_credentials if not connection_id else {}

    if tenant_id is None:
        return fallback_credentials
    if not provider:
        return fallback_credentials

    connection_model = get_connection_model(provider)
    if connection_model is None:
        return fallback_credentials

    def _coerce_dict(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    def _coerce_list(value: Any) -> list[Any]:
        return list(value) if isinstance(value, list) else []

    stmt = select(connection_model).where(connection_model.tenant_id == tenant_id)
    if connection_id:
        stmt = stmt.where(connection_model.id == connection_id)
    else:
        if hasattr(connection_model, "status"):
            stmt = stmt.where(connection_model.status == "active")
        elif hasattr(connection_model, "is_active"):
            stmt = stmt.where(connection_model.is_active.is_(True))

        order_clauses = []
        if hasattr(connection_model, "last_verified_at"):
            order_clauses.append(connection_model.last_verified_at.desc())
        order_clauses.append(connection_model.id.desc())
        stmt = stmt.order_by(*order_clauses)

    result = await service.db.execute(stmt)
    connection = await service._scalar_one_or_none(result)
    if connection is None:
        return missing_connection_result

    if provider == "aws":
        role_arn = getattr(connection, "role_arn", None)
        external_id = getattr(connection, "external_id", None)
        if not role_arn or not external_id:
            return missing_connection_result
        connection_region = resolve_connection_region(connection)
        return {
            "role_arn": role_arn,
            "external_id": external_id,
            "region": connection_region,
            "connection_id": str(getattr(connection, "id", connection_id or "")),
        }

    if provider == "azure":
        tenant = getattr(connection, "azure_tenant_id", None)
        client_id = getattr(connection, "client_id", None)
        client_secret = getattr(connection, "client_secret", None)
        subscription_id = getattr(connection, "subscription_id", None)
        if not all([tenant, client_id, client_secret, subscription_id]):
            return missing_connection_result
        return {
            "tenant_id": tenant,
            "client_id": client_id,
            "client_secret": client_secret,
            "subscription_id": subscription_id,
            "region": resolve_connection_region(connection),
            "connection_id": str(getattr(connection, "id", connection_id or "")),
        }

    if provider == "gcp":
        service_account_json = getattr(connection, "service_account_json", None)
        if isinstance(service_account_json, dict):
            payload = dict(service_account_json)
            payload.setdefault(
                "connection_id",
                str(getattr(connection, "id", connection_id or "")),
            )
            payload.setdefault("region", resolve_connection_region(connection))
            return payload
        if isinstance(service_account_json, str) and service_account_json.strip():
            try:
                parsed = json.loads(service_account_json)
                if isinstance(parsed, dict):
                    payload = dict(parsed)
                    payload.setdefault(
                        "connection_id",
                        str(getattr(connection, "id", connection_id or "")),
                    )
                    payload.setdefault("region", resolve_connection_region(connection))
                    return payload
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "remediation_invalid_gcp_service_account_json",
                    connection_id=str(connection_id),
                    error=str(exc),
                )
        return missing_connection_result

    if provider == "saas":
        return {
            "vendor": getattr(connection, "vendor", None),
            "auth_method": getattr(connection, "auth_method", None),
            "api_key": getattr(connection, "api_key", None),
            "connector_config": _coerce_dict(
                getattr(connection, "connector_config", None)
            ),
            "spend_feed": _coerce_list(getattr(connection, "spend_feed", None)),
            "connection_id": str(getattr(connection, "id", connection_id or "")),
            "region": resolve_connection_region(connection),
        }

    if provider == "license":
        return {
            "vendor": getattr(connection, "vendor", None),
            "auth_method": getattr(connection, "auth_method", None),
            "api_key": getattr(connection, "api_key", None),
            "connector_config": _coerce_dict(
                getattr(connection, "connector_config", None)
            ),
            "license_feed": _coerce_list(getattr(connection, "license_feed", None)),
            "connection_id": str(getattr(connection, "id", connection_id or "")),
            "region": resolve_connection_region(connection),
        }

    if provider == "platform":
        return {
            "vendor": getattr(connection, "vendor", None),
            "auth_method": getattr(connection, "auth_method", None),
            "api_key": getattr(connection, "api_key", None),
            "api_secret": getattr(connection, "api_secret", None),
            "connector_config": _coerce_dict(
                getattr(connection, "connector_config", None)
            ),
            "spend_feed": _coerce_list(getattr(connection, "spend_feed", None)),
            "connection_id": str(getattr(connection, "id", connection_id or "")),
            "region": resolve_connection_region(connection),
        }

    if provider == "hybrid":
        return {
            "vendor": getattr(connection, "vendor", None),
            "auth_method": getattr(connection, "auth_method", None),
            "api_key": getattr(connection, "api_key", None),
            "api_secret": getattr(connection, "api_secret", None),
            "connector_config": _coerce_dict(
                getattr(connection, "connector_config", None)
            ),
            "spend_feed": _coerce_list(getattr(connection, "spend_feed", None)),
            "connection_id": str(getattr(connection, "id", connection_id or "")),
            "region": resolve_connection_region(connection),
        }

    return fallback_credentials
