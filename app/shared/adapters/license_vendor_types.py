from __future__ import annotations

from typing import Any, Protocol


class LicenseVendorRuntime(Protocol):
    def _resolve_api_key(self) -> str: ...

    @property
    def _connector_config(self) -> dict[str, Any]: ...

    @property
    def _vendor(self) -> str: ...

    async def _get_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def _salesforce_instance_url(self) -> str: ...
