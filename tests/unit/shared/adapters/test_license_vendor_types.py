from __future__ import annotations

from typing import Any, cast

from app.shared.adapters.license_vendor_types import LicenseVendorRuntime


class _RuntimeStub:
    def _resolve_api_key(self) -> str:
        return "key"

    @property
    def _connector_config(self) -> dict[str, Any]:
        return {"region": "us"}

    @property
    def _vendor(self) -> str:
        return "example"

    async def _get_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {"url": url, "headers": headers, "params": params}

    def _salesforce_instance_url(self) -> str:
        return "https://example.salesforce.com"


def test_license_vendor_runtime_protocol_contract_shape() -> None:
    runtime = cast(LicenseVendorRuntime, _RuntimeStub())
    assert runtime._resolve_api_key() == "key"
    assert runtime._connector_config["region"] == "us"
    assert runtime._vendor == "example"
    assert runtime._salesforce_instance_url().startswith("https://")

