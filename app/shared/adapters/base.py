from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional, AsyncGenerator

from app.shared.core.exceptions import AdapterError


class BaseAdapter(ABC):
    """
    Abstract Base Class for Multi-Cloud Cost Adapters.

    Standardizes the interface for:
    - Cost Ingestion (Daily/Hourly)
    - Resource Discovery
    - Connection Verification
    """
    last_error: Optional[str] = None

    def _clear_last_error(self) -> None:
        """Reset adapter error state before a new operation."""
        self.last_error = None

    def _set_last_error(self, message: str) -> None:
        """Store a sanitized adapter error message suitable for operator-facing responses."""
        self.last_error = AdapterError(message).message

    def _set_last_error_from_exception(
        self, exc: Exception, *, prefix: str | None = None
    ) -> None:
        """
        Store a sanitized message from an exception.

        Prefixes allow adapters to preserve operation context (for example, provider/auth path)
        while still passing through AdapterError sanitization.
        """
        error_text = str(exc)
        message = f"{prefix}: {error_text}" if prefix else error_text
        self._set_last_error(message)

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

    @abstractmethod
    async def get_resource_usage(
        self, _service_name: str, _resource_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Return normalized resource-level usage rows for the requested service/resource.
        Implementations may return an empty list when the provider does not expose this data.
        """
        raise NotImplementedError()


CostAdapter = BaseAdapter
