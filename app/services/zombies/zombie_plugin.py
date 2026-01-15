from abc import ABC, abstractmethod
from typing import List, Dict, Any
import aioboto3

from app.services.pricing.service import PricingService

class ZombiePlugin(ABC):
    """
    Abstract base class for Zombie Resource detection plugins.
    Each plugin is responsible for detecting a specific type of zombie resource.
    """

    @property
    @abstractmethod
    def category_key(self) -> str:
        """
        The dictionary key for results (e.g., 'unattached_volumes').
        Used to aggregate results in the final report.
        """
        pass

    @abstractmethod
    async def scan(self, session: aioboto3.Session, region: str, credentials: Dict[str, str] = None) -> List[Dict[str, Any]]:
        """
        Scan for zombie resources.

        Args:
            session: The aioboto3 session to use for client creation.
            region: AWS region to scan.
            credentials: STS credentials dictionary (optional).

        Returns:
            List of dictionaries representing detected zombie resources.
        """
        pass

    async def _get_client(self, session: aioboto3.Session, service_name: str, region: str, credentials: Dict[str, str] = None):
        """Helper to get aioboto3 client with optional credentials."""
        kwargs = {"region_name": region}
        if credentials:
            kwargs.update({
                "aws_access_key_id": credentials["AccessKeyId"],
                "aws_secret_access_key": credentials["SecretAccessKey"],
                "aws_session_token": credentials["SessionToken"],
            })
        return session.client(service_name, **kwargs)
