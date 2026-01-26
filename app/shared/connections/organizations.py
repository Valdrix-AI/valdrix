import aioboto3
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.aws_connection import AWSConnection
from app.models.discovered_account import DiscoveredAccount

logger = structlog.get_logger()

class OrganizationsDiscoveryService:
    """
    Service to discover member accounts in an AWS Organization.
    """
    @staticmethod
    async def sync_accounts(db: AsyncSession, connection: AWSConnection) -> int:
        """
        Fetches all member accounts associated with a management account role.
        Saves them to the DiscoveredAccount table for onboarding.
        """
        if not connection.is_management_account:
            logger.warning("sync_skipped_not_management_account", connection_id=str(connection.id))
            return 0
            
        session = aioboto3.Session()
        
        # Step 1: Assume role for management account
        try:
            async with session.client("sts", region_name="us-east-1") as sts:
                role = await sts.assume_role(
                    RoleArn=connection.role_arn,
                    RoleSessionName="ValdrixDiscovery",
                    ExternalId=connection.external_id
                )
                creds = role["Credentials"]
                
            # Step 2: Use assumed credentials for organizations
            async with session.client(
                "organizations", 
                region_name="us-east-1",
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"]
            ) as org:
                paginator = org.get_paginator("list_accounts")
                count = 0
                
                async for page in paginator.paginate():
                    for acc in page.get("Accounts", []):
                        count += 1
                        # Skip if it's the management account itself
                        if acc["Id"] == connection.aws_account_id:
                            continue
                            
                        # Check existance
                        result = await db.execute(
                            select(DiscoveredAccount).where(
                                DiscoveredAccount.account_id == acc["Id"]
                            )
                        )
                        discovered = result.scalar_one_or_none()
                        
                        if discovered:
                            discovered.name = acc["Name"]
                            discovered.email = acc["Email"]
                            # discovered.last_discovered_at is updated via default/auto
                        else:
                            discovered = DiscoveredAccount(
                                management_connection_id=connection.id,
                                account_id=acc["Id"],
                                name=acc["Name"],
                                email=acc["Email"],
                                status="discovered"
                            )
                            db.add(discovered)
                
                await db.commit()
                logger.info("aws_org_sync_complete", discovered_count=count)
                return count
                
        except Exception as e:
            logger.error("aws_org_sync_failed", error=str(e), connection_id=str(connection.id))
            return 0
