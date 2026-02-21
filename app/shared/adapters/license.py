import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from app.shared.adapters.base import BaseAdapter
from app.shared.adapters.feed_utils import as_float, is_number, parse_timestamp
from app.shared.core.credentials import LicenseCredentials
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
_GOOGLE_LICENSE_VENDORS = {
    "google_workspace",
    "googleworkspace",
    "gsuite",
    "google",
}
_GITHUB_LICENSE_VENDORS = {"github", "github_enterprise"}
_SLACK_LICENSE_VENDORS = {"slack", "slack_enterprise"}
_ZOOM_LICENSE_VENDORS = {"zoom"}
_SALESFORCE_LICENSE_VENDORS = {"salesforce", "sfdc"}


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
        if self._auth_method not in {"api_key", "oauth"}:
            return None
        if self._vendor in _MICROSOFT_LICENSE_VENDORS:
            return "microsoft_365"
        if self._vendor in _GOOGLE_LICENSE_VENDORS:
            return "google_workspace"
        if self._vendor in _GITHUB_LICENSE_VENDORS:
            return "github"
        if self._vendor in _SLACK_LICENSE_VENDORS:
            return "slack"
        if self._vendor in _ZOOM_LICENSE_VENDORS:
            return "zoom"
        if self._vendor in _SALESFORCE_LICENSE_VENDORS:
            return "salesforce"
        return None

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
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @staticmethod
    def _normalize_email(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower()
        if not normalized or "@" not in normalized:
            return None
        return normalized

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "y", "on"}:
                return True
            if lowered in {"0", "false", "no", "n", "off"}:
                return False
        return False

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
        if not isinstance(feed, list) or not feed:
            self.last_error = "License feed must contain at least one record for manual/csv verification."
            return False
        for idx, entry in enumerate(feed):
            if not isinstance(entry, dict):
                self.last_error = (
                    f"License feed entry #{idx + 1} must be a JSON object."
                )
                return False
            has_timestamp = entry.get("timestamp") or entry.get("date")
            if not has_timestamp:
                self.last_error = (
                    f"License feed entry #{idx + 1} is missing timestamp/date."
                )
                return False
            amount = entry.get("cost_usd", entry.get("amount_usd"))
            if not is_number(amount):
                self.last_error = f"License feed entry #{idx + 1} must include numeric cost_usd or amount_usd."
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
        if native_vendor == "microsoft_365":
            try:
                async for row in self._stream_microsoft_365_license_costs(
                    start_date, end_date
                ):
                    yield row
                return
            except ExternalAPIError as exc:
                self.last_error = str(exc)
                logger.warning(
                    "license_native_stream_failed_fallback_to_feed",
                    vendor=native_vendor,
                    error=str(exc),
                )

        if native_vendor == "google_workspace":
            try:
                async for row in self._stream_google_workspace_license_costs(
                    start_date, end_date
                ):
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

    async def _verify_native_vendor(self, native_vendor: str) -> None:
        if native_vendor == "microsoft_365":
            await self._verify_microsoft_365()
            return
        if native_vendor == "google_workspace":
            await self._verify_google_workspace()
            return
        if native_vendor == "github":
            await self._verify_github()
            return
        if native_vendor == "slack":
            await self._verify_slack()
            return
        if native_vendor == "zoom":
            await self._verify_zoom()
            return
        if native_vendor == "salesforce":
            await self._verify_salesforce()
            return
        raise ExternalAPIError(f"Unsupported native license vendor '{native_vendor}'")

    async def _verify_microsoft_365(self) -> None:
        token = self._resolve_api_key()
        await self._get_json(
            "https://graph.microsoft.com/v1.0/subscribedSkus",
            headers={"Authorization": f"Bearer {token}"},
        )

    async def _verify_google_workspace(self) -> None:
        token = self._resolve_api_key()
        await self._get_json(
            "https://admin.googleapis.com/admin/directory/v1/customer/my_customer",
            headers={"Authorization": f"Bearer {token}"},
        )

    async def _verify_github(self) -> None:
        token = self._resolve_api_key()
        await self._get_json(
            "https://api.github.com/user",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )

    async def _verify_slack(self) -> None:
        token = self._resolve_api_key()
        payload = await self._get_json(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {token}"},
        )
        if not payload.get("ok"):
            raise ExternalAPIError(
                f"Slack auth.test failed: {payload.get('error') or 'unknown_error'}"
            )

    async def _verify_zoom(self) -> None:
        token = self._resolve_api_key()
        await self._get_json(
            "https://api.zoom.us/v2/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    async def _verify_salesforce(self) -> None:
        token = self._resolve_api_key()
        instance_url = self._salesforce_instance_url()
        api_version = self._connector_config.get("salesforce_api_version", "v60.0")
        await self._get_json(
            f"{instance_url}/services/data/{api_version}/limits",
            headers={"Authorization": f"Bearer {token}"},
        )

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
        token = self._resolve_api_key()
        headers = {"Authorization": f"Bearer {token}"}

        # Standard Google Workspace SKUs to check if none specified
        sku_prices_raw = self._connector_config.get("sku_prices")
        sku_prices: dict[str, float] = {}
        if isinstance(sku_prices_raw, dict):
            for key, value in sku_prices_raw.items():
                if isinstance(key, str) and key.strip():
                    sku_prices[key.strip()] = as_float(value)

        default_price = as_float(
            self._connector_config.get("default_seat_price_usd"),
            default=12.0,  # Business Standard default
        )
        default_currency = str(self._connector_config.get("currency") or "USD").upper()
        timestamp = (
            end_date if end_date.tzinfo else end_date.replace(tzinfo=timezone.utc)
        )

        # Target Products/SKUs (simplified for connector parity)
        # In a full implementation, we'd list all assigned licenses via Directories API
        target_skus = list(sku_prices.keys()) or [
            "Google-Apps-For-Business",
            "1010020027",
        ]
        rows_emitted = 0
        last_error: Exception | None = None

        for sku_id in target_skus:
            try:
                # GET https://licensing.googleapis.com/licensing/v1/product/{productId}/sku/{skuId}/usage
                # ProductID for Workspace is usually 'Google-Apps'
                product_id = "Google-Apps"
                url = f"https://licensing.googleapis.com/licensing/v1/product/{product_id}/sku/{sku_id}/usage"

                payload = await self._get_json(url, headers=headers)
                consumed_units = as_float(payload.get("totalUnits"), default=0.0)

                unit_price = sku_prices.get(sku_id, default_price)
                total_cost = round(consumed_units * unit_price, 2)

                if timestamp < start_date or timestamp > end_date:
                    continue

                rows_emitted += 1
                yield {
                    "provider": "license",
                    "service": sku_id,
                    "region": "global",
                    "usage_type": "seat_license",
                    "resource_id": sku_id,
                    "usage_amount": consumed_units,
                    "usage_unit": "seat",
                    "cost_usd": total_cost,
                    "amount_raw": consumed_units,
                    "currency": default_currency,
                    "timestamp": timestamp,
                    "source_adapter": "google_workspace_licensing",
                    "tags": {
                        "vendor": "google_workspace",
                        "sku_id": sku_id,
                        "unit_price_usd": unit_price,
                    },
                }
            except (ExternalAPIError, httpx.HTTPError) as e:
                last_error = e
                logger.warning(
                    "google_workspace_sku_fetch_failed",
                    sku_id=sku_id,
                    error=str(e),
                )
                continue

        if rows_emitted == 0 and last_error is not None:
            raise ExternalAPIError(
                "Google Workspace native usage fetch failed for all configured SKUs"
            ) from last_error

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
        """Execute a GET request and return a normalized JSON object payload."""
        last_error: Exception | None = None
        for attempt in range(1, _NATIVE_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=_NATIVE_TIMEOUT_SECONDS) as client:
                    response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                if response.status_code == 204:
                    return {}
                payload = response.json()
                if isinstance(payload, list):
                    # Some vendor APIs return top-level arrays (for example GitHub members/events).
                    # Keep adapter callers on a dict contract.
                    return {"value": payload}
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

    async def revoke_license(self, resource_id: str, sku_id: str | None = None) -> bool:
        """
        Revoke a license/seat for a specific user.
        Supported for: google_workspace, microsoft_365, github, slack, zoom, salesforce
        """
        native_vendor = self._native_vendor
        if native_vendor == "google_workspace":
            return await self._revoke_google_workspace(resource_id, sku_id)
        if native_vendor == "microsoft_365":
            return await self._revoke_microsoft_365(resource_id, sku_id)
        if native_vendor == "github":
            return await self._revoke_github(resource_id)
        if native_vendor == "slack":
            return await self._revoke_slack(resource_id)
        if native_vendor == "zoom":
            return await self._revoke_zoom(resource_id)
        if native_vendor == "salesforce":
            return await self._revoke_salesforce(resource_id)
            
        raise NotImplementedError(
            f"License revocation not implemented for vendor '{self._vendor}'"
        )

    async def _revoke_google_workspace(self, resource_id: str, sku_id: str | None = None) -> bool:
        token = self._resolve_api_key()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        product_id = "Google-Apps"
        skus_to_check = [sku_id] if sku_id else self._connector_config.get("managed_skus", ["Google-Apps-For-Business", "1010020027"])

        success = False
        for current_sku in skus_to_check:
            try:
                url = f"https://licensing.googleapis.com/licensing/v1/product/{product_id}/sku/{current_sku}/user/{resource_id}"
                
                from app.shared.core.http import get_http_client
                client = get_http_client()
                response = await client.delete(url, headers=headers)
                
                if response.status_code == 204:
                    logger.info("google_workspace_license_revoked", user_id=resource_id, sku_id=current_sku)
                    success = True
                    break
                elif response.status_code != 404:
                    logger.warning("google_workspace_license_revoke_failed", user_id=resource_id, sku_id=current_sku, status=response.status_code)
            except (ExternalAPIError, httpx.HTTPError) as e:
                logger.error("google_workspace_license_revoke_error", user_id=resource_id, error=str(e))
                continue

        return success

    async def list_users_activity(self) -> list[dict[str, Any]]:
        """
        List all users and their last activity timestamp.
        Supported for: google_workspace, microsoft_365, github, slack, zoom, salesforce
        """
        native_vendor = self._native_vendor
        if native_vendor is None:
            return self._list_manual_feed_activity()
        if native_vendor == "google_workspace":
            return await self._list_google_workspace_activity()
        if native_vendor == "microsoft_365":
            return await self._list_microsoft_365_activity()
        if native_vendor == "github":
            return await self._list_github_activity()
        if native_vendor == "slack":
            return await self._list_slack_activity()
        if native_vendor == "zoom":
            return await self._list_zoom_activity()
        if native_vendor == "salesforce":
            return await self._list_salesforce_activity()
            
        return []

    def _list_manual_feed_activity(self) -> list[dict[str, Any]]:
        """
        Build user activity records from manual/csv license feeds.

        Expected optional keys per feed row:
        user_id/email/resource_id, last_active_at/last_login_at/timestamp, is_admin/role,
        suspended/inactive/status.
        """
        feed = self.credentials.license_feed
        if not isinstance(feed, list):
            return []

        consolidated: dict[str, dict[str, Any]] = {}
        for entry in feed:
            if not isinstance(entry, dict):
                continue

            user_id = self._normalize_text(
                entry.get("user_id")
                or entry.get("principal_id")
                or entry.get("resource_id")
                or entry.get("id")
            )
            email = self._normalize_email(entry.get("email"))
            if email is None and user_id and "@" in user_id:
                email = user_id.lower()

            identity = user_id or email
            if not identity:
                continue

            last_active_at = None
            for candidate in (
                entry.get("last_active_at"),
                entry.get("last_login_at"),
                entry.get("last_login"),
                entry.get("last_activity_at"),
                entry.get("last_seen_at"),
                entry.get("timestamp"),
                entry.get("date"),
            ):
                if candidate in (None, ""):
                    continue
                try:
                    last_active_at = parse_timestamp(candidate)
                except (TypeError, ValueError):
                    continue
                break

            role = str(entry.get("role") or "").strip().lower()
            is_admin = (
                self._coerce_bool(entry.get("is_admin"))
                or role in {"admin", "owner", "super_admin", "system administrator"}
            )
            status = str(entry.get("status") or "").strip().lower()
            suspended = (
                self._coerce_bool(entry.get("suspended"))
                or self._coerce_bool(entry.get("inactive"))
                or status in {"inactive", "suspended", "disabled", "deactivated"}
            )

            full_name = self._normalize_text(
                entry.get("full_name")
                or entry.get("display_name")
                or entry.get("name")
            )

            current = consolidated.get(identity)
            if current is None:
                consolidated[identity] = {
                    "user_id": user_id or email or identity,
                    "email": email,
                    "full_name": full_name,
                    "last_active_at": last_active_at,
                    "is_admin": is_admin,
                    "suspended": suspended,
                }
                continue

            if not current.get("email") and email:
                current["email"] = email
            if not current.get("full_name") and full_name:
                current["full_name"] = full_name
            if not current.get("user_id") and (user_id or email):
                current["user_id"] = user_id or email
            if last_active_at is not None:
                existing_last = current.get("last_active_at")
                if existing_last is None or last_active_at > existing_last:
                    current["last_active_at"] = last_active_at

            current["is_admin"] = bool(current.get("is_admin") or is_admin)
            current["suspended"] = bool(current.get("suspended") or suspended)

        return list(consolidated.values())

    async def _revoke_microsoft_365(self, resource_id: str, sku_id: str | None = None) -> bool:
        """
        Revoke license for M365 user via assignLicense endpoint.
        """
        token = self._resolve_api_key()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        
        # In M365, 'resource_id' is usually the userPrincipalName or id.
        # sku_id is required to know WHICH license to remove.
        if not sku_id:
            logger.warning("m365_revoke_failed_no_sku", user_id=resource_id)
            return False

        url = f"https://graph.microsoft.com/v1.0/users/{resource_id}/assignLicense"
        payload = {
            "addLicenses": [],
            "removeLicenses": [sku_id]
        }
        
        try:
            from app.shared.core.http import get_http_client
            client = get_http_client()
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                logger.info("m365_license_revoked", user_id=resource_id, sku_id=sku_id)
                return True
            else:
                logger.warning("m365_license_revoke_failed", user_id=resource_id, status=response.status_code)
                return False
        except (ExternalAPIError, httpx.HTTPError) as e:
            logger.error("m365_license_revoke_error", user_id=resource_id, error=str(e))
            return False

    async def _list_microsoft_365_activity(self) -> list[dict[str, Any]]:
        """
        List M365 users and activity via signInActivity property.
        """
        token = self._resolve_api_key()
        headers = {"Authorization": f"Bearer {token}"}

        admin_upns_raw = self._connector_config.get("admin_upns", [])
        admin_upns = {
            item.strip().lower()
            for item in admin_upns_raw
            if isinstance(item, str) and item.strip()
        }

        # We need signInActivity which requires Entra ID P1/P2
        url = "https://graph.microsoft.com/v1.0/users?$select=displayName,userPrincipalName,id,signInActivity,accountEnabled"

        try:
            payload = await self._get_json(url, headers=headers)
            users_list = payload.get("value", [])

            activity_records = []
            for user in users_list:
                email = user.get("userPrincipalName")
                display_name = user.get("displayName")
                sign_in = user.get("signInActivity", {})

                # Use lastSuccessfulSignInDateTime or fallback to lastSignInDateTime
                last_login_raw = sign_in.get(
                    "lastSuccessfulSignInDateTime"
                ) or sign_in.get("lastSignInDateTime")

                last_active_at = None
                if last_login_raw:
                    try:
                        last_active_at = parse_timestamp(last_login_raw)
                    except (ValueError, TypeError):
                        pass

                activity_records.append({
                    "user_id": user.get("id"),
                    "email": email,
                    "full_name": display_name,
                    "last_active_at": last_active_at,
                    "is_admin": bool(email and email.lower() in admin_upns),
                    "suspended": not user.get("accountEnabled", True),
                })
            return activity_records
        except (ExternalAPIError, httpx.HTTPError) as e:
            logger.error("m365_list_users_failed", error=str(e))
            return []

    async def _revoke_github(self, resource_id: str) -> bool:
        """
        Remove user from GitHub organization.
        """
        token = self._resolve_api_key()
        org = self._connector_config.get("github_org")
        if not org:
            logger.warning("github_revoke_failed_no_org", user_id=resource_id)
            return False

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        url = f"https://api.github.com/orgs/{org}/memberships/{resource_id}"
        
        try:
            from app.shared.core.http import get_http_client
            client = get_http_client()
            response = await client.delete(url, headers=headers)
            
            if response.status_code == 204:
                logger.info("github_membership_revoked", user_id=resource_id, org=org)
                return True
            else:
                logger.warning("github_membership_revoke_failed", user_id=resource_id, status=response.status_code)
                return False
        except (ExternalAPIError, httpx.HTTPError) as e:
            logger.error("github_membership_revoke_error", user_id=resource_id, error=str(e))
            return False

    async def _list_github_activity(self) -> list[dict[str, Any]]:
        """
        List GitHub org members and estimate activity via Org Events API.
        """
        token = self._resolve_api_key()
        org = self._connector_config.get("github_org")
        if not org:
            return []

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

        try:
            # 1. Fetch Org Members
            members_url = f"https://api.github.com/orgs/{org}/members"
            members_payload = await self._get_json(members_url, headers=headers)
            members = members_payload.get("value", members_payload.get("members", []))
            if not isinstance(members, list):
                members = []

            # 2. Fetch recent Org Events to find last activity for these members
            # This is a high-fidelity fallback for the Audit Log API (Enterprise only)
            events_url = f"https://api.github.com/orgs/{org}/events?per_page=100"
            events_payload = await self._get_json(events_url, headers=headers)
            events = events_payload.get("value", events_payload.get("events", []))
            if not isinstance(events, list):
                events = []

            last_event_per_user: dict[str, datetime] = {}  # login -> timestamp
            for event in events:
                if not isinstance(event, dict):
                    continue
                actor = event.get("actor")
                login = actor.get("login") if isinstance(actor, dict) else None
                created_at = event.get("created_at")
                if login and created_at:
                    try:
                        ts = parse_timestamp(created_at)
                    except (ValueError, TypeError):
                        continue
                    if login not in last_event_per_user or ts > last_event_per_user[login]:
                        last_event_per_user[login] = ts

            activity_records = []
            for member in members:
                if not isinstance(member, dict):
                    continue
                login = str(member.get("login") or "").strip()
                if not login:
                    continue
                activity_records.append({
                    "user_id": login,
                    "email": login,
                    "full_name": member.get("name") or login,
                    "last_active_at": last_event_per_user.get(login),
                    "is_admin": member.get("site_admin", False),
                    "suspended": False,
                })
            return activity_records
        except (ExternalAPIError, httpx.HTTPError) as e:
            logger.error("github_list_members_failed", error=str(e))
            return []

    async def _revoke_zoom(self, resource_id: str) -> bool:
        """
        Disassociate user from Zoom account.
        """
        token = self._resolve_api_key()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://api.zoom.us/v2/users/{resource_id}?action=disassociate"
        
        try:
            from app.shared.core.http import get_http_client
            client = get_http_client()
            response = await client.delete(url, headers=headers)
            
            if response.status_code == 204:
                logger.info("zoom_user_disassociated", user_id=resource_id)
                return True
            else:
                logger.warning("zoom_user_disassociate_failed", user_id=resource_id, status=response.status_code)
                return False
        except (ExternalAPIError, httpx.HTTPError) as e:
            logger.error("zoom_user_disassociate_error", user_id=resource_id, error=str(e))
            return False

    async def _list_zoom_activity(self) -> list[dict[str, Any]]:
        """
        List Zoom users and their last login time.
        """
        token = self._resolve_api_key()
        headers = {"Authorization": f"Bearer {token}"}
        url = "https://api.zoom.us/v2/users"

        try:
            payload = await self._get_json(url, headers=headers)
            users_list = payload.get("users", [])

            activity_records = []
            for user in users_list:
                last_login_raw = user.get("last_login_time")
                last_active_at = None
                if last_login_raw:
                    try:
                        last_active_at = parse_timestamp(last_login_raw)
                    except (ValueError, TypeError):
                        pass
                
                activity_records.append({
                    "user_id": user.get("id"),
                    "email": user.get("email"),
                    "full_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
                    "last_active_at": last_active_at,
                    "is_admin": user.get("role_name") == "Owner",
                    "suspended": user.get("status") == "inactive",
                })
            return activity_records
        except (ExternalAPIError, httpx.HTTPError) as e:
            logger.error("zoom_list_users_failed", error=str(e))
            return []

    async def _revoke_slack(self, resource_id: str) -> bool:
        """
        Deactivate user in Slack.
        """
        token = self._resolve_api_key()
        # admin.users.remove requires Enterprise Grid
        url = "https://slack.com/api/admin.users.remove"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        team_id = self._connector_config.get("slack_team_id")
        if not team_id:
            logger.warning("slack_revoke_failed_no_team_id", user_id=resource_id)
            return False
        
        payload = {
            "team_id": team_id,
            "user_id": resource_id,
        }

        try:
            from app.shared.core.http import get_http_client
            client = get_http_client()
            # method is POST for admin.users.remove
            response = await client.post(url, headers=headers, json=payload)
            data = response.json()
            
            if data.get("ok"):
                logger.info("slack_user_deactivated", user_id=resource_id)
                return True
            else:
                logger.warning("slack_user_deactivation_failed", user_id=resource_id, error=data.get("error"))
                return False
        except (ExternalAPIError, httpx.HTTPError) as e:
            logger.error("slack_user_deactivation_error", user_id=resource_id, error=str(e))
            return False

    async def _list_slack_activity(self) -> list[dict[str, Any]]:
        """
        List Slack access logs to determine activity.
        """
        token = self._resolve_api_key()
        headers = {"Authorization": f"Bearer {token}"}
        url = "https://slack.com/api/team.accessLogs"
        
        try:
            # Requires paid plan. We'll parse the logs to find last activity per user.
            payload = await self._get_json(url, headers=headers)
            if not payload.get("ok"):
                logger.warning("slack_activity_fetch_failed", error=payload.get("error"))
                return []

            logs = payload.get("logins", [])
            user_activity: dict[str, int] = {}  # user_id -> last_timestamp

            for log in logs:
                uid = log.get("user_id")
                ts = log.get("date_last")
                if uid and ts:
                    user_activity[uid] = max(user_activity.get(uid, 0), ts)
            
            activity_records = []
            # We also need to list users to get their metadata
            users_url = "https://slack.com/api/users.list"
            users_payload = await self._get_json(users_url, headers=headers)
            for user in users_payload.get("members", []):
                uid = user.get("id")
                last_ts = user_activity.get(uid)
                last_active_at = datetime.fromtimestamp(last_ts, tz=timezone.utc) if last_ts else None
                
                activity_records.append({
                    "user_id": uid,
                    "email": user.get("profile", {}).get("email"),
                    "full_name": user.get("real_name") or user.get("name"),
                    "last_active_at": last_active_at,
                    "is_admin": user.get("is_admin", False),
                    "suspended": user.get("deleted", False),
                })
            return activity_records
        except (ExternalAPIError, httpx.HTTPError) as e:
            logger.error("slack_list_activity_failed", error=str(e))
            return []

    async def _revoke_salesforce(self, resource_id: str) -> bool:
        """
        Deactivate user in Salesforce.
        """
        token = self._resolve_api_key()
        try:
            instance_url = self._salesforce_instance_url()
        except ExternalAPIError:
            logger.warning("salesforce_revoke_failed_no_url", user_id=resource_id)
            return False
        api_version = self._connector_config.get("salesforce_api_version", "v60.0")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        url = f"{instance_url}/services/data/{api_version}/sobjects/User/{resource_id}"
        
        try:
            from app.shared.core.http import get_http_client
            client = get_http_client()
            # use PATCH to update IsActive
            response = await client.patch(url, headers=headers, json={"IsActive": False})
            
            if response.status_code == 204:
                logger.info("salesforce_user_deactivated", user_id=resource_id)
                return True
            else:
                logger.warning("salesforce_user_deactivation_failed", user_id=resource_id, status=response.status_code)
                return False
        except (ExternalAPIError, httpx.HTTPError) as e:
            logger.error("salesforce_user_deactivation_error", user_id=resource_id, error=str(e))
            return False

    async def _list_salesforce_activity(self) -> list[dict[str, Any]]:
        """
        List Salesforce users and their last login date.
        """
        token = self._resolve_api_key()
        try:
            instance_url = self._salesforce_instance_url()
        except ExternalAPIError:
            return []
        api_version = self._connector_config.get("salesforce_api_version", "v60.0")

        headers = {"Authorization": f"Bearer {token}"}
        query = "SELECT+Id,Email,Name,LastLoginDate,IsActive,Profile.Name+FROM+User"
        url = f"{instance_url}/services/data/{api_version}/query?q={query}"
        
        try:
            payload = await self._get_json(url, headers=headers)
            records = payload.get("records", [])
            
            activity_records = []
            for user in records:
                last_login_raw = user.get("LastLoginDate")
                last_active_at = None
                if last_login_raw:
                    try:
                        last_active_at = parse_timestamp(last_login_raw)
                    except (ValueError, TypeError):
                        pass
                
                activity_records.append({
                    "user_id": user.get("Id"),
                    "email": user.get("Email"),
                    "full_name": user.get("Name"),
                    "last_active_at": last_active_at,
                    "is_admin": (user.get("Profile", {}) or {}).get("Name") == "System Administrator",
                    "suspended": not user.get("IsActive", True)
                })
            return activity_records
        except (ExternalAPIError, httpx.HTTPError) as e:
            logger.error("salesforce_list_users_failed", error=str(e))
            return []

    async def _list_google_workspace_activity(self) -> list[dict[str, Any]]:

        token = self._resolve_api_key()
        headers = {"Authorization": f"Bearer {token}"}
        
        # GET https://admin.googleapis.com/admin/directory/v1/users?customer=my_customer&viewType=admin_view
        url = "https://admin.googleapis.com/admin/directory/v1/users?customer=my_customer"
        
        try:
            payload = await self._get_json(url, headers=headers)
            users_list = payload.get("users", [])
            
            activity_records = []
            for user in users_list:
                primary_email = user.get("primaryEmail")
                last_login_raw = user.get("lastLoginTime")
                
                # Format: "2024-02-19T06:41:24.000Z"
                last_active_at = None
                if last_login_raw:
                    try:
                        last_active_at = parse_timestamp(last_login_raw)
                    except (ValueError, TypeError):
                        pass
                
                activity_records.append({
                    "user_id": primary_email,
                    "email": primary_email,
                    "full_name": user.get("name", {}).get("fullName"),
                    "last_active_at": last_active_at,
                    "is_admin": user.get("isAdmin", False),
                    "suspended": user.get("suspended", False),
                    "creation_time": user.get("creationTime"),
                })
            return activity_records
        except (ExternalAPIError, httpx.HTTPError) as e:
            logger.error("google_workspace_list_users_failed", error=str(e))
            return []

    async def discover_resources(
        self, resource_type: str, region: str | None = None
    ) -> list[dict[str, Any]]:
        return []

    async def get_resource_usage(
        self, _service_name: str, _resource_id: str | None = None
    ) -> list[dict[str, Any]]:
        # License resource-level usage is not exposed by this adapter yet.
        return []
