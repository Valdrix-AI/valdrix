from abc import ABC, abstractmethod
from typing import Dict, Any, List
from datetime import date

class CostAdapter(ABC):
  @abstractmethod
  async def get_daily_costs(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
    """
    Returns a uniform list of daily costs.
    Format: [{"date": "2026-01-01", "service": "EC2", "cost": 50.0}, ...]
    """
    pass

  @abstractmethod
  async def get_resource_usage(self, service_name: str) -> List[Dict[str, Any]]:
    """
    Returns granular resource usage metrcs for AI analysis (CPU %, DISK I/O, Network I/O, etc)
    """
    pass


