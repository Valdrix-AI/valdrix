"""
Notification Settings Model for Valdrics.
Stores per-tenant notification preferences.
"""

from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String, text, Uuid as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesEngine
# from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.models._encryption import get_encryption_key
from app.shared.db.base import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant



class NotificationSettings(Base):
    """Per-tenant notification preferences."""

    __tablename__ = "notification_settings"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )

    # Foreign key to tenant
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        unique=True,  # One settings record per tenant
        nullable=False,
    )

    # Slack configuration
    slack_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    slack_channel_override: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    jira_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    jira_base_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    jira_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    jira_project_key: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    jira_issue_type: Mapped[str] = mapped_column(String(64), default="Task")
    jira_api_token: Mapped[Optional[str]] = mapped_column(
        StringEncryptedType(String(1024), get_encryption_key, AesEngine, "pkcs5"),
        nullable=True,
    )

    # Microsoft Teams (tenant-scoped channel notifications)
    teams_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    teams_webhook_url: Mapped[Optional[str]] = mapped_column(
        StringEncryptedType(String(1024), get_encryption_key, AesEngine, "pkcs5"),
        nullable=True,
    )

    # Workflow automation (tenant-scoped SaaS integrations)
    workflow_github_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    workflow_github_owner: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    workflow_github_repo: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    workflow_github_workflow_id: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    workflow_github_ref: Mapped[str] = mapped_column(String(100), default="main")
    workflow_github_token: Mapped[Optional[str]] = mapped_column(
        StringEncryptedType(String(1024), get_encryption_key, AesEngine, "pkcs5"),
        nullable=True,
    )

    workflow_gitlab_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    workflow_gitlab_base_url: Mapped[str] = mapped_column(
        String(255), default="https://gitlab.com"
    )
    workflow_gitlab_project_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    workflow_gitlab_ref: Mapped[str] = mapped_column(String(100), default="main")
    workflow_gitlab_trigger_token: Mapped[Optional[str]] = mapped_column(
        StringEncryptedType(String(1024), get_encryption_key, AesEngine, "pkcs5"),
        nullable=True,
    )

    workflow_webhook_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    workflow_webhook_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    workflow_webhook_bearer_token: Mapped[Optional[str]] = mapped_column(
        StringEncryptedType(String(1024), get_encryption_key, AesEngine, "pkcs5"),
        nullable=True,
    )

    # Digest schedule: "daily", "weekly", "disabled"
    digest_schedule: Mapped[str] = mapped_column(String(20), default="daily")
    digest_hour: Mapped[int] = mapped_column(default=9)  # 24-hour format, UTC
    digest_minute: Mapped[int] = mapped_column(default=0)

    # Alert preferences
    alert_on_budget_warning: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_on_budget_exceeded: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_on_carbon_budget_warning: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_on_carbon_budget_exceeded: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_on_zombie_detected: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps are inherited from Base

    # Relationship
    tenant: Mapped["Tenant"] = relationship(
        "Tenant", back_populates="notification_settings"
    )

    def __repr__(self) -> str:
        return f"<NotificationSettings tenant={self.tenant_id} schedule={self.digest_schedule}>"
