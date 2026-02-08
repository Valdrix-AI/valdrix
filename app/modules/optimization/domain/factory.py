from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.optimization.domain.ports import BaseZombieDetector
from app.modules.optimization.adapters.aws.detector import AWSZombieDetector
from app.modules.optimization.adapters.azure.detector import AzureZombieDetector
from app.modules.optimization.adapters.gcp.detector import GCPZombieDetector

class ZombieDetectorFactory:
    """
    Factory to instantiate the correct ZombieDetector based on connection type.
    """
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
