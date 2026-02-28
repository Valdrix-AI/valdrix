from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any, Awaitable, Callable, cast

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
from app.shared.adapters.license_resource_ops import (
    build_discovered_license_resources,
    build_license_usage_rows,
    supports_license_discovery_resource_type,
    supports_license_usage_service,
)
from app.shared.adapters.license_vendor_registry import resolve_native_vendor
from app.shared.adapters.license_vendor_ops import (
    list_github_activity as vendor_list_github_activity,
    list_google_workspace_activity as vendor_list_google_workspace_activity,
    list_microsoft_365_activity as vendor_list_microsoft_365_activity,
    list_salesforce_activity as vendor_list_salesforce_activity,
    list_slack_activity as vendor_list_slack_activity,
    list_zoom_activity as vendor_list_zoom_activity,
    revoke_github as vendor_revoke_github,
    revoke_google_workspace as vendor_revoke_google_workspace,
    revoke_microsoft_365 as vendor_revoke_microsoft_365,
    revoke_salesforce as vendor_revoke_salesforce,
    revoke_slack as vendor_revoke_slack,
    revoke_zoom as vendor_revoke_zoom,
    stream_google_workspace_license_costs as vendor_stream_google_workspace_license_costs,
    stream_microsoft_365_license_costs as vendor_stream_microsoft_365_license_costs,
    verify_github as vendor_verify_github,
    verify_google_workspace as vendor_verify_google_workspace,
    verify_microsoft_365 as vendor_verify_microsoft_365,
    verify_salesforce as vendor_verify_salesforce,
    verify_slack as vendor_verify_slack,
    verify_zoom as vendor_verify_zoom,
)
from app.shared.core.credentials import LicenseCredentials
from app.shared.core.exceptions import ExternalAPIError, UnsupportedVendorError

logger = structlog.get_logger()

_NATIVE_TIMEOUT_SECONDS = 20.0
_NATIVE_MAX_RETRIES = 3
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}

_VERIFY_METHOD_BY_VENDOR: dict[str, str] = {
    "microsoft_365": "_verify_microsoft_365",
    "google_workspace": "_verify_google_workspace",
    "github": "_verify_github",
    "slack": "_verify_slack",
    "zoom": "_verify_zoom",
    "salesforce": "_verify_salesforce",
}

_REVOKE_METHOD_BY_VENDOR: dict[str, tuple[str, bool]] = {
    "google_workspace": ("_revoke_google_workspace", True),
    "microsoft_365": ("_revoke_microsoft_365", True),
    "github": ("_revoke_github", False),
    "slack": ("_revoke_slack", False),
    "zoom": ("_revoke_zoom", False),
    "salesforce": ("_revoke_salesforce", False),
}

_ACTIVITY_METHOD_BY_VENDOR: dict[str, str] = {
    "google_workspace": "_list_google_workspace_activity",
    "microsoft_365": "_list_microsoft_365_activity",
    "github": "_list_github_activity",
    "slack": "_list_slack_activity",
    "zoom": "_list_zoom_activity",
    "salesforce": "_list_salesforce_activity",
}

