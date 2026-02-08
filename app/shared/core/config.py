from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from typing import Optional
from app.shared.core.constants import AWS_SUPPORTED_REGIONS, LLMProvider
import structlog
import secrets


@lru_cache
def get_settings():
    """Returns a singleton instance of the application settings."""
    settings = Settings()
    if not settings.CSRF_SECRET_KEY and not settings.is_production:
        # Generate a random key for non-production if missing
        settings.CSRF_SECRET_KEY = secrets.token_hex(32)
    return settings


class Settings(BaseSettings):
    """
    Main configuration for Valdrix AI.
    Uses Pydantic-Settings for environment variable parsing from .env.
    """
    APP_NAME: str = "Valdrix"
    VERSION: str = "0.1.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # local, development, staging, production
    API_URL: str = "http://localhost:8000"  # Base URL for OIDC and Magic Links
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None # Added for D5: Telemetry Sink
    OTEL_EXPORTER_OTLP_INSECURE: bool = False # SEC-07: Secure Tracing
    CSRF_SECRET_KEY: str = "dev_secret_key_change_me_in_prod" # SEC-01: CSRF
    TESTING: bool = False
    RATELIMIT_ENABLED: bool = True

    @model_validator(mode='after')
    def validate_security_config(self) -> 'Settings':
        """Ensure critical production keys are present and valid."""
        if self.TESTING:
            return self

            
        if self.is_production:
            # SEC-01: CSRF key must be changed
            if not self.CSRF_SECRET_KEY:
                raise ValueError(
                    "SECURITY ERROR: CSRF_SECRET_KEY must be set in production! "
                    "Set CSRF_SECRET_KEY environment variable to a secure random value."
                )
            
            # SEC-02: Encryption Key must be secure
            if not self.ENCRYPTION_KEY or len(self.ENCRYPTION_KEY) < 32:
                raise ValueError("ENCRYPTION_KEY must be at least 32 characters in production.")
            
            # PRODUCTION FIX #6: KDF_SALT must be set in production
            if not self.KDF_SALT:
                raise ValueError("CRITICAL: KDF_SALT environment variable must be set in production. See DEPLOYMENT_FIXES_GUIDE.md Section 6.")
            
            # SEC-03: DB and Auth
            if not self.DATABASE_URL:
                raise ValueError("DATABASE_URL is required in production.")
            if not self.SUPABASE_JWT_SECRET or len(self.SUPABASE_JWT_SECRET) < 32:
                raise ValueError("SUPABASE_JWT_SECRET must be at least 32 characters in production.")

            # SEC-04: Database SSL Mode
            if self.DB_SSL_MODE not in ["require", "verify-ca", "verify-full"]:
                raise ValueError(f"SECURITY ERROR: DB_SSL_MODE must be 'require', 'verify-ca', or 'verify-full' in production. Current: {self.DB_SSL_MODE}")
            
            if self.DB_SSL_MODE in ["verify-ca", "verify-full"] and not self.DB_SSL_CA_CERT_PATH:
                raise ValueError(f"SECURITY ERROR: DB_SSL_CA_CERT_PATH is mandatory when DB_SSL_MODE is '{self.DB_SSL_MODE}'.")


        # SEC-05: Admin API Key validation for staging/production
        if self.ENVIRONMENT in ["production", "staging"]:
            if not self.ADMIN_API_KEY:
                raise ValueError(f"SECURITY ERROR: ADMIN_API_KEY must be configured in {self.ENVIRONMENT} environment.")
            
            if self.ENVIRONMENT == "production" and len(self.ADMIN_API_KEY) < 32:
                raise ValueError("SECURITY ERROR: ADMIN_API_KEY must be at least 32 characters in production for security.")
            
            # SEC-A1: CORS origins should not include localhost in production
            localhost_origins = [o for o in self.CORS_ORIGINS if 'localhost' in o or '127.0.0.1' in o]
            if localhost_origins:
                structlog.get_logger().warning(
                    "cors_localhost_in_production",
                    origins=localhost_origins,
                    msg="CORS_ORIGINS contains localhost URLs in production mode"
                )
            
            # SEC-A2: API_URL/FRONTEND_URL should be HTTPS in production
            for attr_name in ["API_URL", "FRONTEND_URL"]:
                val = getattr(self, attr_name)
                if val and val.startswith("http://"):
                    structlog.get_logger().warning(
                        f"{attr_name.lower()}_not_https",
                        **{attr_name.lower(): val},
                        msg=f"{attr_name} should use HTTPS in production"
                    )
        
        # LLM Provider keys (validated in all modes if provider selected)
        provider_keys = {
            LLMProvider.OPENAI: self.OPENAI_API_KEY,
            LLMProvider.CLAUDE: self.CLAUDE_API_KEY,
            LLMProvider.ANTHROPIC: self.ANTHROPIC_API_KEY or self.CLAUDE_API_KEY,
            LLMProvider.GOOGLE: self.GOOGLE_API_KEY,
            LLMProvider.GROQ: self.GROQ_API_KEY
        }
        
        if self.LLM_PROVIDER in provider_keys and not provider_keys[self.LLM_PROVIDER]:
            if self.is_production:
                raise ValueError(f"LLM_PROVIDER is set to '{self.LLM_PROVIDER}' but corresponding API key is missing.")
                
        return self


    # AWS Credentials
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_DEFAULT_REGION: str = "us-east-1"
    AWS_ENDPOINT_URL: Optional[str] = None  # Added for local testing (MotoServer/LocalStack)
    
    # CloudFormation Template (Configurable for S3/GitHub)
    CLOUDFORMATION_TEMPLATE_URL: str = "https://raw.githubusercontent.com/valdrix/valdrix/main/cloudformation/valdrix-role.yaml"
    
    # Reload trigger: 2026-01-14

    # Security
    CORS_ORIGINS: list[str] = [] # Empty by default - restricted in prod
    FRONTEND_URL: str = "http://localhost:5173"  # Used for billing callbacks
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o" # High performance for complex analysis

    # Claude/Anthropic Credentials
    CLAUDE_API_KEY: Optional[str] = None
    CLAUDE_MODEL: str = "claude-3-7-sonnet"
    ANTHROPIC_API_KEY: Optional[str] = None # Added for Phase 28 compatibility

    # Google Gemini Credentials
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_MODEL: str = "gemini-2.0-flash"

    # Groq Credentials
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # LLM Provider
    LLM_PROVIDER: str = "groq" # Options: openai, claude, google, groq
    ENABLE_DELTA_ANALYSIS: bool = True # Innovation 1: Reduce token usage by 90%
    DELTA_ANALYSIS_DAYS: int = 3

    # Scheduler
    SCHEDULER_HOUR: int = 8
    SCHEDULER_MINUTE: int = 0

    # Admin API Key
    ADMIN_API_KEY: Optional[str] = None

    # Database
    DATABASE_URL: Optional[str] = None # Required in prod, optional in dev/test
    DB_SSL_MODE: str = "require"  # Options: disable, require, verify-ca, verify-full
    DB_SSL_CA_CERT_PATH: Optional[str] = None  # Path to CA cert for verify-ca/verify-full modes
    DB_POOL_SIZE: int = 20  # Standard for Supabase/Neon free tiers
    DB_MAX_OVERFLOW: int = 10

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
    
    # GreenOps & Carbon APIs
    WATT_TIME_API_KEY: Optional[str] = None
    ELECTRICITY_MAPS_API_KEY: Optional[str] = None


    # Encryption & Secret Rotation
    ENCRYPTION_KEY: Optional[str] = None
    PII_ENCRYPTION_KEY: Optional[str] = None
    API_KEY_ENCRYPTION_KEY: Optional[str] = None
    LEGACY_ENCRYPTION_KEYS: list[str] = []
    BLIND_INDEX_KEY: Optional[str] = None # SEC-06: Separation of keys
    
    # KDF Settings for password-to-key derivation (SEC-06)
    # PRODUCTION FIX #6: Per-environment encryption salt (not hardcoded)
    # Set via environment variable: export KDF_SALT="<base64-encoded-random-32-bytes>"
    # Generate: python3 -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
    KDF_SALT: str = ""
    KDF_ITERATIONS: int = 100000


    # Cache (Redis for production, in-memory for dev)
    REDIS_URL: Optional[str] = None  # e.g., redis://localhost:6379
    
    # Upstash Redis (Serverless - Free tier: 10K commands/day)
    UPSTASH_REDIS_URL: Optional[str] = None  # e.g., https://xxx.upstash.io
    UPSTASH_REDIS_TOKEN: Optional[str] = None

    # Paystack Billing (Nigeria Support)
    PAYSTACK_SECRET_KEY: Optional[str] = None
    PAYSTACK_PUBLIC_KEY: Optional[str] = None
    EXCHANGERATE_API_KEY: Optional[str] = None # Added for dynamic currency
    FALLBACK_NGN_RATE: float = 1450.0 # SEC: Centralized financial fallback
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

    # Circuit Breaker & Safety Guardrails (Phase 12)
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    CIRCUIT_BREAKER_RECOVERY_SECONDS: int = 300
    CIRCUIT_BREAKER_MAX_DAILY_SAVINGS: float = 1000.0
    
    # REMEDIATION KILL SWITCH: Stop all deletions if daily cost impact hits $500
    REMEDIATION_KILL_SWITCH_THRESHOLD: float = 500.0
    ENFORCE_REMEDIATION_DRY_RUN: bool = False
    
    # Multi-Currency & Localization (Phase 12)
    SUPPORTED_CURRENCIES: list[str] = ["USD", "NGN", "EUR", "GBP"]
    EXCHANGE_RATE_SYNC_INTERVAL_HOURS: int = 24
    BASE_CURRENCY: str = "USD"

    # AWS Regions (BE-ADAPT-1: Regional Whitelist)
    AWS_SUPPORTED_REGIONS: list[str] = AWS_SUPPORTED_REGIONS

    # Scanner Settings
    ZOMBIE_PLUGIN_TIMEOUT_SECONDS: int = 30
    ZOMBIE_REGION_TIMEOUT_SECONDS: int = 120

    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True
    )

    @property
    def is_production(self) -> bool:
        return not self.DEBUG


