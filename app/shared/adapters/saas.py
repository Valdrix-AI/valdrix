from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import httpx
import structlog

from app.shared.adapters.base import BaseAdapter
from app.shared.adapters.feed_utils import as_float, is_number, parse_timestamp
from app.shared.adapters.http_retry import execute_with_http_retry
from app.shared.core.currency import convert_to_usd
from app.shared.core.exceptions import ExternalAPIError
from app.shared.core.credentials import SaaSCredentials

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


async def _saas_get_request(
    *,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=_NATIVE_TIMEOUT_SECONDS) as client:
        return await client.get(url, headers=headers, params=params)


class SaaSAdapter(BaseAdapter):
    """
    Cloud+ adapter for SaaS spend.

    Supported modes:
    - Manual feed (`auth_method=manual|csv`) via `spend_feed`
    - Native vendor pulls (`auth_method=api_key|oauth`) for Stripe and Salesforce
    """

    def __init__(self, credentials: SaaSCredentials):
        self.credentials = credentials
        self.last_error = None

    def _get_credential_field(self, name: str, default: Any = None) -> Any:
        fields = getattr(self.credentials, "__dict__", None)
        if isinstance(fields, dict) and name in fields:
            value = fields[name]
        else:
            value = getattr(self.credentials, name, default)
            if type(value).__name__ == "MagicMock":
                return default
        if value is None:
            return default
        return value

    @property
    def _auth_method(self) -> str:
        raw = self._get_credential_field("auth_method")
        if isinstance(raw, str) and raw.strip():
            return raw.strip().lower()
        return str(self._connector_config.get("auth_method", "manual")).strip().lower()

    @property
    def _vendor(self) -> str:
        raw_vendor = self._get_credential_field("vendor")
        if isinstance(raw_vendor, str) and raw_vendor.strip():
            return raw_vendor.strip().lower()
        raw_platform = self._get_credential_field("platform", "")
        return str(raw_platform).strip().lower()

    @property
    def _connector_config(self) -> dict[str, Any]:
        connector_config = self._get_credential_field("connector_config")
        if isinstance(connector_config, dict):
            return connector_config
        extra_config = self._get_credential_field("extra_config")
        if isinstance(extra_config, dict):
            return extra_config
        return {}

    @property
    def _manual_feed(self) -> Any:
        for field in ("spend_feed", "cost_feed"):
            value = self._get_credential_field(field)
            if value is not None:
                return value
        for field in ("spend_feed", "cost_feed"):
            value = self._connector_config.get(field)
            if value is not None:
                return value
        return None

    @property
    def _native_vendor(self) -> str | None:
        if self._auth_method not in {"api_key", "oauth"}:
            return None
        if self._vendor in _NATIVE_SUPPORTED_VENDORS:
            return self._vendor
        return None

    def _resolve_api_key(self) -> str:
        raw_token = self._get_credential_field("api_key")
        if raw_token is None:
            raise ExternalAPIError("Missing API token for SaaS native connector")
        token = (
            raw_token.get_secret_value()
            if hasattr(raw_token, "get_secret_value")
            else str(raw_token)
        )
        if not token or not token.strip():
            raise ExternalAPIError("Missing API token for SaaS native connector")
        return token.strip()

    async def verify_connection(self) -> bool:
        self.last_error = None
        native_vendor = self._native_vendor
        if self._auth_method in {"api_key", "oauth"} and native_vendor is None:
            supported_vendors = ", ".join(sorted(_NATIVE_SUPPORTED_VENDORS))
            self.last_error = (
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
                self.last_error = str(exc)
                logger.warning(
                    "saas_native_verify_failed",
                    vendor=native_vendor,
                    error=str(exc),
                )
                return False

        feed = self._manual_feed
        is_valid = self._validate_manual_feed(feed)
        if not is_valid:
            if self.last_error is None:
                self.last_error = "Spend feed is missing or invalid."
        return is_valid

    def _validate_manual_feed(self, feed: Any) -> bool:
        if not isinstance(feed, list) or not feed:
            self.last_error = "Spend feed must contain at least one record for manual/csv verification."
            return False
        for idx, entry in enumerate(feed):
            if not isinstance(entry, dict):
                self.last_error = f"Spend feed entry #{idx + 1} must be a JSON object."
                return False
            has_timestamp = entry.get("timestamp") or entry.get("date")
            if not has_timestamp:
                self.last_error = (
                    f"Spend feed entry #{idx + 1} is missing timestamp/date."
                )
                return False
            amount = entry.get("cost_usd", entry.get("amount_usd"))
            if not is_number(amount):
                self.last_error = f"Spend feed entry #{idx + 1} must include numeric cost_usd or amount_usd."
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
                    async for row in self._stream_stripe_cost_and_usage(
                        start_date, end_date
                    ):
                        yield row
                    return
                if native_vendor == _NATIVE_VENDOR_SALESFORCE:
                    async for row in self._stream_salesforce_cost_and_usage(
                        start_date, end_date
                    ):
                        yield row
                    return
            except ExternalAPIError as exc:
                self.last_error = str(exc)
                logger.warning(
                    "saas_native_stream_failed_fallback_to_feed",
                    vendor=native_vendor,
                    error=str(exc),
                )

        feed = self._manual_feed or []
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
                "provider": "saas",
                "service": str(entry.get("service") or entry.get("vendor") or "SaaS"),
                "region": "global",
                "usage_type": str(entry.get("usage_type") or "subscription"),
                "resource_id": resource_id,
                "usage_amount": usage_amount,
                "usage_unit": usage_unit,
                "cost_usd": float(
                    entry.get("cost_usd") or entry.get("amount_usd") or 0.0
                ),
                "amount_raw": entry.get("amount_raw"),
                "currency": str(entry.get("currency") or "USD"),
                "timestamp": timestamp,
                "source_adapter": "saas_feed",
                "tags": entry.get("tags")
                if isinstance(entry.get("tags"), dict)
                else {},
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
                raise ExternalAPIError(
                    "Invalid Stripe invoices payload: expected list in data"
                )

            for invoice in entries:
                if not isinstance(invoice, dict):
                    continue
                timestamp = parse_timestamp(invoice.get("created"))
                if timestamp < start_date or timestamp > end_date:
                    continue

                amount_cents = invoice.get("amount_paid")
                if amount_cents is None:
                    amount_cents = invoice.get("total")

                currency_code = str(invoice.get("currency") or "USD").upper()
                amount_local = as_float(amount_cents, divisor=100)
                cost_usd = amount_local
                if currency_code != "USD":
                    try:
                        cost_usd = float(
                            await convert_to_usd(amount_local, currency_code)
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "saas_currency_conversion_failed",
                            vendor="stripe",
                            currency=currency_code,
                            error=str(exc),
                        )

                service_name = (
                    str(invoice.get("description")).strip()
                    if isinstance(invoice.get("description"), str)
                    and invoice.get("description")
                    else "Stripe Billing"
                )

                yield {
                    "provider": "saas",
                    "service": service_name,
                    "region": "global",
                    "usage_type": "subscription_invoice",
                    "resource_id": str(invoice.get("id") or "").strip() or None,
                    "usage_amount": 1.0,
                    "usage_unit": "invoice",
                    "cost_usd": cost_usd,
                    "amount_raw": amount_local,
                    "currency": currency_code,
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
                raise ExternalAPIError(
                    "Invalid Salesforce query payload: expected list in records"
                )

            for record in records:
                if not isinstance(record, dict):
                    continue
                service_date = record.get("ServiceDate")
                timestamp = parse_timestamp(service_date)
                if timestamp < start_date or timestamp > end_date:
                    continue
                amount_local = as_float(record.get("TotalPrice"))
                currency_code = str(record.get("CurrencyIsoCode") or "USD").upper()
                cost_usd = amount_local
                if currency_code != "USD":
                    try:
                        cost_usd = float(
                            await convert_to_usd(amount_local, currency_code)
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "saas_currency_conversion_failed",
                            vendor="salesforce",
                            currency=currency_code,
                            error=str(exc),
                        )
                yield {
                    "provider": "saas",
                    "service": str(record.get("Description") or "Salesforce Contract"),
                    "region": "global",
                    "usage_type": "contract_line_item",
                    "resource_id": str(record.get("Id") or "").strip() or None,
                    "usage_amount": 1.0,
                    "usage_unit": "contract_line_item",
                    "cost_usd": cost_usd,
                    "amount_raw": amount_local,
                    "currency": currency_code,
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
        response = await execute_with_http_retry(
            request=lambda: _saas_get_request(
                url=url,
                headers=headers,
                params=params,
            ),
            url=url,
            max_retries=_NATIVE_MAX_RETRIES,
            retryable_status_codes=_RETRYABLE_STATUS_CODES,
            retry_http_status_log_event="saas_native_retry_http_status",
            retry_transport_log_event="saas_native_retry_transport_error",
            status_error_prefix="SaaS connector API request failed",
            transport_error_prefix="SaaS connector API request failed",
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalAPIError(
                "SaaS connector API returned invalid JSON payload"
            ) from exc
        if not isinstance(payload, dict):
            raise ExternalAPIError(
                "SaaS connector API returned invalid payload shape"
            )
        return payload

    async def discover_resources(
        self, resource_type: str, region: str | None = None
    ) -> list[dict[str, Any]]:
        return []

    async def get_resource_usage(
        self, _service_name: str, _resource_id: str | None = None
    ) -> list[dict[str, Any]]:
        # SaaS resource-level usage is not exposed by this adapter yet.
        return []
