import uuid
from enum import Enum
import inspect
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Union, cast

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.modules.governance.domain.security.auth import CurrentUser

from fastapi import HTTPException, status

import structlog

logger = structlog.get_logger()

__all__ = [
    "PricingTier",
    "FeatureFlag",
    "TIER_CONFIG",
    "normalize_tier",
    "get_tier_config",
    "is_feature_enabled",
    "get_tier_limit",
    "requires_tier",
    "requires_feature",
    "get_tenant_tier",
    "TierGuard",
]


class PricingTier(str, Enum):
    """Available subscription tiers."""

    FREE = "free"
    STARTER = "starter"
    GROWTH = "growth"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class FeatureFlag(str, Enum):
    """Feature flags for tier gating."""

    DASHBOARDS = "dashboards"
    COST_TRACKING = "cost_tracking"
    ALERTS = "alerts"
    SLACK_INTEGRATION = "slack_integration"
    ZOMBIE_SCAN = "zombie_scan"
    LLM_ANALYSIS = "llm_analysis"
    AI_INSIGHTS = "ai_insights"
    MULTI_CLOUD = "multi_cloud"
    MULTI_REGION = "multi_region"
    GREENOPS = "greenops"
    CARBON_TRACKING = "carbon_tracking"
    AUTO_REMEDIATION = "auto_remediation"
    API_ACCESS = "api_access"
    FORECASTING = "forecasting"
    SSO = "sso"
    SCIM = "scim"
    DEDICATED_SUPPORT = "dedicated_support"
    AUDIT_LOGS = "audit_logs"
    HOURLY_SCANS = "hourly_scans"
    AI_ANALYSIS_DETAILED = "ai_analysis_detailed"
    DOMAIN_DISCOVERY = "domain_discovery"
    IDP_DEEP_SCAN = "idp_deep_scan"
    PRECISION_DISCOVERY = "precision_discovery"
    OWNER_ATTRIBUTION = "owner_attribution"
    GITOPS_REMEDIATION = "gitops_remediation"
    UNIT_ECONOMICS = "unit_economics"
    INGESTION_SLA = "ingestion_sla"
    INGESTION_BACKFILL = "ingestion_backfill"
    ANOMALY_DETECTION = "anomaly_detection"
    CHARGEBACK = "chargeback"
    RECONCILIATION = "reconciliation"
    CLOSE_WORKFLOW = "close_workflow"
    CARBON_ASSURANCE = "carbon_assurance"
    CLOUD_PLUS_CONNECTORS = "cloud_plus_connectors"
    COMPLIANCE_EXPORTS = "compliance_exports"
    SAVINGS_PROOF = "savings_proof"
    COMMITMENT_OPTIMIZATION = "commitment_optimization"
    POLICY_PREVIEW = "policy_preview"
    POLICY_CONFIGURATION = "policy_configuration"
    ESCALATION_WORKFLOW = "escalation_workflow"
    INCIDENT_INTEGRATIONS = "incident_integrations"


