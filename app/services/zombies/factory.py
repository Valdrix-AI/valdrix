from typing import Any
from app.services.zombies.base import BaseZombieDetector
from app.services.zombies.aws_provider.detector import AWSZombieDetector
from app.services.zombies.azure_provider.detector import AzureZombieDetector
from app.services.zombies.gcp_provider.detector import GCPZombieDetector
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection

class ZombieDetectorFactory:
    """
    Factory to instantiate the correct ZombieDetector based on connection type.
    """
    from sqlalchemy.ext.asyncio import AsyncSession
    @staticmethod
    def get_detector(connection: Any, region: str = "us-east-1", db: AsyncSession = None) -> BaseZombieDetector:
        type_name = type(connection).__name__
        
        if "AWSConnection" in type_name:
            return AWSZombieDetector(region=region, connection=connection, db=db)
            
        elif "AzureConnection" in type_name:
            return AzureZombieDetector(region="global", connection=connection, db=db)
            
        elif "GCPConnection" in type_name:
            return GCPZombieDetector(region="global", connection=connection, db=db)
            
        raise ValueError(f"Unsupported connection type: {type_name}")
