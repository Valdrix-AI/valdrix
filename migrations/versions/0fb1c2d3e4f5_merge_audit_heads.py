"""Merge audit remediation head with hard cap settings

Revision ID: 0fb1c2d3e4f5
Revises: 012_add_hard_cap_settings, 0ea1b2c3d4e5
Create Date: 2026-01-18 19:55:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0fb1c2d3e4f5'
down_revision = ('012_add_hard_cap_settings', '0ea1b2c3d4e5')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
