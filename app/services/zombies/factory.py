from typing import Any
from app.services.zombies.base import BaseZombieDetector
from app.services.zombies.aws.detector import AWSZombieDetector
from app.services.zombies.az_provider.detector import AzureZombieDetector
from app.services.zombies.gcp_provider.detector import GCPZombieDetector
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection

class ZombieDetectorFactory:
    """
    Factory to instantiate the correct ZombieDetector based on connection type.
    """
    @staticmethod
    def get_detector(connection: Any, region: str = "us-east-1") -> BaseZombieDetector:
        if isinstance(connection, AWSConnection):
            # Deconstruct AWS connection to get STS options if needed
            # For now, we assume role assumption happens inside detector or passing credentials
            # But the detector expects 'credentials' dict or assumes env vars.
            # We might need to fetch credentials here or pass the connection object.
            
            # TODO: Integrate with STS AssumeRole for cross-account
            # For now, simplistic instantiation
            return AWSZombieDetector(region=region)
            
        elif isinstance(connection, AzureConnection):
            return AzureZombieDetector(region="global")
            
        elif isinstance(connection, GCPConnection):
            return GCPZombieDetector(region="global")
            
        raise ValueError(f"Unsupported connection type: {type(connection)}")
