from functools import lru_cache
from threading import Lock
from typing import Optional
import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator
from app.shared.core.constants import AWS_SUPPORTED_REGIONS
from app.shared.core.config_validation import (
    normalize_branding as _normalize_branding_impl,
    validate_all_config as _validate_all_config_impl,
    validate_billing_config as _validate_billing_config_impl,
    validate_core_secrets as _validate_core_secrets_impl,
    validate_database_config as _validate_database_config_impl,
    validate_enforcement_guardrails as _validate_enforcement_guardrails_impl,
    validate_environment_safety as _validate_environment_safety_impl,
    validate_integration_config as _validate_integration_config_impl,
    validate_llm_config as _validate_llm_config_impl,
    validate_remediation_guardrails as _validate_remediation_guardrails_impl,
    validate_turnstile_config as _validate_turnstile_config_impl,
)
from app.shared.core.config_validation_observability import (
    validate_observability_config as _validate_observability_config_impl,
)

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

_settings_reload_lock = Lock()
SETTINGS_RELOAD_CACHE_REFRESH_RECOVERABLE_EXCEPTIONS = (ImportError, AttributeError, RuntimeError, TypeError, ValueError)
def reload_settings_from_environment() -> "Settings":
    """
    Atomically refresh the cached settings from current environment values.

    The singleton is updated in place so modules that captured the settings
    object during import still observe refreshed values after reload.
    """
    logger = structlog.get_logger()
    with _settings_reload_lock:
        logger.info("settings_reload_started")
        current = get_settings()
        refreshed = Settings()
        for field_name in refreshed.model_dump().keys():
            setattr(current, field_name, getattr(refreshed, field_name))
        try:
            from app.shared.core.security import EncryptionKeyManager

            EncryptionKeyManager.clear_key_caches(warm=True)
        except SETTINGS_RELOAD_CACHE_REFRESH_RECOVERABLE_EXCEPTIONS as cache_exc:  # pragma: no cover - defensive path
            logger.warning("settings_reload_cache_refresh_failed", error=str(cache_exc))
        logger.info("settings_reload_completed")
        return current


