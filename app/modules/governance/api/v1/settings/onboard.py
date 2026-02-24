from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Dict, Any
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr, Field
import structlog

from app.shared.db.session import get_db
from app.shared.core.logging import audit_log
from app.shared.core.auth import get_current_user_from_jwt, CurrentUser
from app.models.tenant import Tenant, User, UserRole
from app.shared.core.pricing import PricingTier
from app.shared.core.config import get_settings
from app.shared.core.rate_limit import auth_limit
from app.shared.core.provider import normalize_provider
from app.shared.core.turnstile import require_turnstile_for_onboard

logger = structlog.get_logger()


class OnboardRequest(BaseModel):
    tenant_name: str = Field(..., min_length=3, max_length=100)
    admin_email: EmailStr | None = None
    cloud_config: Dict[str, Any] | None = Field(
        None, description="Optional cloud credentials for immediate verification"
    )


class OnboardResponse(BaseModel):
    status: str
    tenant_id: UUID


router = APIRouter(tags=["onboarding"])


@router.post("", response_model=OnboardResponse)
@auth_limit
async def onboard(
    request: Request,
    onboard_req: OnboardRequest,
    user: CurrentUser = Depends(get_current_user_from_jwt),  # No DB check
    db: AsyncSession = Depends(get_db),
    _turnstile: None = Depends(require_turnstile_for_onboard),
) -> OnboardResponse:
    # 1. Check if user already exists
    existing = await db.execute(select(User).where(User.id == user.id))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Already onboarded")

    # 2. Create Tenant on permanent free tier.
    if len(onboard_req.tenant_name) < 3:
        raise HTTPException(400, "Tenant name must be at least 3 characters")

    tenant = Tenant(
        name=onboard_req.tenant_name,
        plan=PricingTier.FREE.value,
    )

    # 3. Active Credential Validation (Hardening)
    if onboard_req.cloud_config:
        settings = get_settings()
        if settings.ENVIRONMENT in ["production", "staging"]:
            forwarded_proto = request.headers.get(
                "x-forwarded-proto", request.url.scheme
            )
            forwarded_proto = (
                forwarded_proto.split(",")[0].strip().lower()
                if forwarded_proto
                else request.url.scheme
            )
            if forwarded_proto != "https":
                raise HTTPException(
                    status_code=400,
                    detail="HTTPS is required when submitting cloud credentials.",
                )

        platform = normalize_provider(onboard_req.cloud_config.get("platform", ""))
        default_aws_region = (
            str(getattr(settings, "AWS_DEFAULT_REGION", "") or "").strip() or "us-east-1"
        )
        logger.info("verifying_initial_cloud_connection", platform=platform)

        try:
            from app.shared.adapters.factory import AdapterFactory
            from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
            from app.shared.adapters.aws_utils import map_aws_connection_to_credentials
            from app.shared.core.exceptions import ConfigurationError
            from app.models.aws_connection import AWSConnection
            from app.models.azure_connection import AzureConnection
            from app.models.gcp_connection import GCPConnection
            from app.models.saas_connection import SaaSConnection
            from app.models.license_connection import LicenseConnection
            from app.models.platform_connection import PlatformConnection
            from app.models.hybrid_connection import HybridConnection

            def _as_dict(value: Any) -> dict[str, Any]:
                return value if isinstance(value, dict) else {}

            def _as_list(value: Any) -> list[dict[str, Any]]:
                return value if isinstance(value, list) else []

            def _build_verification_adapter(
                temp_platform: str, temp_connection: Any
            ) -> Any:
                """
                Build onboarding verification adapter.

                AWS onboarding verification must work before CUR is configured.
                """
                if temp_platform != "aws":
                    return AdapterFactory.get_adapter(temp_connection)

                try:
                    return AdapterFactory.get_adapter(temp_connection)
                except ConfigurationError as exc:
                    if "CUR" not in str(exc):
                        raise
                    return MultiTenantAWSAdapter(
                        map_aws_connection_to_credentials(temp_connection)
                    )

            verification_tenant_id = UUID("00000000-0000-0000-0000-000000000000")

            # Create an in-memory connection object for preflight verification.
            conn: Any = None
            if platform == "aws":
                conn = AWSConnection(
                    role_arn=onboard_req.cloud_config.get("role_arn"),
                    external_id=onboard_req.cloud_config.get("external_id"),
                    region=onboard_req.cloud_config.get(
                        "region",
                        default_aws_region,
                    ),
                    aws_account_id=onboard_req.cloud_config.get(
                        "aws_account_id", "000000000000"
                    ),
                    tenant_id=verification_tenant_id,
                )
            elif platform == "azure":
                conn = AzureConnection(
                    client_id=onboard_req.cloud_config.get("client_id"),
                    client_secret=onboard_req.cloud_config.get("client_secret"),
                    azure_tenant_id=onboard_req.cloud_config.get("azure_tenant_id"),
                    subscription_id=onboard_req.cloud_config.get("subscription_id"),
                    tenant_id=verification_tenant_id,
                )
            elif platform == "gcp":
                conn = GCPConnection(
                    project_id=onboard_req.cloud_config.get("project_id"),
                    service_account_json=onboard_req.cloud_config.get(
                        "service_account_json"
                    ),
                    tenant_id=verification_tenant_id,
                )
            elif platform == "saas":
                conn = SaaSConnection(
                    name=str(onboard_req.cloud_config.get("name") or "onboarding-saas"),
                    vendor=str(onboard_req.cloud_config.get("vendor") or "saas"),
                    auth_method=str(
                        onboard_req.cloud_config.get("auth_method") or "manual"
                    ),
                    api_key=onboard_req.cloud_config.get("api_key"),
                    connector_config=_as_dict(
                        onboard_req.cloud_config.get("connector_config")
                    ),
                    spend_feed=_as_list(onboard_req.cloud_config.get("spend_feed")),
                    tenant_id=verification_tenant_id,
                )
            elif platform == "license":
                conn = LicenseConnection(
                    name=str(
                        onboard_req.cloud_config.get("name") or "onboarding-license"
                    ),
                    vendor=str(onboard_req.cloud_config.get("vendor") or "license"),
                    auth_method=str(
                        onboard_req.cloud_config.get("auth_method") or "manual"
                    ),
                    api_key=onboard_req.cloud_config.get("api_key"),
                    connector_config=_as_dict(
                        onboard_req.cloud_config.get("connector_config")
                    ),
                    license_feed=_as_list(onboard_req.cloud_config.get("license_feed")),
                    tenant_id=verification_tenant_id,
                )
            elif platform == "platform":
                conn = PlatformConnection(
                    name=str(
                        onboard_req.cloud_config.get("name") or "onboarding-platform"
                    ),
                    vendor=str(onboard_req.cloud_config.get("vendor") or "platform"),
                    auth_method=str(
                        onboard_req.cloud_config.get("auth_method") or "manual"
                    ),
                    api_key=onboard_req.cloud_config.get("api_key"),
                    api_secret=onboard_req.cloud_config.get("api_secret"),
                    connector_config=_as_dict(
                        onboard_req.cloud_config.get("connector_config")
                    ),
                    spend_feed=_as_list(onboard_req.cloud_config.get("spend_feed")),
                    tenant_id=verification_tenant_id,
                )
            elif platform == "hybrid":
                conn = HybridConnection(
                    name=str(
                        onboard_req.cloud_config.get("name") or "onboarding-hybrid"
                    ),
                    vendor=str(onboard_req.cloud_config.get("vendor") or "hybrid"),
                    auth_method=str(
                        onboard_req.cloud_config.get("auth_method") or "manual"
                    ),
                    api_key=onboard_req.cloud_config.get("api_key"),
                    api_secret=onboard_req.cloud_config.get("api_secret"),
                    connector_config=_as_dict(
                        onboard_req.cloud_config.get("connector_config")
                    ),
                    spend_feed=_as_list(onboard_req.cloud_config.get("spend_feed")),
                    tenant_id=verification_tenant_id,
                )
            else:
                raw_platform = onboard_req.cloud_config.get("platform")
                raise HTTPException(400, f"Unsupported platform: {raw_platform}")

            if conn:
                adapter = _build_verification_adapter(platform, conn)
                if not await adapter.verify_connection():
                    raise HTTPException(
                        400,
                        f"Cloud connection verification failed for {platform}. Please check your credentials.",
                    )
                logger.info("cloud_connection_verified_successfully", platform=platform)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "onboarding_verification_error", platform=platform, error=str(e)
            )
            raise HTTPException(400, f"Error verifying {platform} connection: {str(e)}")

    db.add(tenant)
    await db.flush()  # Get tenant.id

    # 3. Create User linked to Tenant
    new_user = User(
        id=user.id, email=user.email, tenant_id=tenant.id, role=UserRole.OWNER
    )
    db.add(new_user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        logger.warning(
            "onboarding_race_detected_user_already_exists", user_id=str(user.id)
        )
        raise HTTPException(400, "Already onboarded") from exc

    # 4. Audit Log
    audit_log(
        event="tenant_onboarded",
        user_id=str(user.id),
        tenant_id=str(tenant.id),
        details={"tenant_name": onboard_req.tenant_name},
    )

    return OnboardResponse(status="onboarded", tenant_id=tenant.id)