# Tier configuration - USD pricing
TIER_CONFIG: dict[PricingTier, dict[str, Any]] = {
    PricingTier.FREE: {
        "name": "Free",
        "price_usd": 0,
        "features": {
            FeatureFlag.DASHBOARDS,
            FeatureFlag.COST_TRACKING,
            FeatureFlag.ALERTS,
            FeatureFlag.ZOMBIE_SCAN,
            FeatureFlag.LLM_ANALYSIS,
            FeatureFlag.DOMAIN_DISCOVERY,
            FeatureFlag.GREENOPS,
            FeatureFlag.CARBON_TRACKING,
            FeatureFlag.UNIT_ECONOMICS,
        },
        "limits": {
            "max_aws_accounts": 1,
            "max_azure_tenants": 0,
            "max_gcp_projects": 0,
            "max_saas_connections": 0,
            "max_license_connections": 0,
            "max_platform_connections": 0,
            "max_hybrid_connections": 0,
            "byok_enabled": True,
            "ai_insights_per_month": 0,
            "scan_frequency_hours": 168,
            "zombie_scans_per_day": 1,
            "llm_analyses_per_day": 1,
            "llm_analyses_per_user_per_day": 1,
            "llm_system_analyses_per_day": 1,
            "llm_analysis_max_records": 128,
            "llm_analysis_max_window_days": 31,
            "llm_prompt_max_input_tokens": 2048,
            "llm_output_max_tokens": 512,
            "max_backfill_days": 0,
            "retention_days": 30,
        },
        "description": "Permanent free plan with core FinOps visibility and capped AI usage.",
        "cta": "Start Free",
        "display_features": [
            "Single cloud provider (AWS) + core dashboards",
            "Weekly zombie scans + basic alerts",
            "1 AI analysis/day",
            "BYOK supported (no platform surcharge)",
            "30-day data retention",
            "Entry-tier limits with no credit card",
        ],
    },
    PricingTier.STARTER: {
        "name": "Starter",
        "price_usd": {"monthly": 29, "annual": 290},
        "paystack_amount_kobo": {"monthly": 4125000, "annual": 41250000},
        "features": {
            FeatureFlag.DASHBOARDS,
            FeatureFlag.COST_TRACKING,
            FeatureFlag.ALERTS,
            FeatureFlag.ZOMBIE_SCAN,
            FeatureFlag.AI_INSIGHTS,
            FeatureFlag.LLM_ANALYSIS,
            FeatureFlag.DOMAIN_DISCOVERY,
            FeatureFlag.MULTI_REGION,
            FeatureFlag.CARBON_TRACKING,
            FeatureFlag.GREENOPS,
            FeatureFlag.UNIT_ECONOMICS,
            FeatureFlag.INGESTION_SLA,
        },
        "limits": {
            "max_aws_accounts": 5,
            "max_azure_tenants": 0,
            "max_gcp_projects": 0,
            "max_saas_connections": 0,
            "max_license_connections": 0,
            "max_platform_connections": 0,
            "max_hybrid_connections": 0,
            "byok_enabled": True,
            "ai_insights_per_month": 10,
            "llm_analyses_per_day": 5,
            "llm_analyses_per_user_per_day": 2,
            "llm_system_analyses_per_day": 2,
            "llm_analysis_max_records": 256,
            "llm_analysis_max_window_days": 90,
            "llm_prompt_max_input_tokens": 4096,
            "llm_output_max_tokens": 1024,
            "max_backfill_days": 0,
            "scan_frequency_hours": 24,
            "retention_days": 90,
        },
        "description": "For small teams getting started with cloud cost visibility.",
        "cta": "Start with Starter",
        "display_features": [
            "Includes all Free features",
            "Multi-account support",
            "Advanced budget alerts",
            "5 AI analyses/day",
            "BYOK supported (no platform surcharge)",
            "Unit economics KPIs + ingestion SLA monitor",
            "Multi-region analysis",
            "90-day data retention",
        ],
    },
    PricingTier.GROWTH: {
        "name": "Growth",
        "price_usd": {"monthly": 79, "annual": 790},
        "paystack_amount_kobo": {
            "monthly": 11250000,  # ₦112,500
            "annual": 112500000,  # ₦1,125,000
        },
        "features": {
            FeatureFlag.DASHBOARDS,
            FeatureFlag.COST_TRACKING,
            FeatureFlag.ALERTS,
            FeatureFlag.ZOMBIE_SCAN,
            FeatureFlag.AI_INSIGHTS,
            FeatureFlag.LLM_ANALYSIS,
            FeatureFlag.DOMAIN_DISCOVERY,
            FeatureFlag.MULTI_CLOUD,
            FeatureFlag.MULTI_REGION,
            FeatureFlag.CARBON_TRACKING,
            FeatureFlag.GREENOPS,
            FeatureFlag.AUTO_REMEDIATION,
            FeatureFlag.PRECISION_DISCOVERY,
            FeatureFlag.OWNER_ATTRIBUTION,
            FeatureFlag.CHARGEBACK,
            FeatureFlag.INGESTION_SLA,
            FeatureFlag.INGESTION_BACKFILL,
            FeatureFlag.ANOMALY_DETECTION,
            FeatureFlag.UNIT_ECONOMICS,
            FeatureFlag.POLICY_PREVIEW,
            FeatureFlag.ESCALATION_WORKFLOW,
            FeatureFlag.COMMITMENT_OPTIMIZATION,
        },
        "limits": {
            "max_aws_accounts": 20,
            "max_azure_tenants": 10,
            "max_gcp_projects": 15,
            "max_saas_connections": 0,
            "max_license_connections": 0,
            "max_platform_connections": 0,
            "max_hybrid_connections": 0,
            "byok_enabled": True,
            "llm_analyses_per_day": 20,
            "llm_analyses_per_user_per_day": 8,
            "llm_system_analyses_per_day": 5,
            "llm_analysis_max_records": 1024,
            "llm_analysis_max_window_days": 365,
            "llm_prompt_max_input_tokens": 12288,
            "llm_output_max_tokens": 2048,
            "max_backfill_days": 180,
            "retention_days": 365,
        },
        "description": "For growing teams who need AI-powered cost intelligence.",
        "cta": "Start with Growth",
        "display_features": [
            "Includes all Starter features",
            "AI-driven savings analyses",
            "Chargeback/showback workflows",
            "Historical ingestion backfill",
            "Custom remediation guides",
            "BYOK supported (no platform surcharge)",
            "Full multi-cloud support",
            "1-year data retention",
        ],
    },
    PricingTier.PRO: {
        "name": "Pro",
        "price_usd": {"monthly": 199, "annual": 1990},
        "paystack_amount_kobo": {
            "monthly": 28500000,  # ₦285,000
            "annual": 285000000,  # ₦2,850,000
        },
        "features": {
            FeatureFlag.DASHBOARDS,
            FeatureFlag.COST_TRACKING,
            FeatureFlag.ALERTS,
            FeatureFlag.ZOMBIE_SCAN,
            FeatureFlag.AI_INSIGHTS,
            FeatureFlag.LLM_ANALYSIS,
            FeatureFlag.DOMAIN_DISCOVERY,
            FeatureFlag.IDP_DEEP_SCAN,
            FeatureFlag.MULTI_CLOUD,
            FeatureFlag.MULTI_REGION,
            FeatureFlag.CARBON_TRACKING,
            FeatureFlag.GREENOPS,
            FeatureFlag.AUTO_REMEDIATION,
            FeatureFlag.SSO,
            FeatureFlag.API_ACCESS,
            FeatureFlag.DEDICATED_SUPPORT,
            FeatureFlag.HOURLY_SCANS,
            FeatureFlag.AI_ANALYSIS_DETAILED,
            FeatureFlag.SLACK_INTEGRATION,
            FeatureFlag.AUDIT_LOGS,
            FeatureFlag.GITOPS_REMEDIATION,
            FeatureFlag.PRECISION_DISCOVERY,
            FeatureFlag.OWNER_ATTRIBUTION,
            FeatureFlag.CHARGEBACK,
            FeatureFlag.INGESTION_SLA,
            FeatureFlag.INGESTION_BACKFILL,
            FeatureFlag.ANOMALY_DETECTION,
            FeatureFlag.UNIT_ECONOMICS,
            FeatureFlag.RECONCILIATION,
            FeatureFlag.CLOSE_WORKFLOW,
            FeatureFlag.CARBON_ASSURANCE,
            FeatureFlag.CLOUD_PLUS_CONNECTORS,
            FeatureFlag.COMPLIANCE_EXPORTS,
            FeatureFlag.SAVINGS_PROOF,
            FeatureFlag.COMMITMENT_OPTIMIZATION,
            FeatureFlag.POLICY_PREVIEW,
            FeatureFlag.POLICY_CONFIGURATION,
            FeatureFlag.ESCALATION_WORKFLOW,
            FeatureFlag.INCIDENT_INTEGRATIONS,
        },
        "limits": {
            "max_aws_accounts": 25,
            "max_azure_tenants": 25,
            "max_gcp_projects": 25,
            "max_saas_connections": 10,
            "max_license_connections": 10,
            "max_platform_connections": 10,
            "max_hybrid_connections": 10,
            "byok_enabled": True,
            "ai_insights_per_month": 100,
            "llm_analyses_per_day": 100,
            "llm_analyses_per_user_per_day": 25,
            "llm_system_analyses_per_day": 30,
            "llm_analysis_max_records": 5000,
            "llm_analysis_max_window_days": 730,
            "llm_prompt_max_input_tokens": 32768,
            "llm_output_max_tokens": 4096,
            "max_backfill_days": 730,
            "scan_frequency_hours": 1,
            "retention_days": 730,
        },
        "description": "For enterprises requiring high-scale cloud governance.",
        "cta": "Contact Sales",
        "display_features": [
            "Includes all Growth features",
            "SSO / SAML integration",
            "Hourly zombie scanning",
            "Finance-grade reconciliation + close workflow",
            "Dedicated support engineer",
            "Compliance exports and audit evidence",
            "Custom GitOps remediation",
            "BYOK supported (no platform surcharge)",
        ],
    },
    PricingTier.ENTERPRISE: {
        "name": "Enterprise",
        "price_usd": None,
        "features": set(FeatureFlag),
        "limits": {
            "max_aws_accounts": 999,
            "max_azure_tenants": 999,
            "max_gcp_projects": 999,
            "max_saas_connections": 999,
            "max_license_connections": 999,
            "max_platform_connections": 999,
            "max_hybrid_connections": 999,
            "byok_enabled": True,
            "ai_insights_per_month": 999,
            "llm_analyses_per_day": 2000,
            "llm_analyses_per_user_per_day": 500,
            "llm_system_analyses_per_day": 400,
            "llm_analysis_max_records": 20000,
            "llm_analysis_max_window_days": 3650,
            "llm_prompt_max_input_tokens": 65536,
            "llm_output_max_tokens": 8192,
            "scan_frequency_hours": 1,
            "retention_days": None,
        },
        "description": "Custom solutions for global-scale infrastructure.",
        "cta": "Talk to Expert",
        "display_features": [
            "Unlimited accounts & users",
            "Cloud+ connectors (SaaS/license/custom sources)",
            "Savings-proof exports for procurement cycles",
            "Custom feature development",
            "On-premise deployment options",
            "White-labeling support",
            "24/7/365 multi-region support",
        ],
    },
}

