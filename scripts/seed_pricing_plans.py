import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.shared.db.session import async_session_maker, engine
from app.models.pricing import PricingPlan, ExchangeRate
from app.shared.core.pricing import PricingTier, TIER_CONFIG
from sqlalchemy import select

async def seed_data():
    """Seed initial plans and exchange rates."""
    print("🌱 Seeding pricing plans...")
    
    async with async_session_maker() as db:
        async with db.begin():
            # 1. Seed Pricing Plans from TIER_CONFIG
            for tier, config in TIER_CONFIG.items():
                if tier == PricingTier.TRIAL:
                    continue  # Trial is usually implicit or handled separately
                
                # Check if exists
                res = await db.execute(select(PricingPlan).where(PricingPlan.id == tier.value))
                existing = res.scalar_one_or_none()
                
                if not existing:
                    # Convert sets to lists and enums to values for JSON
                    features = [f.value if hasattr(f, "value") else str(f) for f in config.get("features", [])]
                    
                    plan = PricingPlan(
                        id=tier.value,
                        name=config.get("name", tier.value.capitalize()),
                        description=config.get("description", ""),
                        price_usd=config.get("price_usd") or 0.0,
                        features=features,
                        limits=config.get("limits", {}),
                        display_features=config.get("display_features", []),
                        cta_text=config.get("cta", "Get Started"),
                        is_popular=(tier == PricingTier.GROWTH)
                    )
                    db.add(plan)
                    print(f"  + Added Plan: {tier.value}")
                else:
                    print(f"  ~ Plan {tier.value} already exists, skipping.")

            # 2. Seed Initial Exchange Rate
            res = await db.execute(select(ExchangeRate).where(ExchangeRate.from_currency == "USD", ExchangeRate.to_currency == "NGN"))
            existing_rate = res.scalar_one_or_none()
            
            if not existing_rate:
                # Seed with a realistic starting rate (1600 NGN/USD) 
                # Managed by update_exchange_rates.py for automation (BE-FIN-01)
                db.add(ExchangeRate(
                    from_currency="USD",
                    to_currency="NGN",
                    rate=1600.0,
                    provider="manual-initial-seed"
                ))
                print("  + Added Exchange Rate: 1600.0 NGN/USD (Automation target: update_exchange_rates.py)")
            else:
                print(f"  ~ Exchange Rate exists: {existing_rate.rate}")

    print("✅ Seeding complete!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed_data())
