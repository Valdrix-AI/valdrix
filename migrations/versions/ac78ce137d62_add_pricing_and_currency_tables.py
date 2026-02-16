"""Add pricing and currency tables

Revision ID: ac78ce137d62
Revises: c79ea79de972
Create Date: 2026-01-17 20:50:49.910496

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ac78ce137d62'
down_revision: Union[str, Sequence[str], None] = 'c79ea79de972'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy.dialects import postgresql

    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. Create exchange_rates table
    if 'exchange_rates' not in tables:
        op.create_table('exchange_rates',
            sa.Column('from_currency', sa.String(length=3), nullable=False),
            sa.Column('to_currency', sa.String(length=3), nullable=False),
            sa.Column('rate', sa.Numeric(precision=10, scale=4), nullable=False),
            sa.Column('provider', sa.String(length=50), nullable=False),
            sa.Column('last_updated', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.PrimaryKeyConstraint('from_currency', 'to_currency', name=op.f('pk_exchange_rates'))
        )
    else:
        print("Table 'exchange_rates' already exists, skipping creation.")

    # 2. Create pricing_plans table
    if 'pricing_plans' not in tables:
        op.create_table('pricing_plans',
            sa.Column('id', sa.String(length=50), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('description', sa.String(length=500), nullable=True),
            sa.Column('price_usd', sa.Numeric(precision=10, scale=2), nullable=False),
            sa.Column('features', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column('limits', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column('display_features', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column('cta_text', sa.String(length=50), nullable=False),
            sa.Column('is_popular', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_pricing_plans'))
        )
    else:
        print("Table 'pricing_plans' already exists, skipping creation.")

    # 3. Add paystack_auth_code to tenant_subscriptions
    # SEC-10: Encryption is handled at the application layer before storage
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'tenant_subscriptions' in inspector.get_table_names():
        op.add_column('tenant_subscriptions', sa.Column('paystack_auth_code', sa.String(length=255), nullable=True))
    else:
        print("Table 'tenant_subscriptions' does not exist, skipping column addition.")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tenant_subscriptions', 'paystack_auth_code')
    op.drop_table('pricing_plans')
    op.drop_table('exchange_rates')
