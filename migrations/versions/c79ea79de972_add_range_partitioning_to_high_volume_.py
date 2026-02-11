"""add_range_partitioning_to_high_volume_tables

Revision ID: c79ea79de972
Revises: a7604ecc1442
Create Date: 2026-01-16 17:22:57.084365

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c79ea79de972'
down_revision: Union[str, Sequence[str], None] = 'a7604ecc1442'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Implement range partitioning for audit_logs and cost_records."""
    
    # 1. Audit Logs (New Table)
    op.execute("""
        CREATE TABLE audit_logs (
            id UUID NOT NULL,
            tenant_id UUID NOT NULL,
            event_type VARCHAR(50) NOT NULL,
            event_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
            actor_id UUID,
            actor_email VARCHAR(255),
            actor_ip VARCHAR(45),
            correlation_id VARCHAR(36),
            request_method VARCHAR(10),
            request_path VARCHAR(500),
            resource_type VARCHAR(50),
            resource_id VARCHAR(255),
            details JSONB,
            success BOOLEAN NOT NULL,
            error_message TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            PRIMARY KEY (id, event_timestamp)
        ) PARTITION BY RANGE (event_timestamp);
    """)

    # 2. Cost Records (Migration to Partitioned)
    # Step A: Rename existing
    op.execute("ALTER TABLE cost_records RENAME TO cost_records_old")
    # Drop existing indexes and constraints on old table to avoid name conflicts with new ones
    op.execute("DROP INDEX IF EXISTS ix_cost_records_recorded_at")
    op.execute("DROP INDEX IF EXISTS ix_cost_records_service")
    op.execute("DROP INDEX IF EXISTS ix_cost_records_tenant_id")
    op.execute("ALTER TABLE cost_records_old DROP CONSTRAINT IF EXISTS uix_account_cost_granularity")

    
    # Step B: Create Partitioned Root
    op.execute("""
        CREATE TABLE cost_records (
            id UUID NOT NULL,
            tenant_id UUID NOT NULL,
            account_id UUID NOT NULL,
            service VARCHAR NOT NULL,
            region VARCHAR,
            usage_type VARCHAR,
            cost_usd NUMERIC(18, 8) NOT NULL,
            amount_raw NUMERIC(18, 8),
            currency VARCHAR DEFAULT 'USD',
            carbon_kg NUMERIC(10, 4),
            recorded_at DATE NOT NULL,
            timestamp TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            PRIMARY KEY (id, recorded_at)
        ) PARTITION BY RANGE (recorded_at);
    """)

    # 3. Create Initial Partitions (Q1 2026)
    for table in ["audit_logs", "cost_records"]:
        op.execute(f"CREATE TABLE {table}_2026_01 PARTITION OF {table} FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')")
        op.execute(f"CREATE TABLE {table}_2026_02 PARTITION OF {table} FOR VALUES FROM ('2026-02-01') TO ('2026-03-01')")
        op.execute(f"CREATE TABLE {table}_2026_03 PARTITION OF {table} FOR VALUES FROM ('2026-03-01') TO ('2026-04-01')")
        
        # Add catch-all partition for out-of-range/future data to avoid insert errors
        op.execute(f"CREATE TABLE {table}_default PARTITION OF {table} DEFAULT")

    # 4. Migrate Data for Cost Records
    op.execute("""
        INSERT INTO cost_records (id, tenant_id, account_id, service, region, cost_usd, carbon_kg, recorded_at, created_at, updated_at)
        SELECT id, tenant_id, account_id, service, region, cost_usd, carbon_kg, recorded_at, created_at, updated_at 
        FROM cost_records_old
    """)

    # 5. Re-add Constraints and Indexes
    op.execute("CREATE INDEX ix_cost_records_tenant_id ON cost_records (tenant_id)")
    op.execute("CREATE INDEX ix_cost_records_service ON cost_records (service)")
    op.execute("ALTER TABLE cost_records ADD CONSTRAINT uix_account_cost_granularity UNIQUE (account_id, timestamp, service, region, usage_type, recorded_at)")

    # 6. Enable RLS
    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE cost_records ENABLE ROW LEVEL SECURITY")
    
    op.execute("""
        CREATE POLICY audit_logs_isolation_policy ON audit_logs
        USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid);
    """)
    op.execute("""
        CREATE POLICY cost_records_isolation_policy ON cost_records
        USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid);
    """)

    # 7. Cleanup
    op.execute("DROP TABLE cost_records_old")


def downgrade() -> None:
    """Revert partitioning (Standard flat tables)."""
    op.execute("DROP TABLE audit_logs")
    op.execute("DROP TABLE cost_records")
    
    # Re-create original cost_records (abbreviated for downgrade)
    # In a real scenario, we'd copy data back.
    op.execute("""
        CREATE TABLE cost_records (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL,
            account_id UUID NOT NULL,
            service VARCHAR NOT NULL,
            region VARCHAR,
            cost_usd NUMERIC(12, 4) NOT NULL,
            carbon_kg NUMERIC(10, 4),
            recorded_at DATE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

