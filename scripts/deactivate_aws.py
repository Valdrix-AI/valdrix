import asyncio
import structlog
from sqlalchemy import update
from app.shared.db.session import async_session_maker
from app.models.aws_connection import AWSConnection

logger = structlog.get_logger()


async def deactivate_all_connections():
    """Sets all AWS connections to 'inactive' to stop all scheduled scans."""
    async with async_session_maker() as session:
        try:
            stmt = update(AWSConnection).values(status="inactive")
            result = await session.execute(stmt)
            await session.commit()
            logger.info(
                "emergency_deactivation_complete", connections_affected=result.rowcount
            )
            print(f"Successfully deactivated {result.rowcount} AWS connections.")
        except Exception as e:
            logger.error("emergency_deactivation_failed", error=str(e))
            print(f"Error: {str(e)}")


if __name__ == "__main__":
    asyncio.run(deactivate_all_connections())
