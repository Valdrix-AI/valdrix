from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional, AsyncGenerator


class BaseAdapter(ABC):
    """
    Abstract Base Class for Multi-Cloud Cost Adapters.

    Standardizes the interface for:
    - Cost Ingestion (Daily/Hourly)
    - Resource Discovery
    - Connection Verification
    """
    last_error: Optional[str] = None

    @abstractmethod
    async def verify_connection(self) -> bool:
        """Verify that the stored credentials are valid."""
        raise NotImplementedError()

    @abstractmethod
    async def get_cost_and_usage(
        self, start_date: datetime, end_date: datetime, granularity: str = "DAILY"
    ) -> List[Dict[str, Any]]:
        """Fetch normalized cost data as a materialized list."""
        raise NotImplementedError()

    @abstractmethod
    def stream_cost_and_usage(
        self, start_date: datetime, end_date: datetime, granularity: str = "DAILY"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream cost data normalized to the standard Valdrix format.
        Used for memory-efficient ingestion.
        """
        raise NotImplementedError()

    @abstractmethod
    async def discover_resources(
        self, resource_type: str, region: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Discover active resources of a specific type (for Zombie detection)."""
        raise NotImplementedError()

    # Compatibility method for adapters that do not expose resource-level usage yet.
    async def get_resource_usage(
        self, _service_name: str, _resource_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return []


CostAdapter = BaseAdapter