_NATIVE_STREAM_METHOD_BY_VENDOR: dict[str, str] = {
    "microsoft_365": "_stream_microsoft_365_license_costs",
    "google_workspace": "_stream_google_workspace_license_costs",
}


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
            self.last_error = (
                f"Native license auth is not supported for vendor '{self._vendor}'. "
                "Supported vendor aliases: microsoft_365, google_workspace, github, "
                "slack, zoom, salesforce (and common aliases). "
                "Use auth_method manual/csv for custom vendors."
            )
            return False

        if native_vendor is not None:
            try:
                await self._verify_native_vendor(native_vendor)
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
        return self._stream_cost_and_usage_impl(start_date, end_date, granularity)

    async def _stream_cost_and_usage_impl(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY",
    ) -> AsyncGenerator[dict[str, Any], None]:
        native_vendor = self._native_vendor
        stream_method_name = (
            _NATIVE_STREAM_METHOD_BY_VENDOR.get(native_vendor)
            if native_vendor is not None
            else None
        )
        if stream_method_name is not None:
            stream_method = getattr(self, stream_method_name)
            try:
                async for row in stream_method(start_date, end_date):
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

    async def _verify_native_vendor(self, native_vendor: str) -> None:
        method_name = _VERIFY_METHOD_BY_VENDOR.get(native_vendor)
        if method_name is None:
            raise ExternalAPIError(
                f"Unsupported native license vendor '{native_vendor}'"
            )
        await getattr(self, method_name)()

    async def _verify_microsoft_365(self) -> None:
        await vendor_verify_microsoft_365(self)

    async def _verify_google_workspace(self) -> None:
        await vendor_verify_google_workspace(self)

    async def _verify_github(self) -> None:
        await vendor_verify_github(self)

    async def _verify_slack(self) -> None:
        await vendor_verify_slack(self)

    async def _verify_zoom(self) -> None:
        await vendor_verify_zoom(self)

    async def _verify_salesforce(self) -> None:
        await vendor_verify_salesforce(self)

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

    async def _stream_google_workspace_license_costs(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> AsyncGenerator[dict[str, Any], None]:
        async for row in vendor_stream_google_workspace_license_costs(
            self, start_date, end_date
        ):
            yield row

    async def _stream_microsoft_365_license_costs(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> AsyncGenerator[dict[str, Any], None]:
        async for row in vendor_stream_microsoft_365_license_costs(
            self, start_date, end_date
        ):
            yield row

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
        revoke_method = (
            _REVOKE_METHOD_BY_VENDOR.get(native_vendor)
            if native_vendor is not None
            else None
        )
        if revoke_method is not None:
            method_name, supports_sku = revoke_method
            if supports_sku:
                revoke_with_sku = cast(
                    Callable[[str, str | None], Awaitable[bool]],
                    getattr(self, method_name),
                )
                return await revoke_with_sku(resource_id, sku_id)
            revoke_without_sku = cast(
                Callable[[str], Awaitable[bool]],
                getattr(self, method_name),
            )
            return await revoke_without_sku(resource_id)

        raise UnsupportedVendorError(
            (
                f"License revocation is not supported for vendor '{self._vendor}'. "
                "Use a supported native vendor or manual follow-up workflow."
            ),
            details={"vendor": self._vendor, "operation": "revoke_license"},
        )

    async def list_users_activity(self) -> list[dict[str, Any]]:
        """
        List all users and their last activity timestamp.
        Supported for: google_workspace, microsoft_365, github, slack, zoom, salesforce
        """
        native_vendor = self._native_vendor
        if native_vendor is None:
            return self._list_manual_feed_activity()
        method_name = _ACTIVITY_METHOD_BY_VENDOR.get(native_vendor)
        if method_name is None:
            return []
        activity_method = cast(
            Callable[[], Awaitable[list[dict[str, Any]]]],
            getattr(self, method_name),
        )
        return await activity_method()

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

    async def _revoke_google_workspace(
        self, resource_id: str, sku_id: str | None = None
    ) -> bool:
        return await vendor_revoke_google_workspace(self, resource_id, sku_id)

    async def _revoke_microsoft_365(
        self, resource_id: str, sku_id: str | None = None
    ) -> bool:
        return await vendor_revoke_microsoft_365(self, resource_id, sku_id)

    async def _revoke_github(self, resource_id: str) -> bool:
        return await vendor_revoke_github(self, resource_id)

    async def _revoke_zoom(self, resource_id: str) -> bool:
        return await vendor_revoke_zoom(self, resource_id)

    async def _revoke_slack(self, resource_id: str) -> bool:
        return await vendor_revoke_slack(self, resource_id)

    async def _revoke_salesforce(self, resource_id: str) -> bool:
        return await vendor_revoke_salesforce(self, resource_id)

    async def _list_google_workspace_activity(self) -> list[dict[str, Any]]:
        return await vendor_list_google_workspace_activity(self)

    async def _list_microsoft_365_activity(self) -> list[dict[str, Any]]:
        return await vendor_list_microsoft_365_activity(self)

    async def _list_github_activity(self) -> list[dict[str, Any]]:
        return await vendor_list_github_activity(self)

    async def _list_zoom_activity(self) -> list[dict[str, Any]]:
        return await vendor_list_zoom_activity(self)

    async def _list_slack_activity(self) -> list[dict[str, Any]]:
        return await vendor_list_slack_activity(self)

    async def _list_salesforce_activity(self) -> list[dict[str, Any]]:
        return await vendor_list_salesforce_activity(self)

    async def discover_resources(
        self, resource_type: str, region: str | None = None
    ) -> list[dict[str, Any]]:
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
