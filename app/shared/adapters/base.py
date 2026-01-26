from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional

class BaseAdapter(ABC):
    """
    Abstract Base Class for Multi-Cloud Cost Adapters.
    
    Standardizes the interface for:
    - Cost Ingestion (Daily/Hourly)
    - Resource Discovery
    - Connection Verification
    """
    
    @abstractmethod
    async def verify_connection(self) -> bool:
        """Verify that the stored credentials are valid."""
        raise NotImplementedError()
    
    @abstractmethod
    async def get_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY"
    ) -> List[Dict[str, Any]]:
        """Fetch cost data as a list (legacy)."""
        raise NotImplementedError()

    @abstractmethod
    async def stream_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY"
    ) -> Any:
        # Use Any for now as a workaround for AsyncGenerator type hint in abstractmethod
        # Real implementations will return AsyncGenerator[Dict[str, Any], None]
        """
        Stream cost data normalized to the standard Valdrix format.
        Used for memory-efficient ingestion.
        """
        raise NotImplementedError()
    
    @abstractmethod
    async def discover_resources(self, resource_type: str, region: Optional[str] = None) -> List[Dict[str, Any]]:
        """Discover active resources of a specific type (for Zombie detection)."""
        raise NotImplementedError()

    # Deprecated methods compatible for now
    async def get_resource_usage(self, service_name: str, resource_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return []


CostAdapter = BaseAdapter
