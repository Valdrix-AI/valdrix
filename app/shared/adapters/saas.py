import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urljoin

import httpx
import structlog

from app.shared.adapters.base import BaseAdapter
from app.shared.core.exceptions import ExternalAPIError

logger = structlog.get_logger()

_NATIVE_TIMEOUT_SECONDS = 20.0
_NATIVE_MAX_RETRIES = 3
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_NATIVE_VENDOR_STRIPE = "stripe"
_NATIVE_VENDOR_SALESFORCE = "salesforce"
_NATIVE_SUPPORTED_VENDORS = {
    _NATIVE_VENDOR_STRIPE,
    _NATIVE_VENDOR_SALESFORCE,
}


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (TypeError, ValueError):
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)


def _as_float(value: Any, default: float = 0.0, *, divisor: int = 1) -> float:
    if value is None:
        return default
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default
    if divisor <= 0:
        divisor = 1
    return float(amount / Decimal(divisor))


def _is_number(value: Any) -> bool:
    try:
        Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return True


class SaaSAdapter(BaseAdapter):
    """
    Cloud+ adapter for SaaS spend.

    Supported modes:
    - Manual feed (`auth_method=manual|csv`) via `spend_feed`
    - Native vendor pulls (`auth_method=api_key|oauth`) for Stripe and Salesforce
    """

    def __init__(self, connection: Any):
        self.connection = connection
        self._last_error: str | None = None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def _auth_method(self) -> str:
        return str(getattr(self.connection, "auth_method", "manual")).strip().lower()

    @property
    def _vendor(self) -> str:
        return str(getattr(self.connection, "vendor", "")).strip().lower()

    @property
    def _connector_config(self) -> dict[str, Any]:
        raw = getattr(self.connection, "connector_config", {})
        return raw if isinstance(raw, dict) else {}

    @property
    def _native_vendor(self) -> str | None:
        if self._auth_method not in {"api_key", "oauth"}:
            return None
        if self._vendor in _NATIVE_SUPPORTED_VENDORS:
            return self._vendor
        return None

    def _resolve_api_key(self) -> str:
        token = getattr(self.connection, "api_key", None)
        if not isinstance(token, str) or not token.strip():
            raise ExternalAPIError("Missing API token for SaaS native connector")
        return token.strip()

    async def verify_connection(self) -> bool:
        self._last_error = None
        native_vendor = self._native_vendor
        if self._auth_method in {"api_key", "oauth"} and native_vendor is None:
            supported_vendors = ", ".join(sorted(_NATIVE_SUPPORTED_VENDORS))
            self._last_error = (
                f"Native SaaS auth is not supported for vendor '{self._vendor}'. "
                f"Supported vendors: {supported_vendors}. "
                "Use auth_method manual/csv for custom vendors."
            )
            return False

        if native_vendor:
            try:
                if native_vendor == _NATIVE_VENDOR_STRIPE:
                    await self._verify_stripe()
                    return True
                if native_vendor == _NATIVE_VENDOR_SALESFORCE:
                    await self._verify_salesforce()
                    return True
            except ExternalAPIError as exc:
                self._last_error = str(exc)
                logger.warning(
                    "saas_native_verify_failed",
                    vendor=native_vendor,
                    error=str(exc),
                )
                return False

        feed = getattr(self.connection, "spend_feed", None) or getattr(self.connection, "cost_feed", None)
        is_valid = self._validate_manual_feed(feed)
        if not is_valid:
            if self._last_error is None:
                self._last_error = "Spend feed is missing or invalid."
        return is_valid

    def _validate_manual_feed(self, feed: Any) -> bool:
        if not isinstance(feed, list) or not feed:
            self._last_error = "Spend feed must contain at least one record for manual/csv verification."
            return False
        for idx, entry in enumerate(feed):
            if not isinstance(entry, dict):
                self._last_error = f"Spend feed entry #{idx + 1} must be a JSON object."
                return False
            has_timestamp = entry.get("timestamp") or entry.get("date")
            if not has_timestamp:
                self._last_error = (
                    f"Spend feed entry #{idx + 1} is missing timestamp/date."
                )
                return False
            amount = entry.get("cost_usd", entry.get("amount_usd"))
            if not _is_number(amount):
                self._last_error = (
                    f"Spend feed entry #{idx + 1} must include numeric cost_usd or amount_usd."
                )
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
        if native_vendor:
            try:
                if native_vendor == _NATIVE_VENDOR_STRIPE:
                    async for row in self._stream_stripe_cost_and_usage(start_date, end_date):
                        yield row
                    return
                if native_vendor == _NATIVE_VENDOR_SALESFORCE:
                    async for row in self._stream_salesforce_cost_and_usage(start_date, end_date):
                        yield row
                    return
            except ExternalAPIError as exc:
                self._last_error = str(exc)
                logger.warning(
                    "saas_native_stream_failed_fallback_to_feed",
                    vendor=native_vendor,
                    error=str(exc),
                )

        feed = getattr(self.connection, "spend_feed", None) or getattr(self.connection, "cost_feed", None) or []
        if not isinstance(feed, list):
            return

        for entry in feed:
            timestamp = _parse_timestamp(entry.get("timestamp") or entry.get("date"))
            if timestamp < start_date or timestamp > end_date:
                continue
            yield {
                "provider": "saas",
                "service": str(entry.get("service") or entry.get("vendor") or "SaaS"),
                "region": "global",
                "usage_type": str(entry.get("usage_type") or "subscription"),
                "cost_usd": float(entry.get("cost_usd") or entry.get("amount_usd") or 0.0),
                "amount_raw": entry.get("amount_raw"),
                "currency": str(entry.get("currency") or "USD"),
                "timestamp": timestamp,
                "source_adapter": "saas_feed",
                "tags": entry.get("tags") if isinstance(entry.get("tags"), dict) else {},
            }

    async def _verify_stripe(self) -> None:
        api_key = self._resolve_api_key()
        await self._get_json(
            "https://api.stripe.com/v1/balance",
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def _verify_salesforce(self) -> None:
        token = self._resolve_api_key()
        base_url = self._connector_config.get("instance_url")
        if not isinstance(base_url, str) or not base_url.strip():
            raise ExternalAPIError(
                "Missing Salesforce connector_config.instance_url for native mode"
            )
        await self._get_json(
            urljoin(base_url.rstrip("/") + "/", "services/data/v60.0/limits"),
            headers={"Authorization": f"Bearer {token}"},
        )

    async def _stream_stripe_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> AsyncGenerator[dict[str, Any], None]:
        api_key = self._resolve_api_key()
        headers = {"Authorization": f"Bearer {api_key}"}
        endpoint = "https://api.stripe.com/v1/invoices"
        starting_after: str | None = None

        while True:
            params: dict[str, Any] = {
                "limit": 100,
                "created[gte]": int(start_date.timestamp()),
                "created[lte]": int(end_date.timestamp()),
            }
            if starting_after:
                params["starting_after"] = starting_after

            payload = await self._get_json(endpoint, headers=headers, params=params)
            entries = payload.get("data")
            if not isinstance(entries, list):
                raise ExternalAPIError("Invalid Stripe invoices payload: expected list in data")

            for invoice in entries:
                if not isinstance(invoice, dict):
                    continue
                timestamp = _parse_timestamp(invoice.get("created"))
                if timestamp < start_date or timestamp > end_date:
                    continue

                amount_cents = invoice.get("amount_paid")
                if amount_cents is None:
                    amount_cents = invoice.get("total")

                service_name = (
                    str(invoice.get("description")).strip()
                    if isinstance(invoice.get("description"), str) and invoice.get("description")
                    else "Stripe Billing"
                )

                yield {
                    "provider": "saas",
                    "service": service_name,
                    "region": "global",
                    "usage_type": "subscription_invoice",
                    "cost_usd": _as_float(amount_cents, divisor=100),
                    "amount_raw": amount_cents,
                    "currency": str(invoice.get("currency") or "USD").upper(),
                    "timestamp": timestamp,
                    "source_adapter": "saas_stripe_api",
                    "tags": {
                        "vendor": "stripe",
                        "invoice_id": str(invoice.get("id") or ""),
                        "customer_id": str(invoice.get("customer") or ""),
                    },
                }

            has_more = bool(payload.get("has_more"))
            if not has_more or not entries:
                break

            next_token = entries[-1].get("id")
            if not isinstance(next_token, str) or not next_token:
                break
            starting_after = next_token

    async def _stream_salesforce_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> AsyncGenerator[dict[str, Any], None]:
        token = self._resolve_api_key()
        base_url = self._connector_config.get("instance_url")
        if not isinstance(base_url, str) or not base_url.strip():
            raise ExternalAPIError("Salesforce requires connector_config.instance_url")

        endpoint = urljoin(base_url.rstrip("/") + "/", "services/data/v60.0/query")
        start_iso = start_date.date().isoformat()
        end_iso = end_date.date().isoformat()
        soql = (
            "SELECT Id, Description, ServiceDate, TotalPrice, CurrencyIsoCode "  # nosec B608
            "FROM ContractLineItem "
            f"WHERE ServiceDate >= {start_iso} "
            f"AND ServiceDate <= {end_iso} "
            "ORDER BY ServiceDate DESC"
        )
        headers = {"Authorization": f"Bearer {token}"}

        params: dict[str, Any] | None = {"q": soql}
        next_url: str | None = endpoint
        while next_url:
            payload = await self._get_json(next_url, headers=headers, params=params)
            records = payload.get("records")
            if not isinstance(records, list):
                raise ExternalAPIError("Invalid Salesforce query payload: expected list in records")

            for record in records:
                if not isinstance(record, dict):
                    continue
                service_date = record.get("ServiceDate")
                timestamp = _parse_timestamp(service_date)
                if timestamp < start_date or timestamp > end_date:
                    continue
                amount = _as_float(record.get("TotalPrice"))
                yield {
                    "provider": "saas",
                    "service": str(record.get("Description") or "Salesforce Contract"),
                    "region": "global",
                    "usage_type": "contract_line_item",
                    "cost_usd": amount,
                    "amount_raw": record.get("TotalPrice"),
                    "currency": str(record.get("CurrencyIsoCode") or "USD").upper(),
                    "timestamp": timestamp,
                    "source_adapter": "saas_salesforce_api",
                    "tags": {
                        "vendor": "salesforce",
                        "record_id": str(record.get("Id") or ""),
                    },
                }

            next_records = payload.get("nextRecordsUrl")
            if not isinstance(next_records, str) or not next_records.strip():
                break
            next_url = urljoin(base_url.rstrip("/") + "/", next_records.lstrip("/"))
            params = None

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
                async with httpx.AsyncClient(timeout=_NATIVE_TIMEOUT_SECONDS) as client:
                    response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ExternalAPIError("SaaS connector API returned invalid payload shape")
                return payload
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code
                retryable = status_code in _RETRYABLE_STATUS_CODES
                if retryable and attempt < _NATIVE_MAX_RETRIES:
                    logger.warning(
                        "saas_native_retry_http_status",
                        attempt=attempt,
                        max_attempts=_NATIVE_MAX_RETRIES,
                        status_code=status_code,
                        url=url,
                    )
                    await asyncio.sleep(0.05 * attempt)
                    continue
                raise ExternalAPIError(
                    f"SaaS connector API request failed with status {status_code}: {exc}"
                ) from exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt < _NATIVE_MAX_RETRIES:
                    logger.warning(
                        "saas_native_retry_transport_error",
                        attempt=attempt,
                        max_attempts=_NATIVE_MAX_RETRIES,
                        url=url,
                        error=str(exc),
                    )
                    await asyncio.sleep(0.05 * attempt)
                    continue
                raise ExternalAPIError(f"SaaS connector API request failed: {exc}") from exc
            except ValueError as exc:
                raise ExternalAPIError("SaaS connector API returned invalid JSON payload") from exc

        if last_error is not None:
            raise ExternalAPIError(f"SaaS connector API request failed: {last_error}") from last_error
        raise ExternalAPIError("SaaS connector API request failed unexpectedly")

    async def discover_resources(self, resource_type: str, region: str | None = None) -> list[dict[str, Any]]:
        return []
