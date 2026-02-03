"""
LLM Usage Tracking Model

This model stores every LLM API call for cost tracking and analytics.
Each record captures: who made the call (tenant), what model was used,
how many tokens were consumed, and the calculated cost.

Why this matters:
- Bill users accurately for AI usage (future pricing tiers)
- Optimize prompts (see which cost the most)
- Analytics dashboard (AI spend over time)
"""

from uuid import uuid4, UUID
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, Integer, Numeric, ForeignKey, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.ext.hybrid import hybrid_property

from app.shared.core.security import encrypt_string, decrypt_string
from app.shared.db.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class LLMUsage(Base):
    """
    Tracks individual LLM API calls for cost analytics.

    Example usage:
        usage = LLMUsage(
            tenant_id=current_user.tenant_id,
            provider="groq",
            model="llama-3.3-70b-versatile",
            input_tokens=1500,
            output_tokens=800,
            total_tokens=2300,
            cost_usd=0.0015,
            request_type="daily_analysis"
        )
        db.add(usage)
        await db.commit()
    """

    __tablename__ = "llm_usage"

    # Primary Key: UUID prevents enumeration attacks
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign Key: Links this record to a tenant
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # Fast filtering by tenant
    )

    # Provider: Which company's API (openai, anthropic, groq)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)

    # Model: Specific model used (gpt-4o, claude-3-sonnet, llama-3.3-70b)
    model: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Token counts: The currency of LLM pricing
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Cost in USD: Calculated at time of call
    cost_usd: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False, default=0)

    # Request Type: What was this LLM call for?
    request_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    # Trace ID for debugging/auditing
    operation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # is_byok: True if the user's personal API key was used
    is_byok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Timestamp when this usage record was created
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True
    )

    # Relationship: Access the tenant object
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="llm_usage")

    def __repr__(self):
        """String representation for debugging."""
        return f"<LLMUsage {self.model} ${self.cost_usd:.6f}>"



class LLMBudget(Base):
    """
    Tracks monthly LLM usage budget per tenant.

    Enables:
    - Soft alerts: Notify when usage hits threshold (e.g., 80%)
    - Hard limits: Optionally block requests when budget exceeded
    - Cost control: Prevent surprise AI bills
    - BYOK: Securely store tenant API keys with transparent encryption
    """

    __tablename__ = "llm_budgets"

    # Primary Key
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign Key: One budget per tenant
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # One budget per tenant
        index=True,
    )

    # Monthly limit in USD (e.g., $10.00)
    monthly_limit_usd: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=10.00)

    # Alert threshold percentage (e.g., 80 = alert at 80% usage)
    alert_threshold_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=80)

    # Hard limit: If True, block LLM requests when budget exceeded
    hard_limit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # AI Strategy: Per-tenant model and provider selection
    preferred_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="groq")
    preferred_model: Mapped[str] = mapped_column(String(100), nullable=False, default="llama-3.3-70b-versatile")

    # Underlying columns for API Key Overrides (storing encrypted data)
    _openai_api_key: Mapped[str | None] = mapped_column("openai_api_key", String(512), nullable=True)
    _claude_api_key: Mapped[str | None] = mapped_column("claude_api_key", String(512), nullable=True)
    _google_api_key: Mapped[str | None] = mapped_column("google_api_key", String(512), nullable=True)
    _groq_api_key: Mapped[str | None] = mapped_column("groq_api_key", String(512), nullable=True)

    # Hybrid properties for transparent encryption/decryption
    @hybrid_property
    def openai_api_key(self):
        return decrypt_string(self._openai_api_key)

    @openai_api_key.setter
    def openai_api_key(self, value):
        self._openai_api_key = encrypt_string(value) if value else None

    @hybrid_property
    def claude_api_key(self):
        return decrypt_string(self._claude_api_key)

    @claude_api_key.setter
    def claude_api_key(self, value):
        self._claude_api_key = encrypt_string(value) if value else None

    @hybrid_property
    def google_api_key(self):
        return decrypt_string(self._google_api_key)

    @google_api_key.setter
    def google_api_key(self, value):
        self._google_api_key = encrypt_string(value) if value else None

    @hybrid_property
    def groq_api_key(self):
        return decrypt_string(self._groq_api_key)

    @groq_api_key.setter
    def groq_api_key(self, value):
        self._groq_api_key = encrypt_string(value) if value else None

    # Track when alert was sent (avoid spam)
    alert_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="llm_budget")

    def __repr__(self):
        return f"<LLMBudget ${self.monthly_limit_usd}/month>"
