"""add tenant jira notification settings

Revision ID: d7e8f9a0b1c2
Revises: c4f5d6e7a8b9
Create Date: 2026-02-12 22:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, Sequence[str], None] = "c4f5d6e7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notification_settings",
        sa.Column("jira_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "notification_settings",
        sa.Column("jira_base_url", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "notification_settings",
        sa.Column("jira_email", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "notification_settings",
        sa.Column("jira_project_key", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "notification_settings",
        sa.Column("jira_issue_type", sa.String(length=64), nullable=False, server_default="Task"),
    )
    op.add_column(
        "notification_settings",
        sa.Column("jira_api_token", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_settings", "jira_api_token")
    op.drop_column("notification_settings", "jira_issue_type")
    op.drop_column("notification_settings", "jira_project_key")
    op.drop_column("notification_settings", "jira_email")
    op.drop_column("notification_settings", "jira_base_url")
    op.drop_column("notification_settings", "jira_enabled")
