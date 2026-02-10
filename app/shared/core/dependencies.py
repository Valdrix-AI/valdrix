from fastapi import Depends, HTTPException
from typing import Annotated

from app.shared.core.config import get_settings
from app.shared.llm.factory import LLMFactory
from app.shared.llm.analyzer import FinOpsAnalyzer
from app.shared.core.auth import CurrentUser, requires_role
from app.shared.core.pricing import PricingTier, is_feature_enabled, FeatureFlag

def get_llm_provider() -> str:
    settings = get_settings()
    return settings.LLM_PROVIDER

def get_analyzer(provider: str = Depends(get_llm_provider)) -> FinOpsAnalyzer:
    llm = LLMFactory.create(provider)
    return FinOpsAnalyzer(llm)

from functools import lru_cache

@lru_cache()
def requires_feature(feature_name: str | FeatureFlag):
    """Dependency to check if a feature is enabled for the user's tier."""
    async def feature_checker(user: Annotated[CurrentUser, Depends(requires_role("member"))]):
        user_tier = getattr(user, "tier", "starter")
        try:
            tier_enum = PricingTier(user_tier)
        except ValueError:
            tier_enum = PricingTier.STARTER
            
        if not is_feature_enabled(tier_enum, feature_name):
            fn = feature_name.value if isinstance(feature_name, FeatureFlag) else feature_name
            raise HTTPException(
                status_code=403,
                detail=f"Feature '{fn}' requires an upgrade. Current tier: {user_tier}"
            )
        return user
    return feature_checker
