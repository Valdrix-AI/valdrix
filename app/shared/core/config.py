from functools import lru_cache
from typing import Optional
import base64
import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from app.shared.core.constants import AWS_SUPPORTED_REGIONS

# Environment Constants (Finding #10)
ENV_PRODUCTION = "production"
ENV_STAGING = "staging"
ENV_DEVELOPMENT = "development"
ENV_LOCAL = "local"


@lru_cache
def get_settings() -> "Settings":
    """Returns a singleton instance of the application settings."""
    # Production-grade: do not generate security-sensitive secrets at runtime.
    # Require explicit configuration via environment / .env for all non-test runs.
    return Settings()


class SecretReloader:
    """
    Zero Trust Logic: Periodically re-fetches secrets from
    external providers (AWS Secrets Manager, Vault) without restarts.
    """

    def __init__(self, settings: "Settings"):
        self.settings = settings
        self.logger = structlog.get_logger()

    async def reload_all(self) -> None:
        """Atomically update sensitive keys in the singleton settings."""
        self.logger.info("secret_reload_started")
        try:
            # Logic to fetch from AWS Secrets Manager or Vault
            # For now, we simulate a reload from environment (which would be
            # updated by sidecar or mutation hook in K8s)
            import os

            # Example: Atomic swap for critical keys
            if "DATABASE_URL" in os.environ:
                self.settings.DATABASE_URL = os.environ["DATABASE_URL"]

            if "PAYSTACK_SECRET_KEY" in os.environ:
                self.settings.PAYSTACK_SECRET_KEY = os.environ["PAYSTACK_SECRET_KEY"]

            self.logger.info("secret_reload_completed")
        except Exception as e:
            self.logger.error("secret_reload_failed", error=str(e))
            raise


