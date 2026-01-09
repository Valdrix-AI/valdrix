from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from datetime import date

class DailyCost(BaseModel):
    date: date
    cost: float
    service: Optional[str] = None

class CostResponse(BaseModel):
    total_cost: float
    currency: str = "USD"
    start_date: date
    end_date: date
    daily_costs: List[DailyCost]
    # Detailed breakdown for charts (date -> service -> cost)
    breakdown: List[Dict[str, Any]] = [] 
