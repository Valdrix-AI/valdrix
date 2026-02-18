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

from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.models.saas_connection import SaaSConnection
from app.models.license_connection import LicenseConnection
from app.models.platform_connection import PlatformConnection
from app.models.hybrid_connection import HybridConnection
from app.shared.adapters.factory import AdapterFactory
from app.shared.core.logging import audit_log

logger = structlog.get_logger()


class CloudConnectionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all_connections(
        self, tenant_id: UUID
    ) -> dict[
        str,
        list[
            AWSConnection
            | AzureConnection
            | GCPConnection
            | SaaSConnection
            | LicenseConnection
            | PlatformConnection
            | HybridConnection
        ],
    ]:
        """Lists all cloud connections for a tenant, grouped by provider."""
        results: dict[
            str,
            list[
                AWSConnection
                | AzureConnection
                | GCPConnection
                | SaaSConnection
                | LicenseConnection
                | PlatformConnection
                | HybridConnection
            ],
        ] = {
            "aws": [],
            "azure": [],
            "gcp": [],
            "saas": [],
            "license": [],
            "platform": [],
            "hybrid": [],
        }

        # AWS
        aws_q = await self.db.execute(
            select(AWSConnection).where(AWSConnection.tenant_id == tenant_id)
        )
        results["aws"] = list(aws_q.scalars().all())

        # Azure
        azure_q = await self.db.execute(
            select(AzureConnection).where(AzureConnection.tenant_id == tenant_id)
        )
        results["azure"] = list(azure_q.scalars().all())

        # GCP
        gcp_q = await self.db.execute(
            select(GCPConnection).where(GCPConnection.tenant_id == tenant_id)
        )
        results["gcp"] = list(gcp_q.scalars().all())

        # SaaS
        saas_q = await self.db.execute(
            select(SaaSConnection).where(SaaSConnection.tenant_id == tenant_id)
        )
        results["saas"] = list(saas_q.scalars().all())

        # License
        license_q = await self.db.execute(
            select(LicenseConnection).where(LicenseConnection.tenant_id == tenant_id)
        )
        results["license"] = list(license_q.scalars().all())

        # Platform
        platform_q = await self.db.execute(
            select(PlatformConnection).where(PlatformConnection.tenant_id == tenant_id)
        )
        results["platform"] = list(platform_q.scalars().all())

        # Hybrid
        hybrid_q = await self.db.execute(
            select(HybridConnection).where(HybridConnection.tenant_id == tenant_id)
        )
        results["hybrid"] = list(hybrid_q.scalars().all())

        return results

    async def verify_connection(
        self, provider: str, connection_id: UUID, tenant_id: UUID
    ) -> dict[str, Any]:
        """
        Generic entry point for connection verification.
        Delegates to provider-specific logic while maintaining a common interface.
        """
        provider_lower = provider.lower()
        if provider_lower not in {
            "aws",
            "azure",
            "gcp",
            "saas",
            "license",
            "platform",
            "hybrid",
        }:
            raise HTTPException(
                status_code=400, detail=f"Unsupported provider: {provider}"
            )

        connection: (
            AWSConnection
            | AzureConnection
            | GCPConnection
            | SaaSConnection
            | LicenseConnection
            | PlatformConnection
            | HybridConnection
            | None
        )
        if provider_lower == "aws":
            result = await self.db.execute(
                select(AWSConnection).where(
                    AWSConnection.id == connection_id,
                    AWSConnection.tenant_id == tenant_id,
                )
            )
        elif provider_lower == "azure":
            result = await self.db.execute(
                select(AzureConnection).where(
                    AzureConnection.id == connection_id,
                    AzureConnection.tenant_id == tenant_id,
                )
            )
        elif provider_lower == "gcp":
            result = await self.db.execute(
                select(GCPConnection).where(
                    GCPConnection.id == connection_id,
                    GCPConnection.tenant_id == tenant_id,
                )
            )
        elif provider_lower == "saas":
            result = await self.db.execute(
                select(SaaSConnection).where(
                    SaaSConnection.id == connection_id,
                    SaaSConnection.tenant_id == tenant_id,
                )
            )
        elif provider_lower == "license":
            result = await self.db.execute(
                select(LicenseConnection).where(
                    LicenseConnection.id == connection_id,
                    LicenseConnection.tenant_id == tenant_id,
                )
            )
        elif provider_lower == "platform":
            result = await self.db.execute(
                select(PlatformConnection).where(
                    PlatformConnection.id == connection_id,
                    PlatformConnection.tenant_id == tenant_id,
                )
            )
        else:
            result = await self.db.execute(
                select(HybridConnection).where(
                    HybridConnection.id == connection_id,
                    HybridConnection.tenant_id == tenant_id,
                )
            )
        connection = result.scalar_one_or_none()

        if not connection:
            raise HTTPException(status_code=404, detail="Connection not found")

        try:
            adapter = AdapterFactory.get_adapter(connection)
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
                    f"{provider}_connection_verified",
                    "system",
                    str(tenant_id),
                    {"id": str(connection_id)},
                )

                return {
                    "status": "active",
                    "provider": provider,
                    "account_id": getattr(
                        connection,
                        "aws_account_id",
                        getattr(
                            connection,
                            "subscription_id",
                            getattr(connection, "project_id", None),
                        ),
                    ),
                }
            else:
                if hasattr(connection, "status"):
                    connection.status = "error"
                if hasattr(connection, "is_active"):
                    connection.is_active = False
                await self.db.commit()
                raise HTTPException(
                    status_code=400, detail=f"{provider.upper()} verification failed"
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
    def get_aws_setup_templates(external_id: str) -> dict[str, str]:
        """AWS specific onboarding templates."""
        return {
            "magic_link": f"https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/create/review?stackName=ValdrixAccess&templateURL=https://valdrix-public.s3.amazonaws.com/templates/aws-access.yaml&param_ExternalId={external_id}",
            "cfn_template": "https://valdrix-public.s3.amazonaws.com/templates/aws-access.yaml",
            "terraform_snippet": (
                'resource "aws_iam_role" "valdrix_access" {\n'
                '  name = "ValdrixAccessRole"\n'
                f'  assume_role_policy = jsonencode({{... external_id = "{external_id}" ...}})\n'
                "}"
            ),
        }
