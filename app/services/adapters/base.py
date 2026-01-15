from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import List, Dict, Any
from app.schemas.costs import CloudUsageSummary

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
        pass
    
    @abstractmethod
    async def get_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY"
    ) -> List[Dict[str, Any]]:
        """
        Fetch cost data normalized to the standard Valdrix format.
        
        Returns list of dicts:
        {
            "timestamp": datetime,
            "service": str,
            "region": str,
            "usage_type": str,
            "cost_usd": Decimal,
            "currency": str,
            "amount_raw": Decimal,  # Original currency amount
            "tags": dict            # Optional raw tags
        }
        """
        pass
    
    @abstractmethod
    async def discover_resources(self, resource_type: str, region: str = None) -> List[Dict[str, Any]]:
        """Discover active resources of a specific type (for Zombie detection)."""
        pass

    # Deprecated methods compatible for now
    async def get_resource_usage(self, service_name: str, resource_id: str = None) -> List[Dict[str, Any]]:
        return []


CostAdapter = BaseAdapter
