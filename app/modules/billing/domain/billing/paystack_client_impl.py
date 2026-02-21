"""Paystack API client implementation."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from . import paystack_shared as shared


class PaystackClient:
    """Async wrapper for Paystack operations."""

    BASE_URL = "https://api.paystack.co"

    def __init__(self) -> None:
        if not shared.settings.PAYSTACK_SECRET_KEY:
            raise ValueError("PAYSTACK_SECRET_KEY not configured")

        self.headers: dict[str, str] = {
            "Authorization": f"Bearer {shared.settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from app.shared.core.http import get_http_client

        client = get_http_client()
        try:
            response = await client.request(
                method,
                f"{self.BASE_URL}/{endpoint}",
                headers=self.headers,
                json=data,
                timeout=30.0,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Invalid Paystack response payload type")
            return payload
        except httpx.HTTPError as exc:
            shared.logger.error("paystack_api_error", endpoint=endpoint, error=str(exc))
            raise

    async def initialize_transaction(
        self,
        email: str,
        amount_kobo: int,
        plan_code: Optional[str],
        callback_url: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Initialize a transaction to start a subscription."""
        data: dict[str, Any] = {
            "email": email,
            "amount": amount_kobo,
            "callback_url": callback_url,
            "metadata": metadata,
        }
        if plan_code:
            data["plan"] = plan_code

        return await self._request("POST", "transaction/initialize", data)

    async def charge_authorization(
        self,
        email: str,
        amount_kobo: int,
        authorization_code: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Charge a stored authorization code (recurring billing)."""
        data = {
            "email": email,
            "amount": amount_kobo,
            "authorization_code": authorization_code,
            "metadata": metadata,
        }
        return await self._request("POST", "transaction/charge_authorization", data)

    async def verify_transaction(self, reference: str) -> dict[str, Any]:
        """Verify transaction status."""
        return await self._request("GET", f"transaction/verify/{reference}")

    async def fetch_subscription(self, code_or_token: str) -> dict[str, Any]:
        """Fetch subscription details."""
        return await self._request("GET", f"subscription/{code_or_token}")

    async def disable_subscription(self, code: str, token: str) -> dict[str, Any]:
        """Cancel a subscription."""
        data = {"code": code, "token": token}
        return await self._request("POST", "subscription/disable", data)
