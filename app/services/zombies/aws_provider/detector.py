from typing import List, Dict, Any
import aioboto3
import structlog
from app.services.zombies.base import BaseZombieDetector
from app.services.zombies.zombie_plugin import ZombiePlugin

from app.services.zombies.registry import registry
# Import plugins to trigger registration (Audit Fix: Decoupling)
import app.services.zombies.aws_provider.plugins  # noqa

logger = structlog.get_logger()

class AWSZombieDetector(BaseZombieDetector):
    """
    Concrete implementation of ZombieDetector for AWS.
    Manages aioboto3 session and AWS-specific plugin execution.
    """

    from sqlalchemy.ext.asyncio import AsyncSession
    def __init__(self, region: str = "us-east-1", credentials: Dict[str, str] = None, db: AsyncSession = None, connection: Any = None):
        super().__init__(region, credentials, db, connection)
        self.session = aioboto3.Session()
        self._adapter = None
        if connection:
            from app.services.adapters.aws_multitenant import MultiTenantAWSAdapter
            self._adapter = MultiTenantAWSAdapter(connection)

    @property
    def provider_name(self) -> str:
        return "aws"

    def _initialize_plugins(self):
        """Register the standard suite of AWS detections."""
        self.plugins = registry.get_plugins_for_provider("aws")

    async def _execute_plugin_scan(self, plugin: ZombiePlugin) -> List[Dict[str, Any]]:
        """
        Execute AWS plugin scan, passing the aioboto3 session and standard config.
        """
        from botocore.config import Config
        from app.core.config import get_settings
        
        settings = get_settings()
        boto_config = Config(
            connect_timeout=settings.ZOMBIE_PLUGIN_TIMEOUT_SECONDS,
            read_timeout=settings.ZOMBIE_PLUGIN_TIMEOUT_SECONDS,
            retries={"max_attempts": 2}
        )

        creds = self.credentials
        if self._adapter:
            creds = await self._adapter.get_credentials()
            
        return await plugin.scan(self.session, self.region, creds, config=boto_config)
