from enum import Enum
from uuid import UUID

# System-level ID for automated actions (Audit & Remediation)
# Used as the actor_id for SOC2/ISO27001 audit trails where the action is fully automated.
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000000")

# Infrastructure Constants
AWS_SUPPORTED_REGIONS = [
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "af-south-1",
    "ap-east-1",
    "ap-south-1",
    "ap-northeast-3",
    "ap-northeast-2",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-northeast-1",
    "ca-central-1",
    "eu-central-1",
    "eu-west-1",
    "eu-west-2",
    "eu-south-1",
    "eu-west-3",
    "eu-north-1",
    "me-south-1",
    "sa-east-1",
    "us-gov-east-1",
    "us-gov-west-1",
]


class LLMProvider(str, Enum):
    """Supported LLM Providers."""

    OPENAI = "openai"
    GROQ = "groq"
    ANTHROPIC = "anthropic"
    CLAUDE = "anthropic"  # Alias for backward compatibility in config
    GOOGLE = "google"
    AZURE = "azure"


# Tables exempt from RLS enforcement (System/Global data)
RLS_EXEMPT_TABLES = [
    "ix_skipped_table",
    "alembic",
    "users",
    "tenants",
    "tenant_identity_settings",
    "tenant_subscriptions",
    "pricing_plans",
    "exchange_rates",
    "background_jobs",
    "unit_economics_settings",
    "llm_provider_pricing",
]


class Persona(str, Enum):
    """Supported User Personas."""

    ENGINEERING = "engineering"
    FINANCE = "finance"
    PLATFORM = "platform"
    LEADERSHIP = "leadership"


# Subscription Logic
TIER_FREE = "free"
TIER_STARTER = "starter"
TIER_GROWTH = "growth"
TIER_PRO = "pro"
TIER_ENTERPRISE = "enterprise"
