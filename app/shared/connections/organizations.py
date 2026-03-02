import aioboto3
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.aws_connection import AWSConnection
from app.models.discovered_account import DiscoveredAccount
from app.shared.adapters.aws_utils import DEFAULT_BOTO_CONFIG, resolve_aws_region_hint

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
            logger.warning(
                "sync_skipped_not_management_account", connection_id=str(connection.id)
            )
            return 0

        # Step 1: Assume role for management account
        try:
            session = aioboto3.Session()
            sts_region = resolve_aws_region_hint(getattr(connection, "region", None))
            async with session.client(
                "sts",
                region_name=sts_region,
                config=DEFAULT_BOTO_CONFIG,
            ) as sts:
                role = await sts.assume_role(
                    RoleArn=connection.role_arn,
                    RoleSessionName="ValdricsDiscovery",
                    ExternalId=connection.external_id,
                )
                creds = role["Credentials"]

            # Step 2: Use assumed credentials for organizations
            async with session.client(
                "organizations",
                # Organizations remains a global control-plane API in commercial partitions.
                region_name="us-east-1",
                config=DEFAULT_BOTO_CONFIG,
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
            ) as org:
                paginator = org.get_paginator("list_accounts")
                count = 0

                # BE-ORG-OP: Fetch all existing accounts for this management connection upfront to avoid N+1 lookups
                result = await db.execute(
                    select(DiscoveredAccount).where(
                        DiscoveredAccount.management_connection_id == connection.id
                    )
                )
                existing_map = {acc.account_id: acc for acc in result.scalars().all()}

                async for page in paginator.paginate():
                    for acc in page.get("Accounts", []):
                        # Step 3: Skip if it's the management account itself
                        if acc["Id"] == connection.aws_account_id:
                            continue

                        discovered = existing_map.get(acc["Id"])

                        if discovered:
                            discovered.name = acc["Name"]
                            discovered.email = acc["Email"]
                            # Update existing
                        else:
                            discovered = DiscoveredAccount(
                                management_connection_id=connection.id,
                                account_id=acc["Id"],
                                name=acc["Name"],
                                email=acc["Email"],
                                status="discovered",
                            )
                            db.add(discovered)
                            # Add to map so we don't duplicate if AWS returns same ID twice in pagination
                            existing_map[acc["Id"]] = discovered

                        # BE-ORG-4: Increment only for discovered member accounts
                        count += 1

                await db.commit()
                logger.info("aws_org_sync_complete", discovered_count=count)
                return count

        except Exception as e:
            logger.error(
                "aws_org_sync_failed", error=str(e), connection_id=str(connection.id)
            )
            return 0
