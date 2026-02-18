from app.shared.core.pricing import TIER_CONFIG, PricingTier


def test_annual_pricing_discount():
    """
    Verify that annual pricing is exactly 10x monthly pricing
    (2 months free) for all paid tiers.
    """
    tiers_to_check = [PricingTier.STARTER, PricingTier.GROWTH, PricingTier.PRO]

    for tier in tiers_to_check:
        config = TIER_CONFIG[tier]
        price_usd = config["price_usd"]

        assert isinstance(price_usd, dict), f"Price for {tier} should be a dictionary"

        monthly = price_usd["monthly"]
        annual = price_usd["annual"]

        # Verify 10x rule
        assert annual == monthly * 10, (
            f"Annual price for {tier} should be exactly 10x monthly ({monthly} * 10 = {monthly * 10}, but got {annual})"
        )


def test_pricing_period_consistency():
    """Verify that period descriptions for annual billing make sense."""
    # This is more of a placeholder as period strings are often dynamic in frontend,
    # but we check backend sanity.
    for tier, config in TIER_CONFIG.items():
        if tier == PricingTier.FREE:
            continue
        assert "price_usd" in config
