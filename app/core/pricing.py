import uuid
from enum import Enum
from functools import wraps
from typing import Optional, Callable, Dict

from fastapi import HTTPException, status

import structlog

logger = structlog.get_logger()


class PricingTier(str, Enum):
    """Available subscription tiers."""
    FREE = "free"  # Legacy/Test compatibility
    TRIAL = "trial"
    STARTER = "starter"
    GROWTH = "growth"
    PRO = "pro"
    PROFESSIONAL = "pro" # Alias for test compatibility
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
    DEDICATED_SUPPORT = "dedicated_support"
    AUDIT_LOGS = "audit_logs"
    HOURLY_SCANS = "hourly_scans"
    AI_ANALYSIS_DETAILED = "ai_analysis_detailed"
    PRECISION_DISCOVERY = "precision_discovery"
    OWNER_ATTRIBUTION = "owner_attribution"
    GITOPS_REMEDIATION = "gitops_remediation"


# Tier configuration - USD pricing
TIER_CONFIG: Dict[PricingTier, Dict] = {
    PricingTier.FREE: {
        "name": "Free",
        "price_usd": 0,
        "features": {
            FeatureFlag.DASHBOARDS,
            FeatureFlag.COST_TRACKING,
            FeatureFlag.ZOMBIE_SCAN,
            FeatureFlag.GREENOPS,
            FeatureFlag.CARBON_TRACKING,
        },
        "limits": {
            "max_aws_accounts": 1,
            "ai_insights_per_month": 0,
            "scan_frequency_hours": 24,
            "zombie_scans_per_day": 1,
            "llm_analyses_per_day": 0,
        },
        "description": "Basic cloud cost visibility for individuals.",
        "cta": "Get Started",
        "display_features": [
            "Single cloud provider (AWS)",
            "Basic cost dashboards",
            "Daily zombie scanning",
            "GreenOps (Carbon tracking)",
        ]
    },
    PricingTier.TRIAL: {
        "name": "Trial",
        "price_usd": 0,
        "features": {
            FeatureFlag.DASHBOARDS,
            FeatureFlag.ALERTS,
            FeatureFlag.ZOMBIE_SCAN,
        },
        "limits": {
            "zombie_scans_per_day": 5,
            "llm_analyses_per_day": 1,
            "retention_days": 14,
        }
    },
    PricingTier.STARTER: {
        "name": "Starter",
        "price_usd": {
            "monthly": 29,
            "annual": 290
        },
        "paystack_amount_kobo": {
            "monthly": 4125000,
            "annual": 41250000
        },
        "features": {
            FeatureFlag.DASHBOARDS,
            FeatureFlag.COST_TRACKING,
            FeatureFlag.ALERTS,
            FeatureFlag.ZOMBIE_SCAN,
            FeatureFlag.AI_INSIGHTS,
            FeatureFlag.MULTI_REGION,
            FeatureFlag.CARBON_TRACKING,
            FeatureFlag.GREENOPS,
        },
        "limits": {
            "max_aws_accounts": 5,
            "max_azure_tenants": 2,
            "max_gcp_projects": 3,
            "ai_insights_per_month": 10,
            "scan_frequency_hours": 24,
            "retention_days": 90,
        },
        "description": "For small teams getting started with cloud cost visibility.",
        "cta": "Start with Starter",
        "display_features": [
            "Includes all Free features",
            "Multi-account support",
            "Advanced budget alerts",
            "Multi-region analysis",
            "90-day data retention",
        ]
    },
    PricingTier.GROWTH: {
        "name": "Growth",
        "price_usd": {
            "monthly": 79,
            "annual": 790
        },
        "paystack_amount_kobo": {
            "monthly": 11250000,    # ₦112,500
            "annual": 112500000     # ₦1,125,000
        },
        "features": {
            FeatureFlag.DASHBOARDS,
            FeatureFlag.COST_TRACKING,
            FeatureFlag.ALERTS,
            FeatureFlag.ZOMBIE_SCAN,
            FeatureFlag.AI_INSIGHTS,
            FeatureFlag.MULTI_REGION,
            FeatureFlag.CARBON_TRACKING,
            FeatureFlag.GREENOPS,
            FeatureFlag.AUTO_REMEDIATION,
            FeatureFlag.PRECISION_DISCOVERY,
            FeatureFlag.OWNER_ATTRIBUTION,
        },
        "limits": {
            "max_aws_accounts": 20,
            "max_azure_tenants": 10,
            "max_gcp_projects": 15,
            "retention_days": 365,
        },
        "description": "For growing teams who need AI-powered cost intelligence.",
        "cta": "Start Free Trial",
        "display_features": [
            "Includes all Starter features",
            "AI-driven savings insights",
            "Custom remediation guides",
            "Full multi-cloud support",
            "1-year data retention",
        ]
    },
    PricingTier.PRO: {
        "name": "Pro",
        "price_usd": {
            "monthly": 199,
            "annual": 1990
        },
        "paystack_amount_kobo": {
            "monthly": 28500000,    # ₦285,000
            "annual": 285000000     # ₦2,850,000
        },
        "features": {
            FeatureFlag.DASHBOARDS,
            FeatureFlag.COST_TRACKING,
            FeatureFlag.ALERTS,
            FeatureFlag.ZOMBIE_SCAN,
            FeatureFlag.AI_INSIGHTS,
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
        },
        "limits": {
            "max_aws_accounts": 25,
            "ai_insights_per_month": 100,
            "scan_frequency_hours": 1,
            "zombie_scans_per_day": 100,
            "llm_analyses_per_day": 100,
            "retention_days": 730,
        }
    },
    PricingTier.ENTERPRISE: {
        "name": "Enterprise",
        "price_usd": None,
        "features": set(FeatureFlag),
        "limits": {
            "max_aws_accounts": 999,
            "ai_insights_per_month": 999,
            "zombie_scans_per_day": None,
            "llm_analyses_per_day": None,
            "retention_days": None,
        }
    },
}

