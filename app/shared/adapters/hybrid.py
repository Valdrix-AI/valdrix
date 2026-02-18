from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from urllib.parse import urljoin

import httpx
import structlog

from app.shared.adapters.base import BaseAdapter
from app.shared.adapters.feed_utils import as_float, is_number, parse_timestamp
from app.shared.core.credentials import HybridCredentials
from app.shared.core.currency import convert_to_usd
from app.shared.core.exceptions import ExternalAPIError

logger = structlog.get_logger()

_NATIVE_TIMEOUT_SECONDS = 20.0
_NATIVE_MAX_RETRIES = 3
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_LEDGER_HTTP_VENDOR_ALIASES = {
    "ledger_http",
    "cmdb_ledger",
    "cmdb-ledger",
    "ledger",
}
_OPENSTACK_VENDOR_ALIASES = {"openstack", "cloudkitty"}
_VMWARE_VENDOR_ALIASES = {"vmware", "vcenter", "vsphere"}


class HybridAdapter(BaseAdapter):
    """
    Cloud+ adapter for private/hybrid infrastructure spend (on-prem, colo, private cloud).

    v1 is feed-based (manual/csv). Vendor-native pulls can be layered later for
    systems like VMware/VCF, OpenStack, or CMDB-backed ledgers.
    """

    def __init__(self, credentials: HybridCredentials):
        self.credentials = credentials
        self.last_error = None

    @property
    def _auth_method(self) -> str:
        return self.credentials.auth_method.strip().lower()

    @property
    def _vendor(self) -> str:
        return self.credentials.vendor.strip().lower()

    @property
    def _connector_config(self) -> dict[str, Any]:
        return self.credentials.connector_config

    @property
    def _native_vendor(self) -> str | None:
        if self._auth_method not in {"api_key"}:
            return None
        if self._vendor in _LEDGER_HTTP_VENDOR_ALIASES:
            return "ledger_http"
        if self._vendor in _OPENSTACK_VENDOR_ALIASES:
            return "cloudkitty"
        if self._vendor in _VMWARE_VENDOR_ALIASES:
            return "vmware"
        return None

    def _resolve_api_key(self) -> str:
        token = self.credentials.api_key
        if not token:
            raise ExternalAPIError("Missing API token for hybrid native connector")
        return token.get_secret_value().strip()

    def _resolve_api_secret(self) -> str:
        token = self.credentials.api_secret
        if not token:
            raise ExternalAPIError("Missing API secret for hybrid native connector")
        return token.get_secret_value().strip()

    def _iter_month_starts(
        self, start_date: datetime, end_date: datetime
    ) -> list[date]:
        start_day = start_date.date()
        end_day = end_date.date()
        current = date(start_day.year, start_day.month, 1)
        months: list[date] = []
        while current <= end_day:
            months.append(current)
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)
        return months

    def _resolve_openstack_auth_url(self) -> str:
        raw = self._connector_config.get("auth_url")
        if not isinstance(raw, str) or not raw.strip():
            raise ExternalAPIError("OpenStack connector_config.auth_url is required")
        auth_url = raw.strip().rstrip("/")
        if not auth_url.startswith(("https://", "http://")):
            raise ExternalAPIError(
                "OpenStack connector_config.auth_url must be an http(s) URL"
            )
        if auth_url.endswith("/v3/auth/tokens"):
            return auth_url
        if auth_url.endswith("/v3"):
            return f"{auth_url}/auth/tokens"
        return f"{auth_url}/v3/auth/tokens"

    def _resolve_cloudkitty_base_url(self) -> str:
        raw = self._connector_config.get(
            "cloudkitty_base_url"
        ) or self._connector_config.get("base_url")
        if not isinstance(raw, str) or not raw.strip():
            raise ExternalAPIError(
                "OpenStack connector_config.cloudkitty_base_url is required"
            )
        base_url = raw.strip().rstrip("/")
        if not base_url.startswith(("https://", "http://")):
            raise ExternalAPIError(
                "OpenStack connector_config.cloudkitty_base_url must be an http(s) URL"
            )
        return base_url

    def _resolve_vmware_base_url(self) -> str:
        raw = self._connector_config.get("base_url")
        if not isinstance(raw, str) or not raw.strip():
            raise ExternalAPIError("VMware connector_config.base_url is required")
        base_url = raw.strip().rstrip("/")
        if not base_url.startswith(("https://", "http://")):
            raise ExternalAPIError(
                "VMware connector_config.base_url must be an http(s) URL"
            )
        return base_url

    def _resolve_vmware_pricing(self) -> tuple[float, float]:
        cpu_hour_usd = self._connector_config.get("cpu_hour_usd")
        ram_gb_hour_usd = self._connector_config.get("ram_gb_hour_usd")
        if not isinstance(cpu_hour_usd, (int, float)) or cpu_hour_usd <= 0:
            raise ExternalAPIError(
                "VMware connector_config.cpu_hour_usd must be a positive number"
            )
        if not isinstance(ram_gb_hour_usd, (int, float)) or ram_gb_hour_usd <= 0:
            raise ExternalAPIError(
                "VMware connector_config.ram_gb_hour_usd must be a positive number"
            )
        return float(cpu_hour_usd), float(ram_gb_hour_usd)

    def _resolve_verify_ssl(self) -> bool:
        raw = self._connector_config.get("verify_ssl")
        if isinstance(raw, bool):
            return raw
        raw = self._connector_config.get("ssl_verify")
        if isinstance(raw, bool):
            return raw
        return True

    async def verify_connection(self) -> bool:
        self.last_error = None
        native_vendor = self._native_vendor
        if self._auth_method == "api_key" and native_vendor is None:
            supported = ", ".join(sorted(_LEDGER_HTTP_VENDOR_ALIASES))
            self._last_error = (
                f"Native Hybrid auth is not supported for vendor '{self._vendor}'. "
                f"Supported vendors: {supported}, openstack/cloudkitty, vmware/vcenter. "
                "Use auth_method manual/csv for custom vendors."
            )
            return False
        if self._auth_method not in {"manual", "csv", "api_key"}:
            self._last_error = (
                "Hybrid connector auth_method must be one of: manual, csv, api_key "
                f"(got '{self._auth_method}')."
            )
            return False

        if native_vendor == "ledger_http":
            try:
                await self._verify_ledger_http()
                return True
            except ExternalAPIError as exc:
                self.last_error = str(exc)
                logger.warning(
                    "hybrid_native_verify_failed",
                    vendor=native_vendor,
                    error=str(exc),
                )
                return False

        if native_vendor == "cloudkitty":
            try:
                await self._verify_cloudkitty()
                return True
            except ExternalAPIError as exc:
                self.last_error = str(exc)
                logger.warning(
                    "hybrid_native_verify_failed", vendor=native_vendor, error=str(exc)
                )
                return False

        if native_vendor == "vmware":
            try:
                await self._verify_vmware()
                return True
            except ExternalAPIError as exc:
                self.last_error = str(exc)
                logger.warning(
                    "hybrid_native_verify_failed", vendor=native_vendor, error=str(exc)
                )
                return False

        feed = self.credentials.spend_feed
        is_valid = self._validate_manual_feed(feed)
        if not is_valid and self._last_error is None:
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
            if not is_number(amount):
                self._last_error = f"Spend feed entry #{idx + 1} must include numeric cost_usd or amount_usd."
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
        if native_vendor == "ledger_http":
            try:
                async for row in self._stream_ledger_http_cost_and_usage(
                    start_date, end_date
                ):
                    yield row
                return
            except ExternalAPIError as exc:
                self.last_error = str(exc)
                logger.warning(
                    "hybrid_native_stream_failed_fallback_to_feed",
                    vendor=native_vendor,
                    error=str(exc),
                )

        if native_vendor == "cloudkitty":
            try:
                async for row in self._stream_cloudkitty_cost_and_usage(
                    start_date, end_date
                ):
                    yield row
                return
            except ExternalAPIError as exc:
                self.last_error = str(exc)
                logger.warning(
                    "hybrid_native_stream_failed_fallback_to_feed",
                    vendor=native_vendor,
                    error=str(exc),
                )

        if native_vendor == "vmware":
            try:
                async for row in self._stream_vmware_cost_and_usage(
                    start_date, end_date
                ):
                    yield row
                return
            except ExternalAPIError as exc:
                self.last_error = str(exc)
                logger.warning(
                    "hybrid_native_stream_failed_fallback_to_feed",
                    vendor=native_vendor,
                    error=str(exc),
                )

        feed = self.credentials.spend_feed
        if not isinstance(feed, list):
            return

        for entry in feed:
            timestamp = parse_timestamp(entry.get("timestamp") or entry.get("date"))
            if timestamp < start_date or timestamp > end_date:
                continue
            service_name = str(
                entry.get("service")
                or entry.get("system")
                or entry.get("vendor")
                or "Hybrid Infra"
            )
            usage_type = str(entry.get("usage_type") or "infrastructure")
            region = str(entry.get("region") or entry.get("location") or "global")
            cost_value = entry.get("cost_usd", entry.get("amount_usd", 0.0))
            try:
                cost_usd = float(cost_value or 0.0)
            except (TypeError, ValueError):
                cost_usd = 0.0

            yield {
                "provider": "hybrid",
                "service": service_name,
                "region": region,
                "usage_type": usage_type,
                "cost_usd": cost_usd,
                "amount_raw": entry.get("amount_raw"),
                "currency": str(entry.get("currency") or "USD").upper(),
                "timestamp": timestamp,
                "source_adapter": "hybrid_feed",
                "tags": entry.get("tags")
                if isinstance(entry.get("tags"), dict)
                else {},
            }

    async def _get_openstack_token(self) -> str:
        app_cred_id = self._resolve_api_key()
        app_cred_secret = self._resolve_api_secret()
        auth_url = self._resolve_openstack_auth_url()

        body = {
            "auth": {
                "identity": {
                    "methods": ["application_credential"],
                    "application_credential": {
                        "id": app_cred_id,
                        "secret": app_cred_secret,
                    },
                }
            }
        }
        from app.shared.core.http import get_http_client

        client = get_http_client(
            timeout=_NATIVE_TIMEOUT_SECONDS, verify=self._resolve_verify_ssl()
        )
        response = await client.post(auth_url, json=body)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ExternalAPIError(
                f"OpenStack Keystone token request failed: {exc}"
            ) from exc
        token = response.headers.get("X-Subject-Token")
        if not isinstance(token, str) or not token.strip():
            raise ExternalAPIError(
                "OpenStack Keystone response missing X-Subject-Token"
            )
        return token.strip()

    def _extract_cloudkitty_summary_rows(self, payload: object) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            raise ExternalAPIError("CloudKitty summary returned invalid payload shape")
        results = payload.get("results")
        if not isinstance(results, list):
            raise ExternalAPIError("CloudKitty summary payload missing results list")
        rows: list[dict[str, Any]] = []
        for entry in results:
            if not isinstance(entry, dict):
                continue
            desc = entry.get("desc")
            if not isinstance(desc, list) or len(desc) < 1:
                continue
            begin = desc[0]
            end = desc[1] if len(desc) > 1 else None
            qty = entry.get("qty")
            rate = entry.get("rate")
            if not is_number(rate):
                continue
            rows.append({"begin": begin, "end": end, "qty": qty, "rate": rate})
        if not rows:
            return []
        return rows

    async def _verify_cloudkitty(self) -> None:
        token = await self._get_openstack_token()
        base_url = self._resolve_cloudkitty_base_url()
        endpoint = urljoin(base_url.rstrip("/") + "/", "v2/summary")

        now = datetime.now(timezone.utc)
        begin = (now - timedelta(days=1)).replace(microsecond=0)
        end = now.replace(microsecond=0)
        payload = await self._get_json(
            endpoint,
            headers={"X-Auth-Token": token},
            params={
                "begin": begin.isoformat(),
                "end": end.isoformat(),
                "groupby": "day",
            },
        )
        self._extract_cloudkitty_summary_rows(payload)

    async def _stream_cloudkitty_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> AsyncGenerator[dict[str, Any], None]:
        token = await self._get_openstack_token()
        base_url = self._resolve_cloudkitty_base_url()
        endpoint = urljoin(base_url.rstrip("/") + "/", "v2/summary")
        currency_code = str(self._connector_config.get("currency") or "USD").upper()
        groupby = str(self._connector_config.get("groupby") or "month")

        payload = await self._get_json(
            endpoint,
            headers={"X-Auth-Token": token},
            params={
                "begin": start_date.isoformat(),
                "end": end_date.isoformat(),
                "groupby": groupby,
            },
        )
        rows = self._extract_cloudkitty_summary_rows(payload)
        for entry in rows:
            timestamp = parse_timestamp(entry.get("begin"))
            rate = as_float(entry.get("rate"))
            qty = (
                as_float(entry.get("qty"), default=0.0)
                if is_number(entry.get("qty"))
                else None
            )

            cost_usd = float(rate)
            if currency_code != "USD":
                try:
                    cost_usd = float(await convert_to_usd(rate, currency_code))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "hybrid_cloudkitty_currency_conversion_failed",
                        currency=currency_code,
                        error=str(exc),
                    )

            yield {
                "provider": "hybrid",
                "service": "OpenStack CloudKitty",
                "region": str(self._connector_config.get("location") or "global"),
                "usage_type": "rated_usage",
                "resource_id": None,
                "usage_amount": float(qty) if qty is not None else None,
                "usage_unit": "unit",
                "cost_usd": cost_usd,
                "amount_raw": float(rate),
                "currency": currency_code,
                "timestamp": timestamp,
                "source_adapter": "hybrid_openstack_cloudkitty",
                "tags": {
                    "vendor": "openstack",
                    "groupby": groupby,
                    "period_end": str(entry.get("end") or ""),
                },
            }

    async def _verify_vmware(self) -> None:
        session_id = await self._get_vmware_session_id()
        base_url = self._resolve_vmware_base_url()
        endpoint = urljoin(base_url.rstrip("/") + "/", "rest/vcenter/vm")
        payload = await self._get_json(
            endpoint,
            headers={"vmware-api-session-id": session_id},
            params={"_fields": "name,cpu_count,memory_size_MiB,power_state"},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
            raise ExternalAPIError(
                "VMware vCenter VM list returned invalid payload shape"
            )
        self._resolve_vmware_pricing()

    async def _get_vmware_session_id(self) -> str:
        username = self._resolve_api_key()
        password = self._resolve_api_secret()
        base_url = self._resolve_vmware_base_url()
        endpoint = urljoin(base_url.rstrip("/") + "/", "rest/com/vmware/cis/session")

        from app.shared.core.http import get_http_client

        client = get_http_client(
            timeout=_NATIVE_TIMEOUT_SECONDS, verify=self._resolve_verify_ssl()
        )
        response = await client.post(endpoint, auth=(username, password))
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ExternalAPIError(
                f"VMware vCenter session creation failed: {exc}"
            ) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalAPIError(
                "VMware vCenter session creation returned invalid JSON"
            ) from exc
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("value"), str)
            or not payload.get("value")
        ):
            raise ExternalAPIError("VMware vCenter session creation missing session id")
        return str(payload["value"])

    async def _stream_vmware_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> AsyncGenerator[dict[str, Any], None]:
        session_id = await self._get_vmware_session_id()
        base_url = self._resolve_vmware_base_url()
        cpu_hour_usd, ram_gb_hour_usd = self._resolve_vmware_pricing()
        include_powered_off = bool(
            self._connector_config.get("include_powered_off", False)
        )
        location = str(self._connector_config.get("location") or "global")

        endpoint = urljoin(base_url.rstrip("/") + "/", "rest/vcenter/vm")
        payload = await self._get_json(
            endpoint,
            headers={"vmware-api-session-id": session_id},
            params={"_fields": "name,cpu_count,memory_size_MiB,power_state"},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
            raise ExternalAPIError(
                "VMware vCenter VM list returned invalid payload shape"
            )
        vms: list[dict[str, Any]] = [
            vm for vm in payload["value"] if isinstance(vm, dict)
        ]

        # Estimate daily amortized cost using current VM inventory + user-provided unit rates.
        cost_per_day = 0.0
        vm_count = 0
        for vm in vms:
            power_state = str(vm.get("power_state") or "").upper()
            if not include_powered_off and power_state and power_state != "POWERED_ON":
                continue
            cpu_count = as_float(vm.get("cpu_count"), default=0.0)
            mem_mib = as_float(vm.get("memory_size_MiB"), default=0.0)
            mem_gb = mem_mib / 1024.0
            if cpu_count <= 0 and mem_gb <= 0:
                continue
            vm_count += 1
            hourly = (cpu_count * cpu_hour_usd) + (mem_gb * ram_gb_hour_usd)
            cost_per_day += hourly * 24.0

        start_day = start_date.date()
        end_day = end_date.date()
        current = start_day
        while current <= end_day:
            timestamp = datetime.combine(current, time.min, tzinfo=timezone.utc)
            yield {
                "provider": "hybrid",
                "service": "VMware vCenter (estimated)",
                "region": location,
                "usage_type": "infrastructure_estimate",
                "resource_id": None,
                "usage_amount": float(vm_count),
                "usage_unit": "vm",
                "cost_usd": float(cost_per_day),
                "amount_raw": float(cost_per_day),
                "currency": "USD",
                "timestamp": timestamp,
                "source_adapter": "hybrid_vmware_vcenter",
                "tags": {
                    "vendor": "vmware",
                    "estimated": True,
                    "include_powered_off": include_powered_off,
                },
            }
            current = current.fromordinal(current.toordinal() + 1)

    def _resolve_ledger_http_base_url(self) -> str:
        base_url = self._connector_config.get("base_url")
        if not isinstance(base_url, str) or not base_url.strip():
            raise ExternalAPIError(
                "Missing connector_config.base_url for hybrid ledger HTTP connector"
            )
        base_url = base_url.strip()
        if not base_url.startswith(("https://", "http://")):
            raise ExternalAPIError("connector_config.base_url must be an http(s) URL")
        return base_url

    def _resolve_ledger_http_costs_path(self) -> str:
        path = (
            self._connector_config.get("costs_path")
            or self._connector_config.get("path")
            or "/api/v1/finops/costs"
        )
        if not isinstance(path, str) or not path.strip():
            return "/api/v1/finops/costs"
        normalized = "/" + path.strip().lstrip("/")
        return normalized

    def _resolve_ledger_http_headers(self) -> dict[str, str]:
        token = self._resolve_api_key()
        header_name = self._connector_config.get("api_key_header")
        if isinstance(header_name, str) and header_name.strip():
            return {header_name.strip(): token}
        return {"Authorization": f"Bearer {token}"}

    async def _verify_ledger_http(self) -> None:
        base_url = self._resolve_ledger_http_base_url()
        endpoint = urljoin(
            base_url.rstrip("/") + "/",
            self._resolve_ledger_http_costs_path().lstrip("/"),
        )
        headers = self._resolve_ledger_http_headers()
        payload = await self._get_json(endpoint, headers=headers, params={"limit": 1})
        self._extract_ledger_records(payload)

    async def _stream_ledger_http_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> AsyncGenerator[dict[str, Any], None]:
        base_url = self._resolve_ledger_http_base_url()
        endpoint = urljoin(
            base_url.rstrip("/") + "/",
            self._resolve_ledger_http_costs_path().lstrip("/"),
        )
        headers = self._resolve_ledger_http_headers()
        start_param = self._connector_config.get("start_param") or "start_date"
        end_param = self._connector_config.get("end_param") or "end_date"
        params = {
            str(start_param): start_date.date().isoformat(),
            str(end_param): end_date.date().isoformat(),
        }
        payload = await self._get_json(endpoint, headers=headers, params=params)
        records = self._extract_ledger_records(payload)

        for entry in records:
            timestamp = parse_timestamp(entry.get("timestamp") or entry.get("date"))
            if timestamp < start_date or timestamp > end_date:
                continue

            service_name = str(
                entry.get("service")
                or entry.get("system")
                or entry.get("vendor")
                or self._vendor
                or "Hybrid Infra"
            )
            usage_type = str(entry.get("usage_type") or "infrastructure")
            region = str(entry.get("region") or entry.get("location") or "global")

            currency_code = str(entry.get("currency") or "USD").upper()
            cost_usd: float
            amount_raw: float | None = None

            cost_candidate = entry.get("cost_usd", entry.get("amount_usd"))
            if is_number(cost_candidate):
                cost_usd = as_float(cost_candidate)
                amount_raw = (
                    as_float(entry.get("amount_raw"), default=cost_usd)
                    if entry.get("amount_raw") is not None
                    else None
                )
            else:
                amount_local = as_float(
                    entry.get(
                        "amount_raw", entry.get("amount", entry.get("cost", 0.0))
                    ),
                    default=0.0,
                )
                amount_raw = amount_local
                cost_usd = float(amount_local)
                if currency_code != "USD":
                    try:
                        cost_usd = float(
                            await convert_to_usd(amount_local, currency_code)
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "hybrid_ledger_currency_conversion_failed",
                            currency=currency_code,
                            error=str(exc),
                        )

            resource_id_raw = entry.get("resource_id") or entry.get("id")
            resource_id = (
                str(resource_id_raw).strip()
                if resource_id_raw not in (None, "")
                else None
            )
            usage_amount = (
                as_float(entry.get("usage_amount"), default=0.0)
                if is_number(entry.get("usage_amount"))
                else None
            )
            usage_unit_raw = entry.get("usage_unit")
            usage_unit = (
                str(usage_unit_raw).strip()
                if usage_unit_raw not in (None, "")
                else None
            )
            tags = entry.get("tags") if isinstance(entry.get("tags"), dict) else {}

            yield {
                "provider": "hybrid",
                "service": service_name,
                "region": region,
                "usage_type": usage_type,
                "resource_id": resource_id,
                "usage_amount": usage_amount,
                "usage_unit": usage_unit,
                "cost_usd": cost_usd,
                "amount_raw": amount_raw,
                "currency": currency_code,
                "timestamp": timestamp,
                "source_adapter": "hybrid_ledger_http",
                "tags": tags,
            }

    def _extract_ledger_records(self, payload: object) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [entry for entry in payload if isinstance(entry, dict)]
        if isinstance(payload, dict):
            records = (
                payload.get("records")
                or payload.get("data")
                or payload.get("items")
                or []
            )
            if records is None:
                records = []
            if not isinstance(records, list):
                raise ExternalAPIError(
                    "Hybrid ledger HTTP payload is missing a list of records"
                )
            return [entry for entry in records if isinstance(entry, dict)]
        raise ExternalAPIError(
            "Hybrid ledger HTTP connector returned invalid payload shape"
        )

    async def _get_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
    ) -> object:
        last_error: Exception | None = None
        for attempt in range(1, _NATIVE_MAX_RETRIES + 1):
            try:
                from app.shared.core.http import get_http_client

                client = get_http_client(
                    timeout=_NATIVE_TIMEOUT_SECONDS, verify=self._resolve_verify_ssl()
                )
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code
                retryable = status_code in _RETRYABLE_STATUS_CODES
                if retryable and attempt < _NATIVE_MAX_RETRIES:
                    logger.warning(
                        "hybrid_native_retry_http_status",
                        attempt=attempt,
                        max_attempts=_NATIVE_MAX_RETRIES,
                        status_code=status_code,
                        url=url,
                    )
                    await asyncio.sleep(0.05 * attempt)
                    continue
                raise ExternalAPIError(
                    f"Hybrid request failed with status {status_code}: {exc}"
                ) from exc
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt < _NATIVE_MAX_RETRIES:
                    logger.warning(
                        "hybrid_native_retry_transport_error",
                        attempt=attempt,
                        max_attempts=_NATIVE_MAX_RETRIES,
                        url=url,
                        error=str(exc),
                    )
                    await asyncio.sleep(0.05 * attempt)
                    continue
                raise ExternalAPIError(f"Hybrid request failed: {exc}") from exc
            except ValueError as exc:
                raise ExternalAPIError(
                    "Hybrid request returned invalid JSON payload"
                ) from exc

        if last_error is not None:
            raise ExternalAPIError(
                f"Hybrid request failed: {last_error}"
            ) from last_error
        raise ExternalAPIError("Hybrid request failed unexpectedly")

    async def discover_resources(
        self, resource_type: str, region: str | None = None
    ) -> list[dict[str, Any]]:
        return []