def normalize_tier(tier: PricingTier | str | None) -> PricingTier:
    """Map arbitrary tier values to a supported PricingTier."""
    if isinstance(tier, PricingTier):
        return tier
    if isinstance(tier, str):
        candidate = tier.strip().lower()
        try:
            return PricingTier(candidate)
        except ValueError:
            return PricingTier.FREE
    return PricingTier.FREE


def get_tier_config(tier: PricingTier | str) -> dict[str, Any]:
    """Get configuration for a tier."""
    resolved = normalize_tier(tier)
    fallback = (
        TIER_CONFIG.get(PricingTier.FREE) or TIER_CONFIG.get(PricingTier.STARTER) or {}
    )
    return TIER_CONFIG.get(resolved, fallback)


def is_feature_enabled(tier: PricingTier | str, feature: str | FeatureFlag) -> bool:
    """Check if a feature is enabled for a tier."""
    if isinstance(feature, str):
        try:
            # Try to map string to modern FeatureFlag
            feature = FeatureFlag(feature)
        except ValueError:
            return False

    config = get_tier_config(tier)
    return feature in config.get("features", set())


def get_tier_limit(tier: PricingTier | str, limit_name: str) -> Any:
    """Get a limit value for a tier (None = unlimited)."""
    config = get_tier_config(tier)
    # Default to 0 for unknown limits to satisfy TestTierLimits.test_unknown_limit_returns_zero
    limits = cast(dict[str, Any], config.get("limits", {}))
    raw_limit = limits.get(limit_name, 0)
    if raw_limit is None:
        return None
    if isinstance(raw_limit, bool):
        return int(raw_limit)
    if isinstance(raw_limit, float):
        return int(raw_limit)
    return raw_limit


