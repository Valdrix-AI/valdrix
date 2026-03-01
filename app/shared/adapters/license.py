from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import httpx
import structlog

from app.shared.adapters.base import BaseAdapter
from app.shared.adapters.feed_utils import as_float, is_number, parse_timestamp
from app.shared.adapters.http_retry import execute_with_http_retry
from app.shared.adapters.license_feed_ops import (
    coerce_bool as feed_coerce_bool,
    iter_manual_cost_rows,
    list_manual_feed_activity,
    normalize_email as feed_normalize_email,
    normalize_text as feed_normalize_text,
    validate_manual_feed,
)
from app.shared.adapters.license_native_dispatch import (
    list_native_activity,
    resolve_native_stream_method,
    revoke_native_license,
    supported_native_vendors,
    verify_native_vendor,
)
from app.shared.adapters.license_resource_ops import (
    build_discovered_license_resources,
    build_license_usage_rows,
    supports_license_discovery_resource_type,
    supports_license_usage_service,
)
from app.shared.adapters.license_vendor_registry import resolve_native_vendor
from app.shared.core.credentials import LicenseCredentials
from app.shared.core.exceptions import ExternalAPIError

logger = structlog.get_logger()

_NATIVE_TIMEOUT_SECONDS = 20.0
_NATIVE_MAX_RETRIES = 3
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


async def _license_get_request(
    *,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=_NATIVE_TIMEOUT_SECONDS) as client:
        return await client.get(url, headers=headers, params=params)


