from datetime import datetime, timezone
from collections.abc import AsyncGenerator
from typing import Any

from app.shared.adapters.base import BaseAdapter


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)


class LicenseAdapter(BaseAdapter):
    """
    Cloud+ adapter for license/ITAM spend feeds.
    Expects a generic connection object exposing `license_feed` or `cost_feed`.
    """

    def __init__(self, connection: Any):
        self.connection = connection

    async def verify_connection(self) -> bool:
        feed = getattr(self.connection, "license_feed", None) or getattr(self.connection, "cost_feed", None)
        return isinstance(feed, list)

    async def get_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY",
    ) -> list[dict[str, Any]]:
        records = []
        async for row in self.stream_cost_and_usage(start_date, end_date, granularity):
            records.append(row)
        return records

    async def stream_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY",
    ) -> AsyncGenerator[dict[str, Any], None]:
        feed = getattr(self.connection, "license_feed", None) or getattr(self.connection, "cost_feed", None) or []
        for entry in feed:
            timestamp = _parse_timestamp(entry.get("timestamp") or entry.get("date"))
            if timestamp < start_date or timestamp > end_date:
                continue
            yield {
                "provider": "license",
                "service": str(entry.get("service") or entry.get("vendor") or "License"),
                "region": "global",
                "usage_type": str(entry.get("usage_type") or "seat_license"),
                "cost_usd": float(entry.get("cost_usd") or entry.get("amount_usd") or 0.0),
                "amount_raw": entry.get("amount_raw"),
                "currency": str(entry.get("currency") or "USD"),
                "timestamp": timestamp,
                "source_adapter": "license_feed",
                "tags": entry.get("tags") if isinstance(entry.get("tags"), dict) else {},
            }

    async def discover_resources(self, resource_type: str, region: str | None = None) -> list[dict[str, Any]]:
        return []