def requires_tier(
    *allowed_tiers: PricingTier,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator to require specific tiers for an endpoint.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            user = kwargs.get("user") or kwargs.get("current_user")
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            user_tier = normalize_tier(getattr(user, "tier", PricingTier.FREE))

            if user_tier not in allowed_tiers:
                tier_names = [t.value for t in allowed_tiers]
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"This feature requires {' or '.join(tier_names)} tier. Please upgrade.",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def requires_feature(
    feature_name: Union[str, FeatureFlag],
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator to require a specific feature for an endpoint.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            user = kwargs.get("user") or kwargs.get("current_user")
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            user_tier = normalize_tier(getattr(user, "tier", PricingTier.FREE))

            if not is_feature_enabled(user_tier, feature_name):
                fn = (
                    feature_name.value
                    if isinstance(feature_name, FeatureFlag)
                    else feature_name
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Feature '{fn}' is not available on your current plan. Please upgrade.",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


async def get_tenant_tier(
    tenant_id: Union[str, uuid.UUID], db: "AsyncSession"
) -> PricingTier:
    """Get the pricing tier for a tenant."""
    from sqlalchemy import select
    from app.models.tenant import Tenant

    if isinstance(tenant_id, str):
        try:
            tenant_id = uuid.UUID(tenant_id)
        except (ValueError, AttributeError):
            # If not a valid UUID string, we can't look it up.
            return PricingTier.FREE

    try:
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if inspect.isawaitable(tenant):
            tenant = await tenant

        if not tenant:
            return PricingTier.FREE
        try:
            return PricingTier(tenant.plan)
        except ValueError:
            logger.error(
                "invalid_tenant_plan", tenant_id=str(tenant_id), plan=tenant.plan
            )
            return PricingTier.FREE
    except Exception as e:
        logger.error("get_tenant_tier_failed", tenant_id=str(tenant_id), error=str(e))
        return PricingTier.FREE


class TierGuard:
    """
    Context manager and helper for tier-based feature gating.

    Usage:
        async with TierGuard(user, db) as guard:
            if guard.has(FeatureFlag.AI_INSIGHTS):
                ...
    """

    def __init__(self, user: "CurrentUser", db: "AsyncSession"):
        self.user = user
        self.db = db
        self.tier = PricingTier.FREE

    async def __aenter__(self) -> "TierGuard":
        if self.user and self.user.tenant_id:
            self.tier = await get_tenant_tier(self.user.tenant_id, self.db)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    def has(self, feature: FeatureFlag) -> bool:
        return is_feature_enabled(self.tier, feature)

    def limit(self, limit_name: str) -> Any:
        return get_tier_limit(self.tier, limit_name)

    def require(self, feature: FeatureFlag) -> None:
        if not self.has(feature):
            raise HTTPException(
                status_code=403,
                detail=f"Feature '{feature.value}' requires a plan upgrade.",
            )