class LicenseAdapter(BaseAdapter):
    """
    Cloud+ adapter for license/ITAM spend.

    Supported modes:
    - Manual feed (`auth_method=manual|csv`) via `license_feed`
    - Native vendor pulls (`auth_method=api_key|oauth`) for:
      Microsoft 365, Google Workspace, GitHub, Slack, Zoom, Salesforce
    """

    def __init__(self, credentials: LicenseCredentials):
        self.credentials = credentials
        self.last_error = None

    @property
    def _vendor(self) -> str:
        return self.credentials.vendor.strip().lower()

    @property
    def _auth_method(self) -> str:
        return self.credentials.auth_method.strip().lower()

    @property
    def _connector_config(self) -> dict[str, Any]:
        return self.credentials.connector_config

    @property
    def _native_vendor(self) -> str | None:
        return resolve_native_vendor(auth_method=self._auth_method, vendor=self._vendor)

    def _unsupported_native_vendor_message(self) -> str:
        supported_vendors = ", ".join(supported_native_vendors())
        return (
            f"Native license auth is not supported for vendor '{self._vendor}'. "
            f"Supported vendor aliases: {supported_vendors} (and common aliases). "
            "Use auth_method manual/csv for custom vendors."
        )

    def _resolve_api_key(self) -> str:
        token = self.credentials.api_key
        if not token:
            raise ExternalAPIError("Missing API token for license native connector")
        resolved = (
            token.get_secret_value() if hasattr(token, "get_secret_value") else str(token)
        )
        if not resolved or not resolved.strip():
            raise ExternalAPIError("Missing API token for license native connector")
        return resolved.strip()

    @staticmethod
    def _normalize_text(value: Any) -> str | None:
        return feed_normalize_text(value)

    @staticmethod
    def _normalize_email(value: Any) -> str | None:
        return feed_normalize_email(value)

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        return feed_coerce_bool(value)

    async def verify_connection(self) -> bool:
        self.last_error = None
        native_vendor = self._native_vendor
        if self._auth_method in {"api_key", "oauth"} and native_vendor is None:
            self.last_error = self._unsupported_native_vendor_message()
            return False

        if native_vendor is not None:
            try:
                await verify_native_vendor(self, native_vendor)
                return True
            except ExternalAPIError as exc:
                self.last_error = str(exc)
                logger.warning(
                    "license_native_verify_failed", vendor=native_vendor, error=str(exc)
                )
                return False

        feed = self.credentials.license_feed
        is_valid = self._validate_manual_feed(feed)
        if not is_valid:
            if self.last_error is None:
                self.last_error = "License feed is missing or invalid."
        return is_valid

    def _validate_manual_feed(self, feed: Any) -> bool:
        error = validate_manual_feed(feed, is_number_fn=is_number)
        if error is not None:
            self.last_error = error
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

    def stream_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY",
    ) -> AsyncGenerator[dict[str, Any], None]:
        async def _iterate() -> AsyncGenerator[dict[str, Any], None]:
            native_vendor = self._native_vendor
            if self._auth_method in {"api_key", "oauth"} and native_vendor is None:
                self.last_error = self._unsupported_native_vendor_message()
                logger.warning(
                    "license_native_stream_unsupported_vendor",
                    vendor=self._vendor,
                    auth_method=self._auth_method,
                )
                return
            stream_method = (
                resolve_native_stream_method(native_vendor)
                if native_vendor is not None
                else None
            )
            if stream_method is not None:
                try:
                    async for row in stream_method(self, start_date, end_date):
                        yield row
                    return
                except ExternalAPIError as exc:
                    self.last_error = str(exc)
                    logger.warning(
                        "license_native_stream_failed_fallback_to_feed",
                        vendor=native_vendor,
                        error=str(exc),
                    )

            feed = self.credentials.license_feed
            for row in iter_manual_cost_rows(
                feed=feed,
                start_date=start_date,
                end_date=end_date,
                parse_timestamp_fn=parse_timestamp,
                as_float_fn=as_float,
                is_number_fn=is_number,
            ):
                yield row

        return _iterate()

    def _salesforce_instance_url(self) -> str:
        raw = self._connector_config.get("salesforce_instance_url") or self._connector_config.get("instance_url")
        if not isinstance(raw, str) or not raw.strip():
            raise ExternalAPIError(
                "Missing connector_config.salesforce_instance_url for Salesforce connector"
            )
        normalized = raw.strip().rstrip("/")
        if not normalized.startswith(("https://", "http://")):
            raise ExternalAPIError(
                "connector_config.salesforce_instance_url must be an http(s) URL"
            )
        return normalized

    async def _get_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GET request and return a normalized JSON object payload."""
        response = await execute_with_http_retry(
            request=lambda: _license_get_request(
                url=url,
                headers=headers,
                params=params,
            ),
            url=url,
            max_retries=_NATIVE_MAX_RETRIES,
            retryable_status_codes=_RETRYABLE_STATUS_CODES,
            retry_http_status_log_event="license_native_retry_http_status",
            retry_transport_log_event="license_native_retry_transport_error",
            status_error_prefix="License connector API request failed",
            transport_error_prefix="License connector API request failed",
        )
        if response.status_code == 204:
            return {}
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalAPIError(
                "License connector API returned invalid JSON payload"
            ) from exc
        if isinstance(payload, list):
            # Some vendor APIs return top-level arrays (for example GitHub members/events).
            # Keep adapter callers on a dict contract.
            return {"value": payload}
        if not isinstance(payload, dict):
            raise ExternalAPIError(
                "License connector API returned invalid payload shape"
            )
        return payload

    async def revoke_license(self, resource_id: str, sku_id: str | None = None) -> bool:
        """
        Revoke a license/seat for a specific user.
        Supported for: google_workspace, microsoft_365, github, slack, zoom, salesforce
        """
        native_vendor = self._native_vendor
        return await revoke_native_license(
            self,
            native_vendor=native_vendor,
            resource_id=resource_id,
            sku_id=sku_id,
        )

    async def list_users_activity(self) -> list[dict[str, Any]]:
        """
        List all users and their last activity timestamp.
        Supported for: google_workspace, microsoft_365, github, slack, zoom, salesforce
        """
        native_vendor = self._native_vendor
        if self._auth_method in {"api_key", "oauth"} and native_vendor is None:
            self.last_error = self._unsupported_native_vendor_message()
            logger.warning(
                "license_native_activity_unsupported_vendor",
                vendor=self._vendor,
                auth_method=self._auth_method,
            )
            return []
        if native_vendor is None:
            return self._list_manual_feed_activity()
        return await list_native_activity(self, native_vendor)

    def _list_manual_feed_activity(self) -> list[dict[str, Any]]:
        """
        Build user activity records from manual/csv license feeds.

        Expected optional keys per feed row:
        user_id/email/resource_id, last_active_at/last_login_at/timestamp, is_admin/role,
        suspended/inactive/status.
        """
        return list_manual_feed_activity(
            feed=self.credentials.license_feed,
            parse_timestamp_fn=parse_timestamp,
        )

    async def discover_resources(
        self, resource_type: str, region: str | None = None
    ) -> list[dict[str, Any]]:
        self._clear_last_error()
        if not supports_license_discovery_resource_type(resource_type):
            return []
        try:
            activity_rows = await self.list_users_activity()
        except ExternalAPIError as exc:
            self.last_error = str(exc)
            logger.warning(
                "license_discover_resources_failed",
                vendor=self._vendor,
                resource_type=resource_type,
                error=str(exc),
            )
            return []
        return build_discovered_license_resources(
            activity_rows=activity_rows,
            vendor=self._vendor,
            resource_type=resource_type,
            region=region,
        )

    async def get_resource_usage(
        self, service_name: str, resource_id: str | None = None
    ) -> list[dict[str, Any]]:
        self._clear_last_error()
        if not supports_license_usage_service(service_name):
            return []
        try:
            activity_rows = await self.list_users_activity()
        except ExternalAPIError as exc:
            self.last_error = str(exc)
            logger.warning(
                "license_resource_usage_failed",
                vendor=self._vendor,
                service_name=service_name,
                error=str(exc),
            )
            return []

        default_price = as_float(
            self._connector_config.get("default_seat_price_usd"),
            default=0.0,
        )
        if default_price < 0:
            default_price = 0.0
        currency = str(self._connector_config.get("currency") or "USD")

        return build_license_usage_rows(
            activity_rows=activity_rows,
            vendor=self._vendor,
            service_name=service_name,
            resource_id=resource_id,
            default_seat_price_usd=default_price,
            currency=currency,
        )
