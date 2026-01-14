"""Migration: Update tenant_subscriptions for Paystack

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-01-13 06:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, Sequence[str], None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Migrate columns from Stripe to Paystack naming."""
    
    # Rename columns to generic or Paystack specific
    op.alter_column('tenant_subscriptions', 'stripe_customer_id', 
                    new_column_name='paystack_customer_code')
    op.alter_column('tenant_subscriptions', 'stripe_subscription_id', 
                    new_column_name='paystack_subscription_code')
    
    # Add Paystack specific columns
    op.add_column('tenant_subscriptions', 
                  sa.Column('paystack_email_token', sa.String(255), nullable=True))
    op.add_column('tenant_subscriptions', 
                  sa.Column('next_payment_date', sa.DateTime(timezone=True), nullable=True))

    # Drop old indexes and create new ones
    op.execute('DROP INDEX IF EXISTS ix_tenant_subscriptions_stripe_customer_id')
    op.create_index(
        op.f('ix_tenant_subscriptions_paystack_customer_code'),
        'tenant_subscriptions',
        ['paystack_customer_code'],
        unique=False
    )


def downgrade() -> None:
    """Revert changes."""
    op.drop_index(op.f('ix_tenant_subscriptions_paystack_customer_code'), table_name='tenant_subscriptions')
    op.drop_column('tenant_subscriptions', 'next_payment_date')
    op.drop_column('tenant_subscriptions', 'paystack_email_token')
    
    op.alter_column('tenant_subscriptions', 'paystack_subscription_code', 
                    new_column_name='stripe_subscription_id')
    op.alter_column('tenant_subscriptions', 'paystack_customer_code', 
                    new_column_name='stripe_customer_id')
    
    op.create_index(
        'ix_tenant_subscriptions_stripe_customer_id',
        'tenant_subscriptions',
        ['stripe_customer_id'],
        unique=False
    )
