from abc import ABC, abstractmethod
from typing import Dict, Any, List
from datetime import date

class CostAdapter(ABC):
  @abstractmethod
  @abstractmethod
  async def get_daily_costs(self, start_date: date, end_date: date, group_by_service: bool = False) -> Any:
    """
    Returns daily costs.
    If group_by_service is True, returns structured CostResponse with breakdown.
    Otherwise returns simple list of daily totals.
    """
    pass

  @abstractmethod
  async def get_resource_usage(self, service_name: str) -> List[Dict[str, Any]]:
    """
    Returns granular resource usage metrcs for AI analysis (CPU %, DISK I/O, Network I/O, etc)
    """
    pass


