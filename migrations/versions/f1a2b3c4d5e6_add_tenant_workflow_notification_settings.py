"""add tenant workflow notification settings

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-02-13 09:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_settings",
        sa.Column("workflow_github_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "notification_settings",
        sa.Column("workflow_github_owner", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "notification_settings",
        sa.Column("workflow_github_repo", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "notification_settings",
        sa.Column("workflow_github_workflow_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "notification_settings",
        sa.Column("workflow_github_ref", sa.String(length=100), nullable=False, server_default=sa.text("'main'")),
    )
    op.add_column(
        "notification_settings",
        sa.Column("workflow_github_token", sa.String(length=1024), nullable=True),
    )

    op.add_column(
        "notification_settings",
        sa.Column("workflow_gitlab_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "notification_settings",
        sa.Column(
            "workflow_gitlab_base_url",
            sa.String(length=255),
            nullable=False,
            server_default=sa.text("'https://gitlab.com'"),
        ),
    )
    op.add_column(
        "notification_settings",
        sa.Column("workflow_gitlab_project_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "notification_settings",
        sa.Column("workflow_gitlab_ref", sa.String(length=100), nullable=False, server_default=sa.text("'main'")),
    )
    op.add_column(
        "notification_settings",
        sa.Column("workflow_gitlab_trigger_token", sa.String(length=1024), nullable=True),
    )

    op.add_column(
        "notification_settings",
        sa.Column("workflow_webhook_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "notification_settings",
        sa.Column("workflow_webhook_url", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "notification_settings",
        sa.Column("workflow_webhook_bearer_token", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_settings", "workflow_webhook_bearer_token")
    op.drop_column("notification_settings", "workflow_webhook_url")
    op.drop_column("notification_settings", "workflow_webhook_enabled")
    op.drop_column("notification_settings", "workflow_gitlab_trigger_token")
    op.drop_column("notification_settings", "workflow_gitlab_ref")
    op.drop_column("notification_settings", "workflow_gitlab_project_id")
    op.drop_column("notification_settings", "workflow_gitlab_base_url")
    op.drop_column("notification_settings", "workflow_gitlab_enabled")
    op.drop_column("notification_settings", "workflow_github_token")
    op.drop_column("notification_settings", "workflow_github_ref")
    op.drop_column("notification_settings", "workflow_github_workflow_id")
    op.drop_column("notification_settings", "workflow_github_repo")
    op.drop_column("notification_settings", "workflow_github_owner")
    op.drop_column("notification_settings", "workflow_github_enabled")
