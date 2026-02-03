"""
Resource Inventory Schemas

Provides a unified data model for discovered cloud resources across all providers.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class DiscoveredResource(BaseModel):
    """Normalized representation of a discovered cloud resource."""
    id: str
    arn: Optional[str] = None
    service: str
    resource_type: str
    region: str
    provider: str
    tags: Dict[str, str] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class CloudInventory(BaseModel):
    """Account-level inventory of discovered resources."""
    tenant_id: str
    provider: str
    resources: List[DiscoveredResource] = Field(default_factory=list)
    total_count: int = 0
    discovery_method: str # e.g., "resource-explorer-2", "native-api", "tagging-api"
    discovered_at: str
