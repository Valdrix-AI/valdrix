"""
Cloud Cost and Usage Schemas - Normalization Layer
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class CostRecord(BaseModel):
    """Normalized cost entry for a specific date/time and dimension."""
    date: datetime = Field(..., description="Timestamp of the usage")
    amount: Decimal = Field(..., description="Cost amount in USD")
    amount_raw: Optional[Decimal] = Field(None, description="Original cost amount in local currency")
    currency: str = "USD"
    service: Optional[str] = None
    region: Optional[str] = None
    usage_type: Optional[str] = None
    tags: Dict[str, str] = Field(default_factory=dict)

class CloudUsageSummary(BaseModel):
    """High-level summary of cloud usage over a period."""
    tenant_id: str
    provider: str  # aws, azure, gcp
    start_date: date
    end_date: date
    total_cost: Decimal
    records: List[CostRecord]
    
    # Aggregated views
    by_service: Dict[str, Decimal] = Field(default_factory=dict)
    by_region: Dict[str, Decimal] = Field(default_factory=dict)
    by_tag: Dict[str, Dict[str, Decimal]] = Field(default_factory=dict) # e.g., {"Project": {"Prod": 10.5, "Dev": 5.2}}

class ResourceCandidate(BaseModel):
    """Normalized resource identified for optimization/remediation."""
    resource_id: str
    resource_type: str
    region: str
    provider: str
    estimated_monthly_savings: Decimal
    tags: Dict[str, str] = Field(default_factory=dict)
    reason: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