class Settings(BaseSettings):
    """
    Main configuration for Valdrics AI.
    Uses Pydantic-Settings for environment variable parsing from .env.
    """

    APP_NAME: str = "Valdrics"
    VERSION: str = "0.1.0"
    APP_VERSION: Optional[str] = None
    DEBUG: bool = False
    # ENVIRONMENT options: local, development, staging, production
    # is_production property ensures strict security for 'production'
    ENVIRONMENT: str = ENV_DEVELOPMENT
    API_URL: str = "http://localhost:8000"  # Base URL for OIDC and Magic Links
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None  # Added for D5: Telemetry Sink
    OTEL_EXPORTER_OTLP_INSECURE: bool = False  # SEC-07: Secure Tracing
    OTEL_LOGS_EXPORT_ENABLED: bool = True
    CSRF_SECRET_KEY: Optional[str] = None  # SEC-01: CSRF
    CSRF_TEST_SECRET_KEY: Optional[str] = None
    TESTING: bool = False
    PYTEST_CURRENT_TEST: Optional[str] = None
    SENTRY_DSN: Optional[str] = None
    EXPOSE_API_DOCUMENTATION_PUBLICLY: bool = False
    WEB_CONCURRENCY: int = 2
    APP_RUNTIME_DATA_DIR: str = "/tmp/valdrics"
    RATELIMIT_ENABLED: bool = True
    # In staging/production, distributed rate limiting is required by default.
    # This override exists only for controlled break-glass situations.
    ALLOW_IN_MEMORY_RATE_LIMITS: bool = False
    AUTOPILOT_BYPASS_GRACE_PERIOD: bool = False
    TURNSTILE_ENABLED: bool = False
    TURNSTILE_ENFORCE_IN_TESTING: bool = False
    TURNSTILE_SECRET_KEY: Optional[str] = None
    TURNSTILE_VERIFY_URL: str = (
        "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    )
    TURNSTILE_TIMEOUT_SECONDS: float = 3.0
    TURNSTILE_FAIL_OPEN: bool = False
    TURNSTILE_REQUIRE_PUBLIC_ASSESSMENT: bool = True
    TURNSTILE_REQUIRE_SSO_DISCOVERY: bool = True
    TURNSTILE_REQUIRE_ONBOARD: bool = True
    INTERNAL_JOB_SECRET: Optional[str] = None
    WEBHOOK_ALLOWED_DOMAINS: list[str] = []  # Allowlist for generic webhook retries
    WEBHOOK_REQUIRE_HTTPS: bool = True
    WEBHOOK_BLOCK_PRIVATE_IPS: bool = True
    MARKETING_SUBSCRIBE_WEBHOOK_URL: Optional[str] = None
    # Only trust X-Forwarded-For when the deployment path is explicitly trusted.
    TRUST_PROXY_HEADERS: bool = False
    # Number of trusted reverse-proxy hops when resolving client IP from XFF.
    # 1 = trust the nearest proxy and use the right-most forwarded address.
    TRUSTED_PROXY_HOPS: int = 1
    # Explicit proxy network allowlist used before trusting X-Forwarded-For.
    TRUSTED_PROXY_CIDRS: list[str] = []
    SSE_MAX_CONNECTIONS_PER_TENANT: int = 5
    SSE_POLL_INTERVAL_SECONDS: int = 3

    @model_validator(mode="after")
    def validate_all_config(self) -> "Settings":
        """
        PRODUCTION-GRADE: Centralized validation orchestrator.
        Groups validation by concern for clarity and specificity.
        """
        _validate_all_config_impl(
            self,
            env_production=ENV_PRODUCTION,
            env_staging=ENV_STAGING,
        )
        return self

    def _normalize_branding(self) -> None:
        """Normalize branding aliases to canonical public product name."""
        _normalize_branding_impl(self)

    def _validate_core_secrets(self) -> None:
        """Validate critical security primitives (SEC-01/SEC-02/SEC-06)."""
        _validate_core_secrets_impl(self)

    def _validate_database_config(self) -> None:
        """Validate database and cache connectivity settings."""
        _validate_database_config_impl(self, is_production=self.is_production)

    def _validate_llm_config(self) -> None:
        """Validate LLM provider key posture and abuse bounds."""
        _validate_llm_config_impl(self, is_production=self.is_production)

    def _validate_billing_config(self) -> None:
        """Validate billing/provider credentials and webhook allowlist."""
        _validate_billing_config_impl(self, is_production=self.is_production)

    def _validate_turnstile_config(self) -> None:
        """Validate Turnstile anti-bot controls for public/auth surfaces."""
        _validate_turnstile_config_impl(
            self,
            env_production=ENV_PRODUCTION,
            env_staging=ENV_STAGING,
        )

    def _validate_integration_config(self) -> None:
        """Validate SaaS integration strict-mode constraints."""
        _validate_integration_config_impl(self, is_production=self.is_production)

    def _validate_environment_safety(self) -> None:
        """Validate network and deployment safety (SEC-A1/SEC-A2)."""
        _validate_environment_safety_impl(
            self,
            env_production=ENV_PRODUCTION,
            env_staging=ENV_STAGING,
        )

    def _validate_observability_config(self) -> None:
        """Validate observability sink posture for strict environments."""
        _validate_observability_config_impl(
            self,
            env_production=ENV_PRODUCTION,
            env_staging=ENV_STAGING,
        )

    def _validate_remediation_guardrails(self) -> None:
        """Validate remediation kill-switch and scope guardrails."""
        _validate_remediation_guardrails_impl(
            self,
            env_production=ENV_PRODUCTION,
            env_staging=ENV_STAGING,
        )

    def _validate_enforcement_guardrails(self) -> None:
        """Validate enforcement gate runtime safety controls."""
        _validate_enforcement_guardrails_impl(self)

    # AWS Credentials
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_DEFAULT_REGION: str = "us-east-1"
    AWS_ENDPOINT_URL: Optional[str] = (
        None  # Added for local testing (MotoServer/LocalStack)
    )

    # CloudFormation Template (Configurable for S3/GitHub)
    CLOUDFORMATION_TEMPLATE_URL: str = "https://raw.githubusercontent.com/valdrics/valdrics/main/cloudformation/valdrics-role.yaml"

    # Reload trigger: 2026-01-14

    # Security
    CORS_ORIGINS: list[str] = []  # Empty by default - restricted in prod
    FRONTEND_URL: str = "http://localhost:5173"  # Used for billing callbacks
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"  # High performance for complex analysis

    # Claude/Anthropic Credentials
    CLAUDE_API_KEY: Optional[str] = None
    CLAUDE_MODEL: str = "claude-3-7-sonnet"
    ANTHROPIC_API_KEY: Optional[str] = None

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
    # Forecasting policy in strict environments (staging/production):
    # false -> require Prophet at startup (default)
    # true  -> allow temporary Holt-Winters break-glass fallback
    FORECASTER_ALLOW_HOLT_WINTERS_FALLBACK: bool = False
    # Break-glass audit metadata when fallback is enabled in strict env.
    FORECASTER_BREAK_GLASS_REASON: Optional[str] = None
    FORECASTER_BREAK_GLASS_EXPIRES_AT: Optional[str] = None
    FORECASTER_BREAK_GLASS_MAX_DURATION_HOURS: int = 168
    # Disabled-by-default fairness guardrails for future "near-unlimited" tiers.
    # Keep OFF until production evidence gates are met.
    LLM_FAIR_USE_GUARDS_ENABLED: bool = False
    LLM_FAIR_USE_PRO_DAILY_SOFT_CAP: int = 1200
    LLM_FAIR_USE_ENTERPRISE_DAILY_SOFT_CAP: int = 4000
    LLM_FAIR_USE_PER_MINUTE_CAP: int = 30
    LLM_FAIR_USE_PER_TENANT_CONCURRENCY_CAP: int = 4
    LLM_FAIR_USE_CONCURRENCY_LEASE_TTL_SECONDS: int = 180
    LLM_GLOBAL_ABUSE_GUARDS_ENABLED: bool = True
    LLM_GLOBAL_ABUSE_PER_MINUTE_CAP: int = 600
    LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD: int = 30
    LLM_GLOBAL_ABUSE_BLOCK_SECONDS: int = 120
    LLM_GLOBAL_ABUSE_KILL_SWITCH: bool = False

    # Scheduler
    ENABLE_SCHEDULER: bool = True
    SCHEDULER_HOUR: int = 8
    SCHEDULER_MINUTE: int = 0
    # Bound system-scope sweeps to reduce blast radius during incident conditions.
    SCHEDULER_SYSTEM_SWEEP_MAX_TENANTS: int = 5000
    SCHEDULER_SYSTEM_SWEEP_MAX_CONNECTIONS: int = 5000
    # Background job retention (terminal states) enforced by maintenance sweep.
    BACKGROUND_JOB_COMPLETED_RETENTION_DAYS: int = 7
    BACKGROUND_JOB_DEAD_LETTER_RETENTION_DAYS: int = 30
    BACKGROUND_JOB_RETENTION_PURGE_BATCH_SIZE: int = 1000
    BACKGROUND_JOB_RETENTION_PURGE_MAX_BATCHES: int = 20
    # Cost-record retention is plan-aware and enforced by the maintenance sweep.
    COST_RECORD_RETENTION_PURGE_BATCH_SIZE: int = 5000
    COST_RECORD_RETENTION_PURGE_MAX_BATCHES: int = 50
    # Scheduler distributed lock should fail-closed by default.
    # Enable only as temporary emergency bypass.
    SCHEDULER_LOCK_FAIL_OPEN: bool = False
    TENANT_ISOLATION_EVIDENCE_MAX_AGE_HOURS: int = 168

    # Admin API Key
    ADMIN_API_KEY: Optional[str] = None

    # Database
    DATABASE_URL: Optional[str] = None  # Required in prod, optional in dev/test
    DB_SSL_MODE: str = "require"  # Options: disable, require, verify-ca, verify-full
    DB_SSL_CA_CERT_PATH: Optional[str] = (
        None  # Path to CA cert for verify-ca/verify-full modes
    )
    # Conservative default for broad compatibility; tune based on worker count and DB capacity.
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600
    DB_ECHO: bool = False
    DB_SLOW_QUERY_THRESHOLD_SECONDS: float = 0.2
    # Set true only when an external DB pooler (e.g. Supavisor transaction pooler)
    # is explicitly used and double-pooling is undesirable.
    DB_USE_NULL_POOL: bool = False
    DB_EXTERNAL_POOLER: bool = False
    # Tests default to in-memory sqlite to avoid accidental side-effects on real databases.
    # Set true to allow tests to use DATABASE_URL (e.g., integration tests against Postgres).
    ALLOW_TEST_DATABASE_URL: bool = False
    # Enable RLS enforcement listener in tests when running against Postgres.
    ENFORCE_RLS_IN_TESTS: bool = True

    # Supabase Auth
    SUPABASE_URL: Optional[str] = None
    SUPABASE_JWT_SECRET: Optional[str] = None  # Required for auth middleware
    SUPABASE_JWT_ISSUER: str = "supabase"
    JWT_SIGNING_KID: Optional[str] = None

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
    JIRA_ALLOWED_DOMAINS: list[str] = ["atlassian.net"]
    JIRA_REQUIRE_HTTPS: bool = True
    JIRA_BLOCK_PRIVATE_IPS: bool = True
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
    SMTP_FROM: str = "alerts@valdrics.ai"

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
    # Blind index key-stretching to slow offline guessing if key material is exposed.
    BLIND_INDEX_KDF_ITERATIONS: int = 50000

    # Cache (Redis for production, in-memory for dev)
    REDIS_URL: Optional[str] = None  # e.g., redis://localhost:6379
    REDIS_HOST: Optional[str] = None
    REDIS_PORT: Optional[str] = "6379"

    # Upstash Redis (Serverless - Free tier: 10K commands/day)
    UPSTASH_REDIS_URL: Optional[str] = None  # e.g., https://xxx.upstash.io
    UPSTASH_REDIS_TOKEN: Optional[str] = None

    # Paystack Billing (Nigeria Support)
    PAYSTACK_SECRET_KEY: Optional[str] = None
    PAYSTACK_PUBLIC_KEY: Optional[str] = None
    # Explicit offline-validation escape hatch for CI contract checks.
    # Never enable this in real staging/production deployments.
    ALLOW_SYNTHETIC_BILLING_KEYS_FOR_VALIDATION: bool = False
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
    PAYSTACK_WEBHOOK_ALLOWED_IPS: list[str] = [
        "52.31.139.75",
        "52.49.173.169",
        "52.214.14.220",
    ]

    # Circuit Breaker & Safety Guardrails (Phase 12)
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    CIRCUIT_BREAKER_RECOVERY_SECONDS: int = 300
    CIRCUIT_BREAKER_MAX_DAILY_SAVINGS: float = 1000.0
    CIRCUIT_BREAKER_CACHE_SIZE: int = 1000
    # Redis-backed state is the default deployment posture for multi-worker safety.
    CIRCUIT_BREAKER_DISTRIBUTED_STATE: bool = True
    CIRCUIT_BREAKER_DISTRIBUTED_KEY_PREFIX: str = "valdrics:circuit"
    # REMEDIATION KILL SWITCH: Stop all deletions if daily cost impact hits $500
    REMEDIATION_KILL_SWITCH_THRESHOLD: float = 500.0
    REMEDIATION_KILL_SWITCH_SCOPE: str = Field(
        default="tenant", description="Scope: global or tenant"
    )
    REMEDIATION_KILL_SWITCH_ALLOW_GLOBAL_SCOPE: bool = False
    ENFORCE_REMEDIATION_DRY_RUN: bool = False
    ENFORCEMENT_GATE_TIMEOUT_SECONDS: float = 2.0
    ENFORCEMENT_GLOBAL_ABUSE_GUARD_ENABLED: bool = True
    ENFORCEMENT_GLOBAL_GATE_PER_MINUTE_CAP: int = 1200
    ENFORCEMENT_EXPORT_SIGNING_SECRET: Optional[str] = None
    ENFORCEMENT_EXPORT_SIGNING_KID: str = "enforcement-export-hmac-v1"
    ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS: int = 86400
    ENFORCEMENT_RECONCILIATION_SWEEP_ENABLED: bool = True
    ENFORCEMENT_RECONCILIATION_SWEEP_MAX_RELEASES: int = 500
    ENFORCEMENT_RECONCILIATION_EXCEPTION_SCAN_LIMIT: int = 200
    ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_THRESHOLD_USD: float = 100.0
    ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_EXCEPTION_COUNT: int = 5
    ENFORCEMENT_EXPORT_MAX_DAYS: int = 366
    ENFORCEMENT_EXPORT_MAX_ROWS: int = 10000
    ENFORCEMENT_APPROVAL_TOKEN_FALLBACK_SECRETS: list[str] = []

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
    # Bound export window size to keep CSV export queries predictable.
    FOCUS_EXPORT_MAX_DAYS: int = 366

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    @property
    def is_production(self) -> bool:
        """
        True only when ENVIRONMENT is explicitly set to 'production'.
        This is used for high-security gates and billing enforcement.
        Note: Staging/Development use DEBUG=False but are NOT 'production'.
        """
        return self.ENVIRONMENT == "production"

    @property
    def is_strict_environment(self) -> bool:
        """True for staging/production where enterprise controls must fail closed."""
        return self.ENVIRONMENT in {ENV_STAGING, ENV_PRODUCTION}
