import asyncio
from sqlalchemy import select
from app.shared.db.session import async_session_maker
from app.models.aws_connection import AWSConnection
from app.models.cloud import CloudAccount, CostRecord
import app.models.llm
import app.models.notification_settings
import app.models.remediation
import app.models.background_job
import app.models.azure_connection
import app.models.gcp_connection

async def check_schema_integrity():
    async with async_session_maker() as session:
        print("--- AWS Connections ---")
        aws_conns = (await session.execute(select(AWSConnection))).scalars().all()
        for c in aws_conns:
            print(f"AWS ID: {c.id}")

        print("\n--- Cloud Accounts ---")
        cloud_accts = (await session.execute(select(CloudAccount))).scalars().all()
        for c in cloud_accts:
            print(f"CloudAccount ID: {c.id}, Provider: {c.provider}")

        print("\n--- Cost Records ---")
        costs = (await session.execute(select(CostRecord).limit(5))).scalars().all()
        for c in costs:
            print(f"CostRecord AccountID: {c.account_id}, Service: {c.service}")

        print("\n--- Azure Connections ---")
        azure_conns = (await session.execute(select(app.models.azure_connection.AzureConnection))).scalars().all()
        for c in azure_conns:
            print(f"Azure ID: {c.id}, Name: {c.name}")

        print("\n--- GCP Connections ---")
        gcp_conns = (await session.execute(select(app.models.gcp_connection.GCPConnection))).scalars().all()
        for c in gcp_conns:
            print(f"GCP ID: {c.id}, Name: {c.name}, Billing Table: {c.billing_table}")

        # Check for overlap
        aws_ids = {c.id for c in aws_conns}
        cloud_ids = {c.id for c in cloud_accts}
        print(f"\nOverlap (AWS IDs in CloudAccount): {aws_ids.intersection(cloud_ids)}")

if __name__ == "__main__":
    asyncio.run(check_schema_integrity())
