"""add last_ingested_at to aws_connections

Revision ID: f5g6h7i8j9k0
Revises: d4e5f6a7b8c9
Create Date: 2024-03-20 12:05:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f5g6h7i8j9k0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None

def upgrade():
    # Add last_ingested_at to aws_connections
    op.add_column('aws_connections', sa.Column('last_ingested_at', sa.DateTime(timezone=True), nullable=True))

def downgrade():
    # Remove last_ingested_at from aws_connections
    op.drop_column('aws_connections', 'last_ingested_at')
