from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.optimization.domain.ports import BaseZombieDetector
from app.modules.optimization.adapters.aws.detector import AWSZombieDetector
from app.modules.optimization.adapters.azure.detector import AzureZombieDetector
from app.modules.optimization.adapters.gcp.detector import GCPZombieDetector
from app.modules.optimization.adapters.saas.detector import SaaSZombieDetector
from app.modules.optimization.adapters.license.detector import LicenseZombieDetector

class ZombieDetectorFactory:
    """
    Factory to instantiate the correct ZombieDetector based on connection type.
    """
    @staticmethod
    def get_detector(connection: Any, region: str = "us-east-1", db: Optional[AsyncSession] = None) -> BaseZombieDetector:
        type_name = type(connection).__name__
        provider = str(getattr(connection, "provider", "")).lower()
        
        if "AWSConnection" in type_name:
            return AWSZombieDetector(region=region, connection=connection, db=db)
            
        elif "AzureConnection" in type_name:
            return AzureZombieDetector(region="global", connection=connection, db=db)
            
        elif "GCPConnection" in type_name:
            return GCPZombieDetector(region="global", connection=connection, db=db)

        elif "SaaSConnection" in type_name or provider in {"saas", "cloud_plus_saas"}:
            return SaaSZombieDetector(region="global", connection=connection, db=db)

        elif "LicenseConnection" in type_name or provider in {"license", "itam", "cloud_plus_license"}:
            return LicenseZombieDetector(region="global", connection=connection, db=db)
            
        raise ValueError(f"Unsupported connection type: {type_name} (provider={provider})")
