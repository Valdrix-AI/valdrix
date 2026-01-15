import aioboto3
import structlog
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.aws_connection import AWSConnection
from app.models.discovered_account import DiscoveredAccount

logger = structlog.get_logger()

class OrganizationsDiscoveryService:
    @staticmethod
    async def sync_accounts(db: AsyncSession, connection: AWSConnection):
        """
        Poll AWS Organizations API to discover member accounts.
        """
        if not connection.is_management_account:
            logger.warning("skip_org_discovery_non_management", connection_id=str(connection.id))
            return

        logger.info("syncing_aws_organizations", connection_id=str(connection.id), account_id=connection.aws_account_id)
        
        try:
            session = aioboto3.Session()
            
            # 1. Assume Role of the management account to get cross-account access
            async with session.client("sts") as sts_client:
                assumed_role = await sts_client.assume_role(
                    RoleArn=connection.role_arn,
                    RoleSessionName="ValdrixOrgDiscovery",
                    ExternalId=connection.external_id,
                    DurationSeconds=900
                )
                creds = assumed_role['Credentials']
                
            # 2. Use credentials to call Organizations API
            async with session.client(
                "organizations",
                aws_access_key_id=creds['AccessKeyId'],
                aws_secret_access_key=creds['SecretAccessKey'],
                aws_session_token=creds['SessionToken'],
                region_name="us-east-1" # Organizations is global but requires a region for signing
            ) as org_client:
                
                accounts = []
                paginator = org_client.get_paginator('list_accounts')
                async for page in paginator.paginate():
                    accounts.extend(page['Accounts'])
                    
                logger.info("org_discovery_results", count=len(accounts))
                
                # 3. Update DB
                for acc in accounts:
                    acc_id = acc['Id']
                    # Skip if it's the management itself (already connected)
                    if acc_id == connection.aws_account_id:
                        continue
                    
                    # Search for existing record
                    res = await db.execute(
                        select(DiscoveredAccount).where(
                            DiscoveredAccount.management_connection_id == connection.id,
                            DiscoveredAccount.account_id == acc_id
                        )
                    )
                    discovered = res.scalar_one_or_none()
                    
                    if not discovered:
                        discovered = DiscoveredAccount(
                            management_connection_id=connection.id,
                            account_id=acc_id,
                            name=acc.get('Name'),
                            email=acc.get('Email'),
                            status="discovered",
                            last_discovered_at=datetime.now(timezone.utc)
                        )
                        db.add(discovered)
                    else:
                        discovered.name = acc.get('Name')
                        discovered.email = acc.get('Email')
                        discovered.last_discovered_at = datetime.now(timezone.utc)
                
                await db.commit()
                return len(accounts)
                    
        except Exception as e:
            logger.error("org_discovery_failed", connection_id=str(connection.id), error=str(e))
            raise