# Alias for test compatibility
TIER_LIMITS = TIER_CONFIG
PROFESSIONAL = PricingTier.PRO # Alias for test compatibility


def get_tier_config(tier: PricingTier) -> dict:
    """Get configuration for a tier."""
    return TIER_CONFIG.get(tier, TIER_CONFIG[PricingTier.STARTER])


def is_feature_enabled(tier: PricingTier, feature: str | FeatureFlag) -> bool:
    """Check if a feature is enabled for a tier."""
    if isinstance(feature, str):
        try:
            # Try to map string to modern FeatureFlag
            feature = FeatureFlag(feature)
        except ValueError:
            return False
            
    config = get_tier_config(tier)
    return feature in config.get("features", set())

# Aliases for test compatibility
has_feature = is_feature_enabled

def get_tier_limit(tier: PricingTier, limit_name: str) -> Optional[int]:
    """Get a limit value for a tier (None = unlimited)."""
    config = get_tier_config(tier)
    # Default to 0 for unknown limits to satisfy TestTierLimits.test_unknown_limit_returns_zero
    return config.get("limits", {}).get(limit_name, 0)

# Aliases for test compatibility
get_limit = get_tier_limit


def requires_tier(*allowed_tiers: PricingTier):
    """
    Decorator to require specific tiers for an endpoint.
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user = kwargs.get("user")
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            user_tier = getattr(user, "tier", PricingTier.STARTER)
            if isinstance(user_tier, str):
                try:
                    user_tier = PricingTier(user_tier)
                except ValueError:
                    user_tier = PricingTier.STARTER
            
            if user_tier not in allowed_tiers:
                tier_names = [t.value for t in allowed_tiers]
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"This feature requires {' or '.join(tier_names)} tier. Please upgrade."
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def requires_feature(feature_name: str | FeatureFlag):
    """
    Decorator to require a specific feature for an endpoint.
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user = kwargs.get("user")
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            user_tier = getattr(user, "tier", PricingTier.STARTER)
            if isinstance(user_tier, str):
                try:
                    user_tier = PricingTier(user_tier)
                except ValueError:
                    user_tier = PricingTier.STARTER
            
            if not is_feature_enabled(user_tier, feature_name):
                fn = feature_name.value if isinstance(feature_name, FeatureFlag) else feature_name
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Feature '{fn}' is not available on your current plan. Please upgrade."
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


async def get_tenant_tier(tenant_id: str | uuid.UUID, db: "AsyncSession") -> PricingTier:
    """Get the pricing tier for a tenant."""
    from sqlalchemy import select
    from app.models.tenant import Tenant
    
    if isinstance(tenant_id, str):
        try:
            tenant_id = uuid.UUID(tenant_id)
        except (ValueError, AttributeError):
            # If not a valid UUID string, we can't look it up, so return Free/Trial
            return PricingTier.FREE
    
    try:
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            return PricingTier.FREE
        
        return PricingTier(tenant.plan)
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

    async def __aenter__(self):
        if self.user and self.user.tenant_id:
            self.tier = await get_tenant_tier(self.user.tenant_id, self.db)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def has(self, feature: FeatureFlag) -> bool:
        return is_feature_enabled(self.tier, feature)

    def limit(self, limit_name: str) -> Optional[int]:
        return get_tier_limit(self.tier, limit_name)

    def require(self, feature: FeatureFlag):
        if not self.has(feature):
            raise HTTPException(
                status_code=403,
                detail=f"Feature '{feature.value}' requires a plan upgrade."
            )
