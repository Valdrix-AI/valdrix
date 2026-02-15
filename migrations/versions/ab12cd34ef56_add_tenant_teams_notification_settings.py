"""add tenant microsoft teams notification settings

Revision ID: bc12cd34ef56
Revises: cd8320390f08
Create Date: 2026-02-15 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "bc12cd34ef56"
down_revision = "cd8320390f08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_settings",
        sa.Column(
            "teams_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "notification_settings",
        sa.Column("teams_webhook_url", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_settings", "teams_webhook_url")
    op.drop_column("notification_settings", "teams_enabled")