class Settings(BaseSettings):
    """
    Main configuration for Valdrix AI.
    Uses Pydantic-Settings for environment variable parsing from .env.
    """

    APP_NAME: str = "Valdrix"
    VERSION: str = "0.1.0"
    DEBUG: bool = False
    # ENVIRONMENT options: local, development, staging, production
    # is_production property ensures strict security for 'production'
    ENVIRONMENT: str = ENV_DEVELOPMENT
    API_URL: str = "http://localhost:8000"  # Base URL for OIDC and Magic Links
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None  # Added for D5: Telemetry Sink
    OTEL_EXPORTER_OTLP_INSECURE: bool = False  # SEC-07: Secure Tracing
    CSRF_SECRET_KEY: Optional[str] = None  # SEC-01: CSRF
    TESTING: bool = False
    RATELIMIT_ENABLED: bool = True
    AUTOPILOT_BYPASS_GRACE_PERIOD: bool = False
    INTERNAL_JOB_SECRET: Optional[str] = None
    WEBHOOK_ALLOWED_DOMAINS: list[str] = []  # Allowlist for generic webhook retries
    WEBHOOK_REQUIRE_HTTPS: bool = True
    WEBHOOK_BLOCK_PRIVATE_IPS: bool = True
    SSE_MAX_CONNECTIONS_PER_TENANT: int = 5
    SSE_POLL_INTERVAL_SECONDS: int = 3

    @model_validator(mode="after")
    def validate_all_config(self) -> "Settings":
        """
        PRODUCTION-GRADE: Centralized validation orchestrator.
        Groups validation by concern for clarity and specificity.
        """
        if self.TESTING:
            return self

        self._validate_core_secrets()
        self._validate_database_config()
        self._validate_llm_config()
        self._validate_billing_config()
        self._validate_integration_config()
        self._validate_environment_safety()

        return self

    def _validate_core_secrets(self) -> None:
        """Validates critical security primitives (SEC-01, SEC-02, SEC-06)."""
        # Always require these to prevent encryption instability or insecure defaults.
        critical_keys = {
            "CSRF_SECRET_KEY": self.CSRF_SECRET_KEY,
            "ENCRYPTION_KEY": self.ENCRYPTION_KEY,
            "SUPABASE_JWT_SECRET": self.SUPABASE_JWT_SECRET,
        }

        for name, value in critical_keys.items():
            if not value or len(value) < 32:
                # Finding #C4: Explicitly reject placeholders or inadequate keys
                raise ValueError(f"{name} must be set to a secure value (>= 32 chars).")

        # KDF_SALT validation (Base64 check)
        if not self.KDF_SALT:
            raise ValueError("KDF_SALT must be set (base64-encoded random 32 bytes).")
        try:
            decoded_salt = base64.b64decode(self.KDF_SALT)
            if len(decoded_salt) != 32:
                raise ValueError("KDF_SALT must decode to exactly 32 bytes.")
        except Exception as exc:
            raise ValueError("KDF_SALT must be valid base64.") from exc

        if self.ENCRYPTION_KEY_CACHE_TTL_SECONDS < 60:
            raise ValueError("ENCRYPTION_KEY_CACHE_TTL_SECONDS must be >= 60.")
        if self.ENCRYPTION_KEY_CACHE_MAX_SIZE < 10:
            raise ValueError("ENCRYPTION_KEY_CACHE_MAX_SIZE must be >= 10.")

    def _validate_database_config(self) -> None:
        """Validates database and redis connectivity settings."""
        if self.is_production:
            if not self.DATABASE_URL:
                raise ValueError("DATABASE_URL is required in production.")

            # SEC-04: Database SSL Mode handled by Enum/Literal validation
            # in session.py, but we enforce production levels here.
            if self.DB_SSL_MODE not in ["require", "verify-ca", "verify-full"]:
                raise ValueError(
                    f"SECURITY ERROR: DB_SSL_MODE must be secure in production (current: {self.DB_SSL_MODE})."
                )

        # Redis URL construction fallback
        if not self.REDIS_URL and self.REDIS_HOST and self.REDIS_PORT:
            self.REDIS_URL = f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"

    def _validate_llm_config(self) -> None:
        """Validates LLM provider keys based on selection."""
        provider_keys = {
            "openai": self.OPENAI_API_KEY,
            "claude": self.CLAUDE_API_KEY,
            "anthropic": self.ANTHROPIC_API_KEY or self.CLAUDE_API_KEY,
            "google": self.GOOGLE_API_KEY,
            "groq": self.GROQ_API_KEY,
        }

        if self.LLM_PROVIDER in provider_keys and not provider_keys[self.LLM_PROVIDER]:
            if self.is_production:
                raise ValueError(
                    f"LLM_PROVIDER is '{self.LLM_PROVIDER}' but its API key is missing."
                )
            else:
                structlog.get_logger().info(
                    "llm_provider_key_missing_non_prod", provider=self.LLM_PROVIDER
                )

    def _validate_billing_config(self) -> None:
        """Validates Paystack credentials (SEC-P0)."""
        default_currency = (
            str(self.PAYSTACK_DEFAULT_CHECKOUT_CURRENCY or "NGN").strip().upper()
        )
        if default_currency not in {"NGN", "USD"}:
            raise ValueError(
                "PAYSTACK_DEFAULT_CHECKOUT_CURRENCY must be one of: NGN, USD."
            )

        if self.is_production:
            if not self.PAYSTACK_SECRET_KEY or self.PAYSTACK_SECRET_KEY.startswith(
                "sk_test"
            ):
                raise ValueError(
                    "PAYSTACK_SECRET_KEY must be a live key (sk_live_...) in production."
                )
            if not self.PAYSTACK_PUBLIC_KEY:
                raise ValueError("PAYSTACK_PUBLIC_KEY is required in production.")

            if default_currency == "USD" and not self.PAYSTACK_ENABLE_USD_CHECKOUT:
                raise ValueError(
                    "PAYSTACK_DEFAULT_CHECKOUT_CURRENCY cannot be USD when PAYSTACK_ENABLE_USD_CHECKOUT is false."
                )

    def _validate_integration_config(self) -> None:
        """Validates SaaS integration constraints."""
        if self.SAAS_STRICT_INTEGRATIONS:
            # Check if any env-based integration settings are accidentally used
            sconf = [
                self.SLACK_CHANNEL_ID,
                self.JIRA_BASE_URL,
                self.GITHUB_ACTIONS_TOKEN,
            ]
            if any(sconf) and self.is_production:
                raise ValueError(
                    "SAAS_STRICT_INTEGRATIONS forbids env-based settings in production."
                )

    def _validate_environment_safety(self) -> None:
        """Validates network and deployment safety (SEC-A1, SEC-A2)."""
        if self.is_production or self.ENVIRONMENT == "staging":
            if not self.ADMIN_API_KEY or len(self.ADMIN_API_KEY) < 32:
                raise ValueError(
                    "ADMIN_API_KEY must be >= 32 chars in staging/production."
                )

            # Safety Warnings (non-blocking but logged)
            logger = structlog.get_logger()

            # CORS localhost check
            if any("localhost" in o or "127.0.0.1" in o for o in self.CORS_ORIGINS):
                logger.warning("cors_localhost_in_production")

            # HTTPS Enforcement
            for url in [self.API_URL, self.FRONTEND_URL]:
                if url and url.startswith("http://"):
                    logger.warning("insecure_url_in_production", url=url)

    # AWS Credentials
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_DEFAULT_REGION: str = "us-east-1"
    AWS_ENDPOINT_URL: Optional[str] = (
        None  # Added for local testing (MotoServer/LocalStack)
    )

    # CloudFormation Template (Configurable for S3/GitHub)
    CLOUDFORMATION_TEMPLATE_URL: str = "https://raw.githubusercontent.com/valdrix/valdrix/main/cloudformation/valdrix-role.yaml"

    # Reload trigger: 2026-01-14

    # Security
    CORS_ORIGINS: list[str] = []  # Empty by default - restricted in prod
    FRONTEND_URL: str = "http://localhost:5173"  # Used for billing callbacks
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"  # High performance for complex analysis

    # Claude/Anthropic Credentials
    CLAUDE_API_KEY: Optional[str] = None
    CLAUDE_MODEL: str = "claude-3-7-sonnet"
    ANTHROPIC_API_KEY: Optional[str] = None  # Added for Phase 28 compatibility

    # Google Gemini Credentials
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_MODEL: str = "gemini-2.0-flash"

    # Groq Credentials
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # LLM Provider
    LLM_PROVIDER: str = "groq"  # Options: openai, claude, google, groq
    ENABLE_DELTA_ANALYSIS: bool = True  # Innovation 1: Reduce token usage by 90%
    DELTA_ANALYSIS_DAYS: int = 3
    # Disabled-by-default fairness guardrails for future "near-unlimited" tiers.
    # Keep OFF until production evidence gates are met.
    LLM_FAIR_USE_GUARDS_ENABLED: bool = False
    LLM_FAIR_USE_PRO_DAILY_SOFT_CAP: int = 1200
    LLM_FAIR_USE_ENTERPRISE_DAILY_SOFT_CAP: int = 4000
    LLM_FAIR_USE_PER_MINUTE_CAP: int = 30
    LLM_FAIR_USE_PER_TENANT_CONCURRENCY_CAP: int = 4
    LLM_FAIR_USE_CONCURRENCY_LEASE_TTL_SECONDS: int = 180

    # Scheduler
    SCHEDULER_HOUR: int = 8
    SCHEDULER_MINUTE: int = 0

    # Admin API Key
    ADMIN_API_KEY: Optional[str] = None

    # Database
    DATABASE_URL: Optional[str] = None  # Required in prod, optional in dev/test
    DB_SSL_MODE: str = "require"  # Options: disable, require, verify-ca, verify-full
    DB_SSL_CA_CERT_PATH: Optional[str] = (
        None  # Path to CA cert for verify-ca/verify-full modes
    )
    DB_POOL_SIZE: int = 20  # Standard for Supabase/Neon free tiers
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600
    DB_ECHO: bool = False
    # Tests default to in-memory sqlite to avoid accidental side-effects on real databases.
    # Set true to allow tests to use DATABASE_URL (e.g., integration tests against Postgres).
    ALLOW_TEST_DATABASE_URL: bool = False
    # Enable RLS enforcement listener in tests when running against Postgres.
    ENFORCE_RLS_IN_TESTS: bool = False

    # Supabase Auth
    SUPABASE_URL: Optional[str] = None
    SUPABASE_JWT_SECRET: Optional[str] = None  # Required for auth middleware

    # Notifications
    SAAS_STRICT_INTEGRATIONS: bool = False
    SLACK_BOT_TOKEN: Optional[str] = None
    SLACK_CHANNEL_ID: Optional[str] = None
    JIRA_BASE_URL: Optional[str] = None
    JIRA_EMAIL: Optional[str] = None
    JIRA_API_TOKEN: Optional[str] = None
    JIRA_PROJECT_KEY: Optional[str] = None
    JIRA_ISSUE_TYPE: str = "Task"
    JIRA_TIMEOUT_SECONDS: float = 10.0
    WORKFLOW_DISPATCH_TIMEOUT_SECONDS: float = 10.0
    WORKFLOW_EVIDENCE_BASE_URL: Optional[str] = None
    TEAMS_TIMEOUT_SECONDS: float = 10.0
    # Teams incoming webhooks are validated with SSRF controls and a domain allowlist.
    # This defaults to common Microsoft endpoints and can be overridden via env for self-host.
    TEAMS_WEBHOOK_ALLOWED_DOMAINS: list[str] = [
        "office.com",
        "office365.com",
        "webhook.office.com",
        "logic.azure.com",
        "powerautomate.com",
    ]
    TEAMS_WEBHOOK_REQUIRE_HTTPS: bool = True
    TEAMS_WEBHOOK_BLOCK_PRIVATE_IPS: bool = True

    # GitHub Actions workflow dispatch
    GITHUB_ACTIONS_ENABLED: bool = False
    GITHUB_ACTIONS_OWNER: Optional[str] = None
    GITHUB_ACTIONS_REPO: Optional[str] = None
    GITHUB_ACTIONS_WORKFLOW_ID: Optional[str] = None
    GITHUB_ACTIONS_REF: str = "main"
    GITHUB_ACTIONS_TOKEN: Optional[str] = None

    # GitLab CI trigger
    GITLAB_CI_ENABLED: bool = False
    GITLAB_CI_BASE_URL: str = "https://gitlab.com"
    GITLAB_CI_PROJECT_ID: Optional[str] = None
    GITLAB_CI_REF: str = "main"
    GITLAB_CI_TRIGGER_TOKEN: Optional[str] = None

    # Generic CI webhook trigger
    GENERIC_CI_WEBHOOK_ENABLED: bool = False
    GENERIC_CI_WEBHOOK_URL: Optional[str] = None
    GENERIC_CI_WEBHOOK_BEARER_TOKEN: Optional[str] = None

    # SMTP Email (for carbon alerts)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: str = "alerts@valdrix.ai"

    # GreenOps & Carbon APIs
    WATT_TIME_API_KEY: Optional[str] = None
    ELECTRICITY_MAPS_API_KEY: Optional[str] = None
    CARBON_LOW_INTENSITY_THRESHOLD: float = 250.0
    CARBON_INTENSITY_API_TIMEOUT_SECONDS: float = 5.0

    # OIDC / GCP Workload Identity
    GCP_OIDC_AUDIENCE: Optional[str] = None
    GCP_OIDC_STS_URL: str = "https://sts.googleapis.com/v1/token"
    GCP_OIDC_SCOPE: str = "https://www.googleapis.com/auth/cloud-platform"
    GCP_OIDC_VERIFY_TIMEOUT_SECONDS: int = 10

    # Encryption & Secret Rotation
    ENCRYPTION_KEY: Optional[str] = None
    PII_ENCRYPTION_KEY: Optional[str] = None
    API_KEY_ENCRYPTION_KEY: Optional[str] = None
    ENCRYPTION_FALLBACK_KEYS: list[str] = []
    ENCRYPTION_KEY_CACHE_TTL_SECONDS: int = 3600
    ENCRYPTION_KEY_CACHE_MAX_SIZE: int = 1000
    BLIND_INDEX_KEY: Optional[str] = None  # SEC-06: Separation of keys

    # KDF Settings for password-to-key derivation (SEC-06)
    # PRODUCTION FIX #6: Per-environment encryption salt (not hardcoded)
    # Set via environment variable: export KDF_SALT="<base64-encoded-random-32-bytes>"
    # Generate: python3 -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
    KDF_SALT: Optional[str] = None
    KDF_ITERATIONS: int = 100000

    # Cache (Redis for production, in-memory for dev)
    REDIS_URL: Optional[str] = None  # e.g., redis://localhost:6379
    REDIS_HOST: Optional[str] = None  # Added for K8s compatibility
    REDIS_PORT: Optional[str] = "6379"

    # Upstash Redis (Serverless - Free tier: 10K commands/day)
    UPSTASH_REDIS_URL: Optional[str] = None  # e.g., https://xxx.upstash.io
    UPSTASH_REDIS_TOKEN: Optional[str] = None

    # Paystack Billing (Nigeria Support)
    PAYSTACK_SECRET_KEY: Optional[str] = None
    PAYSTACK_PUBLIC_KEY: Optional[str] = None
    # Monthly plans
    PAYSTACK_PLAN_STARTER: Optional[str] = None
    PAYSTACK_PLAN_GROWTH: Optional[str] = None
    PAYSTACK_PLAN_PRO: Optional[str] = None
    PAYSTACK_PLAN_ENTERPRISE: Optional[str] = None
    # Annual plans (17% discount - 2 months free)
    PAYSTACK_PLAN_STARTER_ANNUAL: Optional[str] = None
    PAYSTACK_PLAN_GROWTH_ANNUAL: Optional[str] = None
    PAYSTACK_PLAN_PRO_ANNUAL: Optional[str] = None
    PAYSTACK_PLAN_ENTERPRISE_ANNUAL: Optional[str] = None
    PAYSTACK_DEFAULT_CHECKOUT_CURRENCY: str = "NGN"
    PAYSTACK_ENABLE_USD_CHECKOUT: bool = False

    # Circuit Breaker & Safety Guardrails (Phase 12)
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    CIRCUIT_BREAKER_RECOVERY_SECONDS: int = 300
    CIRCUIT_BREAKER_MAX_DAILY_SAVINGS: float = 1000.0
    CIRCUIT_BREAKER_CACHE_SIZE: int = 1000

    # REMEDIATION KILL SWITCH: Stop all deletions if daily cost impact hits $500
    REMEDIATION_KILL_SWITCH_THRESHOLD: float = 500.0
    REMEDIATION_KILL_SWITCH_SCOPE: str = "tenant"  # tenant or global
    ENFORCE_REMEDIATION_DRY_RUN: bool = False

    # Multi-Currency & Localization (Phase 12)
    SUPPORTED_CURRENCIES: list[str] = ["USD", "NGN", "EUR", "GBP"]
    EXCHANGE_RATE_SYNC_INTERVAL_HOURS: int = 24
    BASE_CURRENCY: str = "USD"
    WEBHOOK_IDEMPOTENCY_TTL_HOURS: int = 72  # L5: Move to settings

    # AWS Regions (BE-ADAPT-1: Regional Whitelist)
    AWS_SUPPORTED_REGIONS: list[str] = AWS_SUPPORTED_REGIONS

    # Scanner Settings
    ZOMBIE_PLUGIN_TIMEOUT_SECONDS: int = 30
    ZOMBIE_REGION_TIMEOUT_SECONDS: int = 120
    CLOUD_API_BUDGET_GOVERNOR_ENABLED: bool = True
    CLOUD_API_BUDGET_ENFORCE: bool = True
    # Daily per-tenant caps for expensive telemetry APIs.
    # 0 disables capping for the API.
    AWS_CLOUDWATCH_DAILY_CALL_BUDGET: int = 3000
    GCP_MONITORING_DAILY_CALL_BUDGET: int = 3000
    AZURE_MONITOR_DAILY_CALL_BUDGET: int = 3000
    # Estimated API costs per call used only for observability metrics.
    AWS_CLOUDWATCH_ESTIMATED_COST_PER_CALL_USD: float = 0.00001
    GCP_MONITORING_ESTIMATED_COST_PER_CALL_USD: float = 0.0
    AZURE_MONITOR_ESTIMATED_COST_PER_CALL_USD: float = 0.0

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    @property
    def is_production(self) -> bool:
        """
        True only when ENVIRONMENT is explicitly set to 'production'.
        This is used for high-security gates and billing enforcement.
        Note: Staging/Development use DEBUG=False but are NOT 'production'.
        """
        return self.ENVIRONMENT == "production"
