import asyncio
import argparse
import boto3
import structlog
from uuid import UUID
from typing import Optional
from sqlalchemy import select
from app.shared.db.session import async_session_maker
from app.models.aws_connection import AWSConnection

logger = structlog.get_logger()

async def get_connection_by_id(session, connection_id: UUID) -> Optional[AWSConnection]:
    result = await session.execute(select(AWSConnection).where(AWSConnection.id == connection_id))
    return result.scalar_one_or_none()

async def disconnect_aws(connection_id: UUID, dry_run: bool = True):
    """
    Scripted emergency disconnect.
    Optionally deletes the IAM role or just marks as inactive in DB.
    """
    logger.info("emergency_disconnect_starting", connection_id=str(connection_id), dry_run=dry_run)
    
    async with async_session_maker() as session:
        conn = await get_connection_by_id(session, connection_id)
        if not conn:
            logger.error("connection_not_found", connection_id=str(connection_id))
            return

        role_arn = conn.role_arn
        logger.info("found_connection", role_arn=role_arn)

        if not dry_run:
            try:
                # 1. Update DB immediately to stop scans
                conn.status = "inactive"
                await session.commit()
                logger.info("connection_deactivated_in_db")

                # 2. Optional: Invalidate IAM Role via AWS SDK
                # This requires administrative credentials set in environment
                # Extract role name from ARN: arn:aws:iam::123456789012:role/ValdrixRole
                role_name = role_arn.split('/')[-1]
                
                iam = boto3.client('iam')
                # Instead of deleting (destructive), we just remove the Trust Relationship (AssumeRolePolicy)
                # or attach a 'Deny All' policy for faster cutoff.
                
                logger.info("applying_deny_all_to_role", role_name=role_name)
                deny_policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Deny",
                            "Action": "*",
                            "Resource": "*"
                        }
                    ]
                }
                # Inline policy to block everything immediately
                iam.put_role_policy(
                    RoleName=role_name,
                    PolicyName="EmergencyDisconnectDenyAll",
                    PolicyDocument=asyncio.get_event_loop().run_in_executor(None, lambda: str(deny_policy)) # Simplified for script
                )
                logger.info("deny_all_policy_attached")

            except Exception as e:
                logger.error("disconnect_aws_failed", error=str(e))
                await session.rollback()
        else:
            logger.info("dry_run_no_changes_made")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Emergency AWS Disconnect")
    parser.add_argument("connection_id", type=str, help="UUID of the AWS connection")
    parser.add_argument("--execute", action="store_true", help="Actually perform the disconnect")
    args = parser.parse_args()

    asyncio.run(disconnect_aws(UUID(args.connection_id), dry_run=not args.execute))
