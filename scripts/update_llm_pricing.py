#!/usr/bin/env python3
import asyncio
import argparse
import structlog
from sqlalchemy import select, update
from app.shared.db.session import async_session_maker
from app.models.pricing import PricingPlan, ExchangeRate, TenantSubscription, LLMProviderPricing
from app.models.llm import LLMUsage, LLMBudget
from app.models.tenant import User, Tenant
from app.models.aws_connection import AWSConnection
from app.models.cloud import CostRecord
from app.models.notification_settings import NotificationSettings
from app.models.remediation import RemediationRequest
from app.models.remediation_settings import RemediationSettings
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.models.background_job import BackgroundJob
from app.models.attribution import AttributionRule, CostAllocation
from app.models.anomaly_marker import AnomalyMarker
from app.models.optimization import OptimizationStrategy, StrategyRecommendation
from app.models.carbon_settings import CarbonSettings
from app.models.discovered_account import DiscoveredAccount
from app.modules.governance.domain.security.audit_log import AuditLog
from app.shared.llm.pricing_data import LLM_PRICING
from app.shared.core.config import get_settings
import os

logger = structlog.get_logger()

# ENV check is handled by the unified factory

async def get_db_session_factory():
    """Returns the unified database session factory."""
    return async_session_maker

async def seed_from_static_data():
    """Seed the database with the initial '2026 pricing' from our static dictionary."""
    session_factory = await get_db_session_factory()
    async with session_factory() as db:
        for provider, models in LLM_PRICING.items():
            for model_name, cost in models.items():
                if model_name == "default":
                    continue
                
                # Check if exists
                stmt = select(LLMProviderPricing).where(
                    LLMProviderPricing.provider == provider,
                    LLMProviderPricing.model == model_name
                )
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                input_cost = cost["input"] if isinstance(cost, dict) else cost.input
                output_cost = cost["output"] if isinstance(cost, dict) else cost.output
                free_tokens = cost.get("free_tier_tokens", 0) if isinstance(cost, dict) else cost.free_tier_tokens
                
                if not existing:
                    new_pricing = LLMProviderPricing(
                        provider=provider,
                        model=model_name,
                        input_cost_per_million=input_cost,
                        output_cost_per_million=output_cost,
                        free_tier_tokens=free_tokens
                    )
                    db.add(new_pricing)
                    print(f"✅ Seeded {provider}/{model_name}")
                else:
                    changed = (
                        float(existing.input_cost_per_million) != float(input_cost)
                        or float(existing.output_cost_per_million) != float(output_cost)
                        or int(existing.free_tier_tokens or 0) != int(free_tokens)
                    )
                    if changed:
                        existing.input_cost_per_million = input_cost
                        existing.output_cost_per_million = output_cost
                        existing.free_tier_tokens = free_tokens
                        print(f"✅ Updated {provider}/{model_name} from static source")
                    else:
                        print(f"ℹ️ Unchanged {provider}/{model_name}")
        
        await db.commit()

async def update_pricing(provider: str, model: str, input_cost: float, output_cost: float, free_tokens: int):
    """Update or create pricing for a specific provider/model."""
    session_factory = await get_db_session_factory()
    async with session_factory() as db:
        stmt = select(LLMProviderPricing).where(
            LLMProviderPricing.provider == provider,
            LLMProviderPricing.model == model
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            existing.input_cost_per_million = input_cost
            existing.output_cost_per_million = output_cost
            existing.free_tier_tokens = free_tokens
            print(f"✅ Updated {provider}/{model}")
        else:
            new_pricing = LLMProviderPricing(
                provider=provider,
                model=model,
                input_cost_per_million=input_cost,
                output_cost_per_million=output_cost,
                free_tier_tokens=free_tokens
            )
            db.add(new_pricing)
            print(f"✅ Created {provider}/{model}")
            
        await db.commit()

def main():
    parser = argparse.ArgumentParser(description="Update LLM Provider Pricing")
    subparsers = parser.add_subparsers(dest="command")
    
    # Seed command
    subparsers.add_parser("seed", help="Seed from static LLM_PRICING data")
    
    # Update command
    update_parser = subparsers.add_parser("update", help="Update specific model pricing")
    update_parser.add_argument("--provider", required=True)
    update_parser.add_argument("--model", required=True)
    update_parser.add_argument("--input", type=float, required=True, help="Cost per 1M input tokens")
    update_parser.add_argument("--output", type=float, required=True, help="Cost per 1M output tokens")
    update_parser.add_argument("--free", type=int, default=0, help="Free tier tokens")
    
    args = parser.parse_args()
    
    if args.command == "seed":
        asyncio.run(seed_from_static_data())
    elif args.command == "update":
        asyncio.run(update_pricing(args.provider, args.model, args.input, args.output, args.free))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
