import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from app.shared.adapters.base import BaseAdapter
from app.shared.adapters.feed_utils import as_float, is_number, parse_timestamp
from app.shared.core.exceptions import ExternalAPIError

logger = structlog.get_logger()

_NATIVE_TIMEOUT_SECONDS = 20.0
_NATIVE_MAX_RETRIES = 3
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_MICROSOFT_LICENSE_VENDORS = {
    "microsoft_365",
    "microsoft365",
    "m365",
    "microsoft",
}


class LicenseAdapter(BaseAdapter):
    """
    Cloud+ adapter for license/ITAM spend.

    Supported modes:
    - Manual feed (`auth_method=manual|csv`) via `license_feed`
    - Native vendor pulls (`auth_method=api_key|oauth`) for Microsoft 365
    """

    def __init__(self, connection: Any):
        self.connection = connection
        self._last_error: str | None = None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def _vendor(self) -> str:
        return str(getattr(self.connection, "vendor", "")).strip().lower()

    @property
    def _auth_method(self) -> str:
        return str(getattr(self.connection, "auth_method", "manual")).strip().lower()

    @property
    def _connector_config(self) -> dict[str, Any]:
        raw = getattr(self.connection, "connector_config", {})
        return raw if isinstance(raw, dict) else {}

    @property
    def _native_vendor(self) -> str | None:
        if self._auth_method not in {"api_key", "oauth"}:
            return None
        if self._vendor in _MICROSOFT_LICENSE_VENDORS:
            return "microsoft_365"
        return None

    def _resolve_api_key(self) -> str:
        token = getattr(self.connection, "api_key", None)
        if not isinstance(token, str) or not token.strip():
            raise ExternalAPIError("Missing API token for license native connector")
        return token.strip()

    async def verify_connection(self) -> bool:
        self._last_error = None
        native_vendor = self._native_vendor
        if self._auth_method in {"api_key", "oauth"} and native_vendor is None:
            self._last_error = (
                f"Native license auth is not supported for vendor '{self._vendor}'. "
                "Supported vendor aliases: microsoft_365, microsoft365, m365, microsoft. "
                "Use auth_method manual/csv for custom vendors."
            )
            return False

        if native_vendor == "microsoft_365":
            try:
                await self._verify_microsoft_365()
                return True
            except ExternalAPIError as exc:
                self._last_error = str(exc)
                logger.warning(
                    "license_native_verify_failed", vendor=native_vendor, error=str(exc)
                )
                return False

        feed = getattr(self.connection, "license_feed", None) or getattr(
            self.connection, "cost_feed", None
        )
        is_valid = self._validate_manual_feed(feed)
        if not is_valid:
            if self._last_error is None:
                self._last_error = "License feed is missing or invalid."
        return is_valid

    def _validate_manual_feed(self, feed: Any) -> bool:
        if not isinstance(feed, list) or not feed:
            self._last_error = "License feed must contain at least one record for manual/csv verification."
            return False
        for idx, entry in enumerate(feed):
            if not isinstance(entry, dict):
                self._last_error = (
                    f"License feed entry #{idx + 1} must be a JSON object."
                )
                return False
            has_timestamp = entry.get("timestamp") or entry.get("date")
            if not has_timestamp:
                self._last_error = (
                    f"License feed entry #{idx + 1} is missing timestamp/date."
                )
                return False
            amount = entry.get("cost_usd", entry.get("amount_usd"))
            if not is_number(amount):
                self._last_error = f"License feed entry #{idx + 1} must include numeric cost_usd or amount_usd."
                return False
        return True

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
        native_vendor = self._native_vendor
        if native_vendor == "microsoft_365":
            try:
                async for row in self._stream_microsoft_365_license_costs(
                    start_date, end_date
                ):
                    yield row
                return
            except ExternalAPIError as exc:
                self._last_error = str(exc)
                logger.warning(
                    "license_native_stream_failed_fallback_to_feed",
                    vendor=native_vendor,
                    error=str(exc),
                )

        feed = (
            getattr(self.connection, "license_feed", None)
            or getattr(self.connection, "cost_feed", None)
            or []
        )
        if not isinstance(feed, list):
            return

        for entry in feed:
            timestamp = parse_timestamp(entry.get("timestamp") or entry.get("date"))
            if timestamp < start_date or timestamp > end_date:
                continue
            resource_id_raw = entry.get("resource_id") or entry.get("id")
            resource_id = (
                str(resource_id_raw).strip()
                if resource_id_raw not in (None, "")
                else None
            )
            usage_amount_raw = entry.get("usage_amount")
            usage_amount = (
                as_float(usage_amount_raw, default=0.0)
                if is_number(usage_amount_raw)
                else None
            )
            usage_unit_raw = entry.get("usage_unit")
            usage_unit = (
                str(usage_unit_raw).strip()
                if usage_unit_raw not in (None, "")
                else None
            )
            yield {
                "provider": "license",
                "service": str(
                    entry.get("service") or entry.get("vendor") or "License"
                ),
                "region": "global",
                "usage_type": str(entry.get("usage_type") or "seat_license"),
                "resource_id": resource_id,
                "usage_amount": usage_amount,
                "usage_unit": usage_unit,
                "cost_usd": float(
                    entry.get("cost_usd") or entry.get("amount_usd") or 0.0
                ),
                "amount_raw": entry.get("amount_raw"),
                "currency": str(entry.get("currency") or "USD"),
                "timestamp": timestamp,
                "source_adapter": "license_feed",
                "tags": entry.get("tags")
                if isinstance(entry.get("tags"), dict)
                else {},
            }

    async def _verify_microsoft_365(self) -> None:
        token = self._resolve_api_key()
        await self._get_json(
            "https://graph.microsoft.com/v1.0/subscribedSkus",
            headers={"Authorization": f"Bearer {token}"},
        )

    async def _stream_microsoft_365_license_costs(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> AsyncGenerator[dict[str, Any], None]:
        token = self._resolve_api_key()
        payload = await self._get_json(
            "https://graph.microsoft.com/v1.0/subscribedSkus",
            headers={"Authorization": f"Bearer {token}"},
        )
        entries = payload.get("value")
        if not isinstance(entries, list):
            raise ExternalAPIError("Invalid Microsoft Graph subscribedSkus payload")

        sku_prices_raw = self._connector_config.get("sku_prices")
        sku_prices: dict[str, float] = {}
        if isinstance(sku_prices_raw, dict):
            for key, value in sku_prices_raw.items():
                if isinstance(key, str):
                    sku_prices[key.strip().upper()] = as_float(value)
        default_price = as_float(
            self._connector_config.get("default_seat_price_usd"), default=0.0
        )
        default_currency = str(self._connector_config.get("currency") or "USD").upper()
        timestamp = (
            end_date if end_date.tzinfo else end_date.replace(tzinfo=timezone.utc)
        )

        for sku in entries:
            if not isinstance(sku, dict):
                continue
            sku_code = str(
                sku.get("skuPartNumber") or sku.get("skuId") or "M365_SKU"
            ).upper()
            consumed_units = as_float(sku.get("consumedUnits"), default=0.0)
            prepaid = sku.get("prepaidUnits")
            if consumed_units <= 0 and isinstance(prepaid, dict):
                consumed_units = as_float(prepaid.get("enabled"), default=0.0)

            unit_price = sku_prices.get(sku_code, default_price)
            total_cost = round(consumed_units * unit_price, 2)

            if timestamp < start_date or timestamp > end_date:
                continue

            yield {
                "provider": "license",
                "service": sku_code,
                "region": "global",
                "usage_type": "seat_license",
                "resource_id": str(sku.get("skuId") or sku_code).strip() or None,
                "usage_amount": consumed_units,
                "usage_unit": "seat",
                "cost_usd": total_cost,
                "amount_raw": consumed_units,
                "currency": default_currency,
                "timestamp": timestamp,
                "source_adapter": "license_microsoft_graph",
                "tags": {
                    "vendor": "microsoft_365",
                    "sku_id": str(sku.get("skuId") or ""),
                    "unit_price_usd": unit_price,
                    "consumed_units": consumed_units,
                },
            }

    async def _get_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, _NATIVE_MAX_RETRIES + 1):
            try:
                from app.shared.core.http import get_http_client

                client = get_http_client()
                response = await client.post(url, headers=headers, params=params)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ExternalAPIError(
                        "License connector API returned invalid payload shape"
                    )
                return payload
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code
                retryable = status_code in _RETRYABLE_STATUS_CODES
                if retryable and attempt < _NATIVE_MAX_RETRIES:
                    logger.warning(
                        "license_native_retry_http_status",
                        attempt=attempt,
                        max_attempts=_NATIVE_MAX_RETRIES,
                        status_code=status_code,
                        url=url,
                    )
                    await asyncio.sleep(0.05 * attempt)
                    continue
                raise ExternalAPIError(
                    f"License connector API request failed with status {status_code}: {exc}"
                ) from exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt < _NATIVE_MAX_RETRIES:
                    logger.warning(
                        "license_native_retry_transport_error",
                        attempt=attempt,
                        max_attempts=_NATIVE_MAX_RETRIES,
                        url=url,
                        error=str(exc),
                    )
                    await asyncio.sleep(0.05 * attempt)
                    continue
                raise ExternalAPIError(
                    f"License connector API request failed: {exc}"
                ) from exc
            except ValueError as exc:
                raise ExternalAPIError(
                    "License connector API returned invalid JSON payload"
                ) from exc

        if last_error is not None:
            raise ExternalAPIError(
                f"License connector API request failed: {last_error}"
            ) from last_error
        raise ExternalAPIError("License connector API request failed unexpectedly")

    async def discover_resources(
        self, resource_type: str, region: str | None = None
    ) -> list[dict[str, Any]]:
        return []
