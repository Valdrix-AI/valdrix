"""
Tier-Based Feature Gating

Enforces subscription tier limits:
- Free: Basic zombie scans, daily digest
- Starter: 5 AWS accounts, AI insights (limited), email alerts
- Professional: 25 accounts, full AI insights, Slack, hourly scans
- Enterprise: Unlimited, custom integrations, SLA

Usage:
    from app.core.tier_guard import requires_tier, FeatureFlag

    @router.get("/insights")
    @requires_tier(FeatureFlag.AI_INSIGHTS)
    async def get_insights(user: CurrentUser): ...
"""

from enum import Enum
from functools import wraps
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

logger = structlog.get_logger()


class PricingTier(str, Enum):
    """Subscription tiers in order of access level."""
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class FeatureFlag(str, Enum):
    """Feature flags for tier gating."""
    # Core features
    ZOMBIE_SCAN = "zombie_scan"
    COST_TRACKING = "cost_tracking"
    CARBON_TRACKING = "carbon_tracking"
    
    # AI features
    AI_INSIGHTS = "ai_insights"
    AI_ANALYSIS_DETAILED = "ai_analysis_detailed"
    
    # Integrations
    SLACK_INTEGRATION = "slack_integration"
    CUSTOM_INTEGRATIONS = "custom_integrations"
    
    # Frequency
    HOURLY_SCANS = "hourly_scans"
    REALTIME_SCANS = "realtime_scans"
    
    # Scale
    MULTI_REGION = "multi_region"
    UNLIMITED_ACCOUNTS = "unlimited_accounts"
    
    # Enterprise
    AUDIT_LOGS = "audit_logs"
    SSO = "sso"
    SLA_GUARANTEE = "sla_guarantee"


# Feature access matrix: which tier gets what
TIER_FEATURES = {
    PricingTier.FREE: {
        FeatureFlag.ZOMBIE_SCAN,
        FeatureFlag.COST_TRACKING,
        FeatureFlag.CARBON_TRACKING,
    },
    PricingTier.STARTER: {
        FeatureFlag.ZOMBIE_SCAN,
        FeatureFlag.COST_TRACKING,
        FeatureFlag.CARBON_TRACKING,
        FeatureFlag.AI_INSIGHTS,  # Limited to 10/month
        FeatureFlag.MULTI_REGION,
    },
    PricingTier.PROFESSIONAL: {
        FeatureFlag.ZOMBIE_SCAN,
        FeatureFlag.COST_TRACKING,
        FeatureFlag.CARBON_TRACKING,
        FeatureFlag.AI_INSIGHTS,
        FeatureFlag.AI_ANALYSIS_DETAILED,
        FeatureFlag.SLACK_INTEGRATION,
        FeatureFlag.HOURLY_SCANS,
        FeatureFlag.MULTI_REGION,
        FeatureFlag.AUDIT_LOGS,
    },
    PricingTier.ENTERPRISE: {
        # Enterprise gets everything
        *[f for f in FeatureFlag],
    },
}

# Numeric limits per tier
TIER_LIMITS = {
    PricingTier.FREE: {
        "max_aws_accounts": 1,
        "ai_insights_per_month": 0,
        "scan_frequency_hours": 24,
    },
    PricingTier.STARTER: {
        "max_aws_accounts": 5,
        "ai_insights_per_month": 10,
        "scan_frequency_hours": 24,
    },
    PricingTier.PROFESSIONAL: {
        "max_aws_accounts": 25,
        "ai_insights_per_month": 100,
        "scan_frequency_hours": 1,
    },
    PricingTier.ENTERPRISE: {
        "max_aws_accounts": 999,  # "unlimited"
        "ai_insights_per_month": 999,
        "scan_frequency_hours": 0,  # realtime
    },
}


async def get_tenant_tier(tenant_id: str, db: AsyncSession) -> PricingTier:
    """Get the current tier for a tenant."""
    try:
        from app.services.billing.paystack_billing import TenantSubscription
        
        result = await db.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == tenant_id
            )
        )
        sub = result.scalar_one_or_none()
        
        if not sub:
            return PricingTier.FREE
        
        return PricingTier(sub.tier.lower())
    except Exception as e:
        logger.warning("tier_lookup_failed", tenant_id=tenant_id, error=str(e))
        return PricingTier.FREE


def has_feature(tier: PricingTier, feature: FeatureFlag) -> bool:
    """Check if a tier has access to a feature."""
    return feature in TIER_FEATURES.get(tier, set())


def get_limit(tier: PricingTier, limit_key: str) -> int:
    """Get a numeric limit for a tier."""
    return TIER_LIMITS.get(tier, {}).get(limit_key, 0)


def requires_tier(feature: FeatureFlag):
    """
    Decorator to enforce tier-based feature access.
    
    Usage:
        @router.get("/insights")
        @requires_tier(FeatureFlag.AI_INSIGHTS)
        async def get_insights(user: CurrentUser, db: AsyncSession): ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract user and db from kwargs
            user = kwargs.get("user") or kwargs.get("current_user")
            db = kwargs.get("db")
            
            if not user or not db:
                # Fallback: allow if we can't check (shouldn't happen)
                return await func(*args, **kwargs)
            
            tier = await get_tenant_tier(str(user.tenant_id), db)
            
            if not has_feature(tier, feature):
                logger.warning(
                    "feature_access_denied",
                    tenant_id=str(user.tenant_id),
                    feature=feature.value,
                    tier=tier.value
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Feature '{feature.value}' requires a higher subscription tier. Current: {tier.value}"
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


class TierGuard:
    """
    Context manager for checking tier access within functions.
    
    Usage:
        async with TierGuard(user, db) as guard:
            if guard.has(FeatureFlag.AI_INSIGHTS):
                # Do AI stuff
            accounts = guard.limit("max_aws_accounts")
    """
    
    def __init__(self, user, db: AsyncSession):
        self.user = user
        self.db = db
        self.tier = PricingTier.FREE
    
    async def __aenter__(self):
        self.tier = await get_tenant_tier(str(self.user.tenant_id), self.db)
        return self
    
    async def __aexit__(self, *args):
        pass
    
    def has(self, feature: FeatureFlag) -> bool:
        return has_feature(self.tier, feature)
    
    def limit(self, key: str) -> int:
        return get_limit(self.tier, key)
    
    def require(self, feature: FeatureFlag):
        if not self.has(feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Feature '{feature.value}' requires upgrade. Current: {self.tier.value}"
            )
