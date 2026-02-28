from __future__ import annotations

from pathlib import Path

from app.shared.core.pricing import (
    ENTERPRISE_FEATURES,
    FEATURE_MATURITY,
    FeatureFlag,
    FeatureMaturity,
    PricingTier,
    TIER_CONFIG,
    get_tier_feature_maturity,
)


def test_enterprise_features_are_explicit_not_dynamic() -> None:
    pricing_path = Path("app/shared/core/pricing.py")
    raw = pricing_path.read_text(encoding="utf-8")
    assert "set(FeatureFlag)" not in raw
    assert "ENTERPRISE_FEATURES" in raw


def test_enterprise_feature_roster_matches_tier_config() -> None:
    configured = TIER_CONFIG[PricingTier.ENTERPRISE]["features"]
    assert configured == ENTERPRISE_FEATURES
    assert all(isinstance(feature, FeatureFlag) for feature in configured)


def test_feature_maturity_is_defined_for_every_feature_flag() -> None:
    assert set(FEATURE_MATURITY.keys()) == set(FeatureFlag)
    assert all(isinstance(value, FeatureMaturity) for value in FEATURE_MATURITY.values())


def test_tier_feature_maturity_payload_contains_only_tier_features() -> None:
    for tier in PricingTier:
        maturity = get_tier_feature_maturity(tier)
        configured = TIER_CONFIG[tier]["features"]
        configured_values = {feature.value for feature in configured}
        assert set(maturity.keys()) == configured_values
        assert set(maturity.values()).issubset({m.value for m in FeatureMaturity})
