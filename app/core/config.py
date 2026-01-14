from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    APP_NAME: str = "Valdrix"
    VERSION: str = "0.1.0"
    DEBUG: bool = False

    # AWS Credentials
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_DEFAULT_REGION: str = "us-east-1"
    
    # Reload trigger: 2026-01-14

    # Security
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"]
    FRONTEND_URL: str = "http://localhost:5173"  # Used for billing callbacks
    ENCRYPTION_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o" # High performance for complex analysis

    # Claude Credentials
    CLAUDE_API_KEY: Optional[str] = None
    CLAUDE_MODEL: str = "claude-3-7-sonnet"

    # Google Gemini Credentials
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_MODEL: str = "gemini-2.0-flash"

    # Groq Credentials
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # LLM Provider
    LLM_PROVIDER: str = "groq" # Options: openai, claude, google, groq

    # Scheduler
    SCHEDULER_HOUR: int = 8
    SCHEDULER_MINUTE: int = 0

    # Admin API Key
    ADMIN_API_KEY: Optional[str] = None

    # Database
    DATABASE_URL: str # Required in prod
    DB_SSL_MODE: str = "require"  # Options: disable, require, verify-ca, verify-full
    DB_SSL_CA_CERT_PATH: Optional[str] = None  # Path to CA cert for verify-ca/verify-full modes

    # Supabase Auth
    SUPABASE_URL: Optional[str] = None
    SUPABASE_JWT_SECRET: str # Required for auth middleware

    # Notifications
    SLACK_BOT_TOKEN: Optional[str] = None
    SLACK_CHANNEL_ID: Optional[str] = None

    # SMTP Email (for carbon alerts)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: str = "alerts@valdrix.ai"

    # Encryption
    ENCRYPTION_KEY: Optional[str] = None

    # Cache (Redis for production, in-memory for dev)
    REDIS_URL: Optional[str] = None  # e.g., redis://localhost:6379
    
    # Upstash Redis (Serverless - Free tier: 10K commands/day)
    UPSTASH_REDIS_URL: Optional[str] = None  # e.g., https://xxx.upstash.io
    UPSTASH_REDIS_TOKEN: Optional[str] = None

    # Paystack Billing (Nigeria Support)
    PAYSTACK_SECRET_KEY: Optional[str] = None
    PAYSTACK_PUBLIC_KEY: Optional[str] = None
    # Monthly plans
    PAYSTACK_PLAN_STARTER: str = "PLN_starter_xxx"    # ₦41,250/mo ($29)
    PAYSTACK_PLAN_GROWTH: str = "PLN_growth_xxx"      # ₦112,350/mo ($79)
    PAYSTACK_PLAN_PRO: str = "PLN_pro_xxx"            # ₦283,000/mo ($199)
    PAYSTACK_PLAN_ENTERPRISE: str = "PLN_ent_xxx"     # Custom
    # Annual plans (17% discount - 2 months free)
    PAYSTACK_PLAN_STARTER_ANNUAL: Optional[str] = None
    PAYSTACK_PLAN_GROWTH_ANNUAL: Optional[str] = None
    PAYSTACK_PLAN_PRO_ANNUAL: Optional[str] = None
    PAYSTACK_PLAN_ENTERPRISE_ANNUAL: Optional[str] = None

    # Circuit Breaker Defaults
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    CIRCUIT_BREAKER_RECOVERY_SECONDS: int = 300
    CIRCUIT_BREAKER_MAX_DAILY_SAVINGS: float = 1000.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True
    )

@lru_cache
def get_settings():
    return Settings()
