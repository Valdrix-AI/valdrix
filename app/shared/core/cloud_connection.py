"""
Cloud Connection Service - Unified Cloud Account Management

Centralizes:
- Listing connections.
- Verifying connections (delegating to adapters).
- Onboarding templates.
"""

from uuid import UUID
from typing import Any
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from app.shared.adapters.factory import AdapterFactory
from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
from app.shared.adapters.aws_utils import map_aws_connection_to_credentials
from app.shared.core.connection_queries import (
    CONNECTION_MODEL_PAIRS,
    get_connection_model,
    list_tenant_connections,
)
from app.shared.core.config import get_settings
from app.shared.core.logging import audit_log
from app.shared.core.provider import normalize_provider, resolve_provider_from_connection

logger = structlog.get_logger()


class CloudConnectionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _build_verification_adapter(provider: str, connection: Any) -> Any:
        """
        Build a verification adapter for a connection.

        AWS verification must validate STS assume-role even before CUR is configured,
        so it intentionally bypasses CUR-only adapter selection.
        """
        if provider == "aws":
            return MultiTenantAWSAdapter(map_aws_connection_to_credentials(connection))
        return AdapterFactory.get_adapter(connection)

    async def list_all_connections(
        self, tenant_id: UUID
    ) -> dict[str, list[Any]]:
        """Lists all cloud connections for a tenant, grouped by provider."""
        results: dict[str, list[Any]] = {
            provider: [] for provider, _ in CONNECTION_MODEL_PAIRS
        }
        connections = await list_tenant_connections(self.db, tenant_id, active_only=False)
        for connection in connections:
            provider = normalize_provider(resolve_provider_from_connection(connection))
            if provider in results:
                results[provider].append(connection)

        return results

    async def verify_connection(
        self, provider: str, connection_id: UUID, tenant_id: UUID
    ) -> dict[str, Any]:
        """
        Generic entry point for connection verification.
        Delegates to provider-specific logic while maintaining a common interface.
        """
        provider_norm = normalize_provider(provider)
        if not provider_norm:
            raise HTTPException(
                status_code=400, detail=f"Unsupported provider: {provider}"
            )

        model = get_connection_model(provider_norm)
        if model is None:
            raise HTTPException(
                status_code=400, detail=f"Unsupported provider: {provider}"
            )
        result = await self.db.execute(
            select(model).where(model.id == connection_id, model.tenant_id == tenant_id)
        )
        connection = result.scalar_one_or_none()

        if not connection:
            raise HTTPException(status_code=404, detail="Connection not found")

        try:
            adapter = self._build_verification_adapter(provider_norm, connection)
            is_valid = await adapter.verify_connection()

            from datetime import datetime, timezone

            if is_valid:
                # Update status based on model fields (most have status or is_active)
                if hasattr(connection, "status"):
                    connection.status = "active"
                if hasattr(connection, "is_active"):
                    connection.is_active = True

                if hasattr(connection, "last_verified_at"):
                    connection.last_verified_at = datetime.now(timezone.utc)
                if hasattr(connection, "last_synced_at"):
                    connection.last_synced_at = datetime.now(timezone.utc)

                if hasattr(connection, "error_message"):
                    connection.error_message = None

                await self.db.commit()
                audit_log(
                    f"{provider_norm}_connection_verified",
                    "system",
                    str(tenant_id),
                    {"id": str(connection_id)},
                )

                return {
                    "status": "active",
                    "provider": provider_norm,
                    "account_id": self._resolve_connection_reference(connection),
                }
            else:
                if hasattr(connection, "status"):
                    connection.status = "error"
                if hasattr(connection, "is_active"):
                    connection.is_active = False
                await self.db.commit()
                raise HTTPException(
                    status_code=400,
                    detail=f"{provider_norm.upper()} verification failed",
                )

        except HTTPException:
            raise
        except Exception as e:
            from app.shared.core.exceptions import AdapterError
            adapter_err = AdapterError(str(e))
            
            logger.error(
                "provider_verification_failed",
                provider=provider,
                error=str(e),
                connection_id=str(connection_id),
            )
            # Update status
            if connection:
                if hasattr(connection, "status"):
                    connection.status = "error"
                if hasattr(connection, "error_message"):
                    connection.error_message = adapter_err.message
                if hasattr(connection, "is_active"):
                    connection.is_active = False
            await self.db.commit()

            # Raise sanitized exception (Finding #2)
            raise adapter_err

    @staticmethod
    def _resolve_connection_reference(connection: Any) -> str | None:
        """
        Return the most useful provider-specific connection reference for API clients.

        Priority:
        - core-cloud native identifiers
        - Cloud+ vendor/name
        - connection UUID
        """
        for attr in ("aws_account_id", "subscription_id", "project_id", "vendor", "name"):
            value = getattr(connection, attr, None)
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned:
                    return cleaned
        connection_id = getattr(connection, "id", None)
        return str(connection_id) if connection_id is not None else None

    @staticmethod
    def _resolve_aws_console_region() -> str:
        settings = get_settings()
        configured = str(getattr(settings, "AWS_DEFAULT_REGION", "") or "").strip()
        supported = {
            str(region).strip()
            for region in getattr(settings, "AWS_SUPPORTED_REGIONS", [])
            if str(region).strip()
        }
        if configured and configured in supported:
            return configured
        return "us-east-1"

    @staticmethod
    def get_aws_setup_templates(external_id: str) -> dict[str, str]:
        """AWS specific onboarding templates."""
        console_region = CloudConnectionService._resolve_aws_console_region()
        return {
            "magic_link": f"https://console.aws.amazon.com/cloudformation/home?region={console_region}#/stacks/create/review?stackName=ValdrixAccess&templateURL=https://valdrix-public.s3.amazonaws.com/templates/aws-access.yaml&param_ExternalId={external_id}",
            "cfn_template": "https://valdrix-public.s3.amazonaws.com/templates/aws-access.yaml",
            "terraform_snippet": (
                'resource "aws_iam_role" "valdrix_access" {\n'
                '  name = "ValdrixAccessRole"\n'
                f'  assume_role_policy = jsonencode({{... external_id = "{external_id}" ...}})\n'
                "}"
            ),
        }
