"""
Pricing Tiers Configuration and Feature Gating

This module defines:
- Tier pricing and limits
- 14-day trial logic
- Feature gating decorators
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import wraps
from typing import Optional, Callable

from fastapi import HTTPException, status

import structlog

logger = structlog.get_logger()


class PricingTier(str, Enum):
    """Available subscription tiers."""
    TRIAL = "trial"
    STARTER = "starter"
    GROWTH = "growth"
    PRO = "pro"
    ENTERPRISE = "enterprise"


# Tier configuration - USD pricing (NGN calculated at checkout)
TIER_CONFIG = {
    PricingTier.TRIAL: {
        "name": "Trial",
        "price_usd": 0,
        "duration_days": 14,
        "cloud_spend_limit": None,  # Unlimited during trial
        "features": {
            "dashboards": True,
            "alerts": True,
            "zombie_detection": True,
            "llm_analysis": True,
            "multi_cloud": True,
            "greenops": True,
            "auto_remediation": False,
            "api_access": False,
            "forecasting": False,
        },
        "limits": {
            "zombie_scans_per_day": 10,
            "llm_analyses_per_day": 5,
        }
    },
    PricingTier.STARTER: {
        "name": "Starter",
        "price_usd": 29,
        "price_ngn": 41250,
        "cloud_spend_limit": 10000,  # $10K/month
        "features": {
            "dashboards": True,
            "alerts": True,
            "zombie_detection": True,
            "llm_analysis": False,
            "multi_cloud": False,
            "greenops": False,
            "auto_remediation": False,
            "api_access": False,
            "forecasting": False,
        },
        "limits": {
            "zombie_scans_per_day": 20,
            "llm_analyses_per_day": 0,
        }
    },
    PricingTier.GROWTH: {
        "name": "Growth",
        "price_usd": 79,
        "price_ngn": 112350,
        "cloud_spend_limit": 50000,  # $50K/month
        "features": {
            "dashboards": True,
            "alerts": True,
            "zombie_detection": True,
            "llm_analysis": True,
            "multi_cloud": True,
            "greenops": True,
            "auto_remediation": False,
            "api_access": False,
            "forecasting": True,
        },
        "limits": {
            "zombie_scans_per_day": 50,
            "llm_analyses_per_day": 20,
        }
    },
    PricingTier.PRO: {
        "name": "Pro",
        "price_usd": 199,
        "price_ngn": 283000,
        "cloud_spend_limit": 200000,  # $200K/month
        "features": {
            "dashboards": True,
            "alerts": True,
            "zombie_detection": True,
            "llm_analysis": True,
            "multi_cloud": True,
            "greenops": True,
            "auto_remediation": True,
            "api_access": True,
            "forecasting": True,
        },
        "limits": {
            "zombie_scans_per_day": None,  # Unlimited
            "llm_analyses_per_day": 100,
        }
    },
    PricingTier.ENTERPRISE: {
        "name": "Enterprise",
        "price_usd": None,  # Custom
        "cloud_spend_limit": None,  # Unlimited
        "features": {
            "dashboards": True,
            "alerts": True,
            "zombie_detection": True,
            "llm_analysis": True,
            "multi_cloud": True,
            "greenops": True,
            "auto_remediation": True,
            "api_access": True,
            "forecasting": True,
            "sso": True,
            "dedicated_support": True,
        },
        "limits": {
            "zombie_scans_per_day": None,
            "llm_analyses_per_day": None,
        }
    },
}


def get_tier_config(tier: PricingTier) -> dict:
    """Get configuration for a tier."""
    return TIER_CONFIG.get(tier, TIER_CONFIG[PricingTier.STARTER])


def is_feature_enabled(tier: PricingTier, feature: str) -> bool:
    """Check if a feature is enabled for a tier."""
    config = get_tier_config(tier)
    return config.get("features", {}).get(feature, False)


def get_tier_limit(tier: PricingTier, limit_name: str) -> Optional[int]:
    """Get a limit value for a tier (None = unlimited)."""
    config = get_tier_config(tier)
    return config.get("limits", {}).get(limit_name)


class TrialManager:
    """Manages 14-day trial logic."""
    
    TRIAL_DURATION_DAYS = 14
    
    @staticmethod
    def calculate_trial_end(start_date: datetime) -> datetime:
        """Calculate when trial ends."""
        return start_date + timedelta(days=TrialManager.TRIAL_DURATION_DAYS)
    
    @staticmethod
    def is_trial_active(trial_started_at: Optional[datetime]) -> bool:
        """Check if trial is still active."""
        if not trial_started_at:
            return False
        trial_end = TrialManager.calculate_trial_end(trial_started_at)
        return datetime.now(timezone.utc) < trial_end
    
    @staticmethod
    def days_remaining(trial_started_at: Optional[datetime]) -> int:
        """Get days remaining in trial."""
        if not trial_started_at:
            return 0
        trial_end = TrialManager.calculate_trial_end(trial_started_at)
        remaining = (trial_end - datetime.now(timezone.utc)).days
        return max(0, remaining)


def requires_tier(*allowed_tiers: PricingTier):
    """
    Decorator to require specific tiers for an endpoint.
    
    Usage:
        @router.get("/analyze")
        @requires_tier(PricingTier.GROWTH, PricingTier.PRO, PricingTier.ENTERPRISE)
        async def analyze_costs(user: CurrentUser):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract user from kwargs (injected by Depends)
            user = kwargs.get("user")
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            # Get tenant's current tier
            user_tier = getattr(user, "tier", PricingTier.STARTER)
            
            # Convert string to enum if needed
            if isinstance(user_tier, str):
                try:
                    user_tier = PricingTier(user_tier)
                except ValueError:
                    user_tier = PricingTier.STARTER
            
            # Check if user's tier is allowed
            if user_tier not in allowed_tiers:
                tier_names = [t.value for t in allowed_tiers]
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"This feature requires {' or '.join(tier_names)} tier. Please upgrade."
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def requires_feature(feature_name: str):
    """
    Decorator to require a specific feature for an endpoint.
    
    Usage:
        @router.post("/remediate")
        @requires_feature("auto_remediation")
        async def auto_remediate(user: CurrentUser):
            ...
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
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Feature '{feature_name}' is not available on your current plan. Please upgrade."
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator
