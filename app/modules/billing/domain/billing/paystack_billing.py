"""
Paystack Billing Integration - Production Ready (Nigeria Support)

Implements subscription-based billing using Paystack.

Features:
- Subscription management via Paystack Plans
- Transaction initialization (Checkout)
- Webhook signature verification
- Subscription status tracking

Requirements:
- httpx (for async API calls)
- PAYSTACK_SECRET_KEY env var
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Optional
from uuid import UUID
import httpx
import structlog
from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pricing import TenantSubscription
from app.shared.core.config import get_settings
from app.shared.core.pricing import PricingTier
from app.shared.core.security import encrypt_string, decrypt_string

logger = structlog.get_logger()


class _SettingsProxy:
    """Lazy settings accessor to avoid stale module-level configuration."""

    def __getattr__(self, name: str) -> Any:
        return getattr(get_settings(), name)


settings: Any = _SettingsProxy()
PAYSTACK_CHECKOUT_CURRENCY = "NGN"
PAYSTACK_FX_PROVIDER = "cbn_nfem"
PAYSTACK_USD_FX_PROVIDER = "native_usd"

__all__ = [
    "TenantSubscription",
    "SubscriptionStatus",
    "BillingService",
    "WebhookHandler",
    "PaystackClient",
]


def _email_hash(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:12]


class SubscriptionStatus(str, Enum):
    """Paystack subscription statuses."""

    ACTIVE = "active"
    NON_RENEWING = "non-renewing"
    ATTENTION = "attention"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PaystackClient:
    """Async wrapper for Paystack operations."""

    BASE_URL = "https://api.paystack.co"

    def __init__(self) -> None:
        if not settings.PAYSTACK_SECRET_KEY:
            raise ValueError("PAYSTACK_SECRET_KEY not configured")

        self.headers: dict[str, str] = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
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
        except httpx.HTTPError as e:
            logger.error("paystack_api_error", endpoint=endpoint, error=str(e))
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
        data = {
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


class BillingService:
    """
    Paystack billing operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = PaystackClient()

        # Monthly plan codes
        self.plan_codes = {
            PricingTier.STARTER: settings.PAYSTACK_PLAN_STARTER,
            PricingTier.GROWTH: settings.PAYSTACK_PLAN_GROWTH,
            PricingTier.PRO: settings.PAYSTACK_PLAN_PRO,
            PricingTier.ENTERPRISE: settings.PAYSTACK_PLAN_ENTERPRISE,
        }

        # Annual plan codes (17% discount - 2 months free)
        self.annual_plan_codes = {
            PricingTier.STARTER: getattr(
                settings, "PAYSTACK_PLAN_STARTER_ANNUAL", None
            ),
            PricingTier.GROWTH: getattr(settings, "PAYSTACK_PLAN_GROWTH_ANNUAL", None),
            PricingTier.PRO: getattr(settings, "PAYSTACK_PLAN_PRO_ANNUAL", None),
            PricingTier.ENTERPRISE: getattr(
                settings, "PAYSTACK_PLAN_ENTERPRISE_ANNUAL", None
            ),
        }

        # Monthly amounts in Kobo (NGN x 100)
        from app.shared.core.pricing import TIER_CONFIG

        self.plan_amounts = {}
        self.annual_plan_amounts = {}

        for tier, config in TIER_CONFIG.items():
            kobo_config = config.get("paystack_amount_kobo")
            if tier == PricingTier.FREE and kobo_config is None:
                continue
            # Enterprise/custom tiers may not have fixed Paystack amounts.
            if kobo_config is None:
                logger.warning(
                    "paystack_amount_kobo_missing_for_tier",
                    tier=tier.value,
                )
                continue
            if not isinstance(kobo_config, dict):
                logger.warning(
                    "paystack_amount_kobo_invalid_for_tier",
                    tier=tier.value,
                    value_type=type(kobo_config).__name__,
                )
                continue
            monthly = kobo_config.get("monthly")
            annual = kobo_config.get("annual")
            if not isinstance(monthly, (int, float)) or not isinstance(
                annual, (int, float)
            ):
                logger.warning(
                    "paystack_amount_kobo_values_invalid_for_tier",
                    tier=tier.value,
                    monthly=monthly,
                    annual=annual,
                )
                continue
            self.plan_amounts[tier] = int(monthly)
            self.annual_plan_amounts[tier] = int(annual)

    def _resolve_checkout_currency(self, requested_currency: str | None) -> str:
        default_currency = str(
            getattr(
                settings, "PAYSTACK_DEFAULT_CHECKOUT_CURRENCY", PAYSTACK_CHECKOUT_CURRENCY
            )
            or PAYSTACK_CHECKOUT_CURRENCY
        ).strip().upper()
        if default_currency not in {"NGN", "USD"}:
            default_currency = PAYSTACK_CHECKOUT_CURRENCY

        resolved = (
            str(requested_currency).strip().upper()
            if isinstance(requested_currency, str) and requested_currency.strip()
            else default_currency
        )
        if resolved == "USD" and not bool(
            getattr(settings, "PAYSTACK_ENABLE_USD_CHECKOUT", False)
        ):
            raise ValueError("USD checkout is not enabled")
        if resolved not in {"NGN", "USD"}:
            raise ValueError(f"Unsupported checkout currency: {resolved}")
        return resolved

    @staticmethod
    def _parse_paystack_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    @staticmethod
    def _infer_interval_days(charge_data: dict[str, Any]) -> int:
        interval_raw: Any = None
        plan_data = charge_data.get("plan")
        if isinstance(plan_data, dict):
            interval_raw = plan_data.get("interval")
        if interval_raw is None:
            metadata = charge_data.get("metadata")
            if isinstance(metadata, dict):
                interval_raw = metadata.get("billing_cycle")

        interval = str(interval_raw or "").strip().lower()
        if interval in {"annual", "annually", "year", "yearly"}:
            return 365
        return 30

    async def _fetch_provider_next_payment_date(
        self, subscription: TenantSubscription
    ) -> datetime | None:
        code_raw = getattr(subscription, "paystack_subscription_code", None)
        if not isinstance(code_raw, str) or not code_raw.strip():
            return None

        try:
            provider_payload = await self.client.fetch_subscription(code_raw.strip())
        except Exception as exc:
            logger.warning(
                "renewal_fetch_subscription_failed",
                tenant_id=str(subscription.tenant_id),
                subscription_code=code_raw,
                error=str(exc),
            )
            return None

        if not isinstance(provider_payload, dict):
            return None
        data = provider_payload.get("data")
        if not isinstance(data, dict):
            return None

        return (
            self._parse_paystack_datetime(data.get("next_payment_date"))
            or self._parse_paystack_datetime(data.get("next_payment"))
            or self._parse_paystack_datetime(data.get("current_period_end"))
        )

    @staticmethod
    def _compute_fallback_next_payment_date(
        subscription: TenantSubscription, interval_days: int
    ) -> datetime:
        now = datetime.now(timezone.utc)
        anchor = getattr(subscription, "next_payment_date", None)
        if isinstance(anchor, datetime):
            anchor_utc = anchor if anchor.tzinfo else anchor.replace(tzinfo=timezone.utc)
            if anchor_utc < now - timedelta(days=interval_days):
                anchor_utc = now
        else:
            anchor_utc = now

        candidate = anchor_utc + timedelta(days=interval_days)
        if candidate <= now:
            candidate = now + timedelta(days=interval_days)
        return candidate

    async def _resolve_renewal_next_payment_date(
        self, subscription: TenantSubscription, charge_data: dict[str, Any]
    ) -> datetime:
        provider_next_payment = await self._fetch_provider_next_payment_date(
            subscription
        )
        if provider_next_payment is not None:
            return provider_next_payment

        payload_next_payment = self._parse_paystack_datetime(
            charge_data.get("next_payment_date")
        )
        if payload_next_payment is not None:
            return payload_next_payment

        interval_days = self._infer_interval_days(charge_data)
        return self._compute_fallback_next_payment_date(subscription, interval_days)

    async def create_checkout_session(
        self,
        tenant_id: UUID,
        tier: PricingTier,
        email: str,
        callback_url: str,
        billing_cycle: str = "monthly",
        currency: str | None = None,
    ) -> dict[str, Any]:
        """
        Initialize Paystack transaction for subscription using dynamic currency.
        Defaults to NGN and supports USD only when explicitly enabled.
        """
        if tier == PricingTier.FREE:
            raise ValueError("Cannot checkout free tier")

        is_annual = billing_cycle.lower() == "annual"

        # 1. Look up USD price from TIER_CONFIG (or DB fallback)
        from app.shared.core.pricing import TIER_CONFIG

        config = TIER_CONFIG.get(tier)
        if not config:
            raise ValueError(f"Invalid tier: {tier}")

        usd_price = (
            config["price_usd"]["annual"]
            if is_annual
            else config["price_usd"]["monthly"]
        )

        checkout_currency = self._resolve_checkout_currency(currency)
        fx_rate: float | None = None
        fx_provider: str | None = None
        amount_subunits: int

        if checkout_currency == PAYSTACK_CHECKOUT_CURRENCY:
            # Convert to NGN using Exchange Rate Service.
            from app.shared.core.currency import ExchangeRateService

            currency_service = ExchangeRateService(self.db)
            ngn_rate = await currency_service.get_ngn_rate()
            amount_subunits = currency_service.convert_usd_to_ngn(usd_price, ngn_rate)
            fx_rate = float(ngn_rate)
            fx_provider = PAYSTACK_FX_PROVIDER
        else:
            # USD checkout uses native currency subunits (cents).
            amount_subunits = int(round(float(usd_price) * 100))
            fx_rate = 1.0
            fx_provider = PAYSTACK_USD_FX_PROVIDER

        try:
            # Check existing subscription
            result = await self.db.execute(
                select(TenantSubscription).where(
                    TenantSubscription.tenant_id == tenant_id
                )
            )
            sub = result.scalar_one_or_none()

            # Start transaction (WITHOUT plan_code to allow dynamic amount)
            # We pass plan_code as None here because initialize_transaction supports it
            response = await self.client.initialize_transaction(
                email=email,
                amount_kobo=amount_subunits,
                plan_code=None,  # Dynamic billing uses authorization_code later
                callback_url=callback_url,
                metadata={
                    "tenant_id": str(tenant_id),
                    "tier": tier.value,
                    "billing_cycle": billing_cycle,
                    "usd_price": usd_price,
                    "currency": checkout_currency,
                    "amount_subunits": amount_subunits,
                    "exchange_rate": fx_rate,
                    "fx_provider": fx_provider,
                },
            )

            auth_url = response["data"]["authorization_url"]
            reference = response["data"]["reference"]

            logger.info(
                "paystack_dynamic_tx_initialized",
                tenant_id=str(tenant_id),
                tier=tier.value,
                currency=checkout_currency,
                amount_subunits=amount_subunits,
                reference=reference,
                fx_rate=fx_rate,
                usd_price=usd_price,
            )

            # SOC2: Persist immutable billing event for audit trails (FX transparency)
            try:
                from app.modules.governance.domain.security.audit_log import (
                    AuditEventType,
                    AuditLogger,
                )

                audit = AuditLogger(
                    db=self.db, tenant_id=tenant_id, correlation_id=reference
                )
                await audit.log(
                    event_type=AuditEventType.BILLING_PAYMENT_INITIATED,
                    resource_type="tenant_subscription",
                    resource_id=str(tenant_id),
                    details={
                        "provider": "paystack",
                        "tier": tier.value,
                        "usd_price": usd_price,
                        "exchange_rate": fx_rate,
                        "amount_subunits": amount_subunits,
                        "settlement_currency": checkout_currency,
                        "billing_cycle": billing_cycle,
                    },
                )
            except Exception as audit_exc:
                logger.warning(
                    "billing_init_audit_failed",
                    tenant_id=str(tenant_id),
                    error=str(audit_exc),
                )

            # Create/Update local record placeholder
            if not sub:
                import uuid

                sub = TenantSubscription(
                    id=uuid.uuid4(), tenant_id=tenant_id, tier=tier.value
                )
                self.db.add(sub)
            sub.billing_currency = checkout_currency
            sub.last_charge_amount_subunits = amount_subunits
            sub.last_charge_fx_rate = fx_rate
            sub.last_charge_fx_provider = fx_provider
            sub.last_charge_reference = reference
            sub.last_charge_at = datetime.now(timezone.utc)

            await self.db.commit()

            return {"url": auth_url, "reference": reference}

        except Exception as e:
            logger.error(
                "paystack_checkout_failed", tenant_id=str(tenant_id), error=str(e)
            )
            raise

    async def charge_renewal(self, subscription: TenantSubscription) -> bool:
        """
        Charges a recurring subscription using the stored authorization_code.
        This allows for dynamic pricing based on current exchange rates.
        """
        if not subscription.paystack_auth_code:
            logger.error(
                "renewal_failed_no_auth_code", tenant_id=str(subscription.tenant_id)
            )
            return False

        # SEC-10: Decrypt Authorization Code for use
        auth_code = decrypt_string(subscription.paystack_auth_code, context="api_key")
        if not auth_code:
            logger.error(
                "renewal_failed_decryption_error", tenant_id=str(subscription.tenant_id)
            )
            return False

        # 1. Determine USD price from DB
        from app.models.pricing import PricingPlan

        plan_res = await self.db.execute(
            select(PricingPlan).where(PricingPlan.id == subscription.tier)
        )
        plan_obj = plan_res.scalar_one_or_none()

        if plan_obj:
            usd_price = float(plan_obj.price_usd)
        else:
            # Fallback to TIER_CONFIG
            from app.shared.core.pricing import TIER_CONFIG

            try:
                subscription_tier = PricingTier(subscription.tier)
            except ValueError:
                logger.error(
                    "renewal_failed_invalid_tier",
                    tenant_id=str(subscription.tenant_id),
                    tier=subscription.tier,
                )
                return False

            config = TIER_CONFIG.get(subscription_tier)
            if not config:
                return False
            # Handle both int and dict cases for safety
            price_cfg = config["price_usd"]
            usd_price = (
                price_cfg["monthly"]
                if isinstance(price_cfg, dict)
                else float(price_cfg)
            )

        raw_currency = getattr(subscription, "billing_currency", None)
        if isinstance(raw_currency, str) and raw_currency.strip():
            renewal_currency = raw_currency.strip().upper()
        else:
            renewal_currency = PAYSTACK_CHECKOUT_CURRENCY
        fx_rate: float | None = None
        fx_provider: str | None = None
        amount_subunits: int

        if renewal_currency == PAYSTACK_CHECKOUT_CURRENCY:
            # Get latest exchange rate for NGN settlement.
            from app.shared.core.currency import ExchangeRateService

            currency_service = ExchangeRateService(self.db)
            ngn_rate = await currency_service.get_ngn_rate()
            amount_subunits = currency_service.convert_usd_to_ngn(usd_price, ngn_rate)
            fx_rate = float(ngn_rate)
            fx_provider = PAYSTACK_FX_PROVIDER
        elif renewal_currency == "USD":
            amount_subunits = int(round(float(usd_price) * 100))
            fx_rate = 1.0
            fx_provider = PAYSTACK_USD_FX_PROVIDER
        else:
            logger.warning(
                "renewal_unsupported_currency_fallback_to_ngn",
                tenant_id=str(subscription.tenant_id),
                billing_currency=raw_currency,
            )
            from app.shared.core.currency import ExchangeRateService

            currency_service = ExchangeRateService(self.db)
            ngn_rate = await currency_service.get_ngn_rate()
            amount_subunits = currency_service.convert_usd_to_ngn(usd_price, ngn_rate)
            fx_rate = float(ngn_rate)
            fx_provider = PAYSTACK_FX_PROVIDER
            renewal_currency = PAYSTACK_CHECKOUT_CURRENCY

        # 3. Fetch User email linked to tenant
        from app.models.tenant import User

        user_res = await self.db.execute(
            select(User).where(User.tenant_id == subscription.tenant_id).limit(1)
        )
        user_obj = user_res.scalar_one_or_none()
        if not user_obj:
            logger.error(
                "renewal_failed_no_user_found", tenant_id=str(subscription.tenant_id)
            )
            return False

        from app.shared.core.security import (
            decrypt_string as sec_decrypt,
        )  # Avoid naming collision

        user_email = sec_decrypt(user_obj.email, context="pii")
        if not user_email:
            logger.error(
                "renewal_failed_email_decryption_error",
                tenant_id=str(subscription.tenant_id),
            )
            return False

        try:
            # Paystack Charge Authorization API
            response = await self.client.charge_authorization(
                email=user_email,
                amount_kobo=amount_subunits,
                authorization_code=auth_code,
                metadata={
                    "tenant_id": str(subscription.tenant_id),
                    "type": "renewal",
                    "plan": subscription.tier,
                    "currency": renewal_currency,
                    "exchange_rate": fx_rate,
                    "fx_provider": fx_provider,
                },
            )

            if response.get("status") and response["data"].get("status") == "success":
                charge_data = response.get("data", {})
                reference = charge_data.get("reference")
                subscription.next_payment_date = (
                    await self._resolve_renewal_next_payment_date(
                        subscription, charge_data
                    )
                )
                subscription.billing_currency = renewal_currency
                subscription.last_charge_amount_subunits = amount_subunits
                subscription.last_charge_fx_rate = fx_rate
                subscription.last_charge_fx_provider = fx_provider
                if reference:
                    subscription.last_charge_reference = str(reference)
                subscription.last_charge_at = datetime.now(timezone.utc)
                await self.db.commit()

                # SOC2: Persist immutable billing event for audit trails (FX transparency on renewal)
                try:
                    from app.modules.governance.domain.security.audit_log import (
                        AuditEventType,
                        AuditLogger,
                    )

                    audit = AuditLogger(
                        db=self.db,
                        tenant_id=subscription.tenant_id,
                        correlation_id=str(reference) if reference else None,
                    )
                    await audit.log(
                        event_type=AuditEventType.BILLING_PAYMENT_RECEIVED,
                        resource_type="tenant_subscription",
                        resource_id=str(subscription.id),
                        details={
                            "provider": "paystack",
                            "event": "charge_renewal",
                            "usd_price": usd_price,
                            "exchange_rate": fx_rate,
                            "amount_subunits": amount_subunits,
                            "settlement_currency": renewal_currency,
                            "reference": reference,
                            "success": True,
                        },
                    )
                except Exception as audit_exc:
                    logger.warning(
                        "billing_renewal_audit_failed",
                        tenant_id=str(subscription.tenant_id),
                        error=str(audit_exc),
                    )

                return True
            return False
        except Exception as e:
            logger.error(
                "renewal_failed", tenant_id=str(subscription.tenant_id), error=str(e)
            )
            return False

    async def cancel_subscription(self, tenant_id: UUID) -> None:
        """Cancel Paystack subscription."""
        result = await self.db.execute(
            select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
        )
        sub = result.scalar_one_or_none()

        if (
            not sub
            or not sub.paystack_subscription_code
            or not sub.paystack_email_token
        ):
            raise ValueError("No active subscription to cancel")

        try:
            await self.client.disable_subscription(
                code=sub.paystack_subscription_code, token=sub.paystack_email_token
            )
            sub.status = SubscriptionStatus.CANCELLED.value
            sub.canceled_at = datetime.now(timezone.utc)
            await self.db.commit()

            logger.info("subscription_canceled", tenant_id=str(tenant_id))

        except Exception as e:
            logger.error("cancel_failed", tenant_id=str(tenant_id), error=str(e))
            raise


class WebhookHandler:
    """Paystack Webhook Handler."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def handle(
        self, request: Request, payload: bytes, signature: str
    ) -> dict[str, str]:
        """Verify and process webhook."""
        from fastapi import HTTPException

        # Finding #12: Validate Content-Type for JSON parsing safety
        content_type = request.headers.get("Content-Type", "")
        if "application/json" not in content_type.lower():
            logger.warning(
                "paystack_webhook_invalid_content_type", content_type=content_type
            )
            raise HTTPException(
                400, "Unsupported media type: expected application/json"
            )

        if not self.verify_signature(payload, signature):
            raise HTTPException(401, "Invalid signature")

        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            logger.error("paystack_webhook_invalid_json", payload_len=len(payload))
            raise HTTPException(400, "Invalid JSON payload")

        event_type = event.get("event")
        data = event.get("data", {})

        logger.info("paystack_webhook_received", paystack_event=event_type)

        handlers = {
            "subscription.create": self._handle_subscription_create,
            "subscription.disable": self._handle_subscription_disable,
            "charge.success": self._handle_charge_success,
            "invoice.payment_failed": self._handle_invoice_failed,
        }

        handler = handlers.get(event_type)
        if handler:
            await handler(data)

        return {"status": "success"}

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Paystack webhook signature using HMAC-SHA512."""
        if not signature:
            logger.warning("paystack_webhook_missing_signature")
            return False

        if not settings.PAYSTACK_SECRET_KEY:
            logger.error("paystack_secret_key_not_configured")
            return False

        expected = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode(), payload, hashlib.sha512
        ).hexdigest()

        is_valid = hmac.compare_digest(expected, signature)
        if not is_valid:
            logger.warning(
                "paystack_webhook_invalid_signature", provided_sig=signature[:8] + "..."
            )

        return is_valid

    async def _handle_subscription_create(self, data: dict[str, Any]) -> None:
        """Handle new subscription - update subscription codes and next payment date."""
        customer_code = data.get("customer", {}).get("customer_code")
        subscription_code = data.get("subscription_code")
        email_token = data.get("email_token")
        next_payment_date_str = data.get("next_payment_date")

        if not customer_code:
            logger.warning("subscription_create_missing_customer_code", data=data)
            return

        # Find subscription by customer code
        result = await self.db.execute(
            select(TenantSubscription).where(
                TenantSubscription.paystack_customer_code == customer_code
            )
        )
        sub = result.scalar_one_or_none()

        if not sub:
            logger.warning(
                "subscription_create_tenant_not_found",
                customer_code=customer_code,
                msg="No matching tenant - subscription may have been created before charge.success",
            )
            return

        # Update subscription codes
        if subscription_code:
            sub.paystack_subscription_code = subscription_code
        if email_token:
            sub.paystack_email_token = email_token
        if next_payment_date_str:
            try:
                sub.next_payment_date = datetime.fromisoformat(
                    next_payment_date_str.replace("Z", "+00:00")
                )
            except ValueError:
                logger.warning("invalid_next_payment_date", date=next_payment_date_str)

        sub.status = SubscriptionStatus.ACTIVE.value
        # SOC2: Persist an immutable billing event for audit trails.
        try:
            from app.modules.governance.domain.security.audit_log import (
                AuditEventType,
                AuditLogger,
            )

            audit = AuditLogger(
                db=self.db,
                tenant_id=sub.tenant_id,
                correlation_id=str(subscription_code or customer_code or ""),
            )
            await audit.log(
                event_type=AuditEventType.BILLING_SUBSCRIPTION_CREATED,
                resource_type="tenant_subscription",
                resource_id=str(sub.id),
                details={
                    "provider": "paystack",
                    "event": "subscription.create",
                    "subscription_code": subscription_code,
                    "customer_code": customer_code,
                    "next_payment_date": next_payment_date_str,
                },
            )
        except Exception as exc:
            logger.warning(
                "billing_audit_log_failed",
                tenant_id=str(sub.tenant_id),
                paystack_event="subscription.create",
                error=str(exc),
            )

        await self.db.commit()

        logger.info(
            "subscription_create_processed",
            subscription_code=subscription_code,
            customer_code=customer_code,
        )

    async def _handle_charge_success(self, data: dict[str, Any]) -> None:
        """Handle successful charge - primary activation point."""
        metadata = data.get("metadata", {})
        if isinstance(metadata, str):
            try:
                import json

                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError, ValueError):
                metadata = {}

        tenant_id_str = metadata.get("tenant_id")
        tier = metadata.get("tier")
        logger.info("paystack_webhook_data_parsed", tenant_id=tenant_id_str, tier=tier)

        customer = data.get("customer", {})
        customer_code = customer.get("customer_code")
        customer_email = customer.get("email")
        charge_amount_raw = data.get("amount")
        charge_currency = str(
            data.get("currency") or PAYSTACK_CHECKOUT_CURRENCY
        ).upper()
        charge_reference = data.get("reference")

        tenant_id = None
        if tenant_id_str:
            try:
                tenant_id = UUID(tenant_id_str)
            except ValueError:
                logger.warning("invalid_tenant_id_in_metadata", tenant_id=tenant_id_str)

        # FALLBACK: Lookup by Email if metadata is missing or invalid
        if not tenant_id and customer_email:
            from app.models.tenant import User
            from app.shared.core.security import generate_blind_index

            logger.info(
                "webhook_metadata_missing_attempting_email_lookup",
                email_hash=_email_hash(customer_email),
            )
            email_bidx = generate_blind_index(customer_email)

            user_result = await self.db.execute(
                select(User).where(User.email_bidx == email_bidx)
            )
            user = user_result.scalar_one_or_none()
            if user:
                tenant_id = user.tenant_id
                logger.info(
                    "webhook_email_lookup_success",
                    tenant_id=str(tenant_id),
                    email_hash=_email_hash(customer_email),
                )
            else:
                logger.error(
                    "webhook_email_lookup_failed",
                    email_hash=_email_hash(customer_email),
                )

        if not tenant_id:
            logger.error(
                "webhook_tenant_lookup_failed_no_identifier",
                reference=data.get("reference"),
            )
            return

        # In subscription context, data includes authorization (for future charges)
        _ = data.get("authorization", {})

        # If this is a subscription charge, we might get plan info
        # plan = data.get("plan", {}) # F841: Local variable `plan` is assigned to but never used

        if tenant_id:
            resolved_tier: PricingTier | None = None
            if tier:
                try:
                    resolved_tier = PricingTier(str(tier).strip().lower())
                except ValueError:
                    logger.warning(
                        "paystack_webhook_invalid_tier",
                        tenant_id=str(tenant_id),
                        tier=tier,
                    )

            # It's a subscription payment
            result = await self.db.execute(
                select(TenantSubscription).where(
                    TenantSubscription.tenant_id == tenant_id
                )
            )
            sub = result.scalar_one_or_none()

            if not sub:
                import uuid

                sub = TenantSubscription(id=uuid.uuid4(), tenant_id=tenant_id)
                self.db.add(sub)

            sub.paystack_customer_code = customer_code

            # SEC-10: Encrypt and Capture Authorization Code for Dynamic Recurring Billing
            authorization = data.get("authorization", {})
            auth_code = authorization.get("authorization_code")
            if auth_code:
                sub.paystack_auth_code = encrypt_string(auth_code, context="api_key")
                logger.info(
                    "paystack_auth_token_encrypted_and_captured",
                    tenant_id=str(tenant_id),
                )

            if resolved_tier is not None:
                sub.tier = resolved_tier.value
            sub.status = SubscriptionStatus.ACTIVE.value
            sub.billing_currency = charge_currency
            if isinstance(charge_amount_raw, (int, float, str)):
                try:
                    sub.last_charge_amount_subunits = int(charge_amount_raw)
                except (TypeError, ValueError):
                    logger.warning(
                        "paystack_charge_amount_invalid",
                        tenant_id=str(tenant_id),
                        amount=charge_amount_raw,
                    )
            fx_rate_raw = metadata.get("exchange_rate")
            if isinstance(fx_rate_raw, (int, float, str)):
                try:
                    sub.last_charge_fx_rate = float(fx_rate_raw)
                except (TypeError, ValueError):
                    logger.warning(
                        "paystack_fx_rate_invalid",
                        tenant_id=str(tenant_id),
                        exchange_rate=fx_rate_raw,
                    )
            fx_provider = metadata.get("fx_provider")
            if isinstance(fx_provider, str) and fx_provider.strip():
                sub.last_charge_fx_provider = fx_provider.strip().lower()
            elif charge_currency == PAYSTACK_CHECKOUT_CURRENCY:
                sub.last_charge_fx_provider = PAYSTACK_FX_PROVIDER
            if charge_reference:
                sub.last_charge_reference = str(charge_reference)
            sub.last_charge_at = datetime.now(timezone.utc)

            # Keep entitlements in sync: auth reads Tenant.plan, not TenantSubscription.tier.
            if resolved_tier is not None:
                try:
                    from app.models.tenant import Tenant

                    await self.db.execute(
                        update(Tenant)
                        .where(Tenant.id == tenant_id)
                        .values(plan=resolved_tier.value)
                    )
                except Exception as exc:
                    logger.warning(
                        "billing_plan_sync_failed",
                        tenant_id=str(tenant_id),
                        tier=resolved_tier.value,
                        error=str(exc),
                    )

            # SOC2: Persist an immutable billing event for audit trails.
            try:
                from app.modules.governance.domain.security.audit_log import (
                    AuditEventType,
                    AuditLogger,
                )

                reference = data.get("reference")
                correlation_id = str(reference) if reference else None
                audit = AuditLogger(
                    db=self.db, tenant_id=tenant_id, correlation_id=correlation_id
                )
                await audit.log(
                    event_type=AuditEventType.BILLING_PAYMENT_RECEIVED,
                    resource_type="tenant_subscription",
                    resource_id=str(sub.id),
                    details={
                        "provider": "paystack",
                        "event": "charge.success",
                        "reference": reference,
                        "tier": (resolved_tier.value if resolved_tier else sub.tier),
                        "customer_code": customer_code,
                        "currency": charge_currency,
                        "amount_subunits": (
                            int(charge_amount_raw)
                            if isinstance(charge_amount_raw, (int, float))
                            else charge_amount_raw
                        ),
                        "fx_rate": metadata.get("exchange_rate"),
                        "fx_provider": metadata.get("fx_provider")
                        or sub.last_charge_fx_provider,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "billing_audit_log_failed",
                    tenant_id=str(tenant_id),
                    paystack_event="charge.success",
                    error=str(exc),
                )

            await self.db.commit()
            logger.info("paystack_subscription_activated", tenant_id=str(tenant_id))

    async def _handle_subscription_disable(self, data: dict[str, Any]) -> None:
        code = data.get("subscription_code")
        if code:
            result = await self.db.execute(
                select(TenantSubscription).where(
                    TenantSubscription.paystack_subscription_code == code
                )
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.status = SubscriptionStatus.CANCELLED.value
                sub.canceled_at = datetime.now(timezone.utc)
                await self.db.commit()

    async def _handle_invoice_failed(self, data: dict[str, Any]) -> None:
        """Handle failed payment - trigger dunning workflow."""
        invoice_code = data.get("invoice_code")
        subscription_code = data.get("subscription_code")
        customer_code = data.get("customer", {}).get("customer_code")

        logger.warning(
            "invoice_payment_failed",
            invoice_code=invoice_code,
            subscription_code=subscription_code,
            customer_code=customer_code,
            msg="Payment failed - initiating dunning workflow",
        )

        # Find subscription and trigger dunning workflow
        if subscription_code:
            result = await self.db.execute(
                select(TenantSubscription).where(
                    TenantSubscription.paystack_subscription_code == subscription_code
                )
            )
            sub = result.scalar_one_or_none()

            if sub:
                # Delegate to DunningService for complete workflow
                from app.modules.billing.domain.billing.dunning_service import (
                    DunningService,
                )

                dunning = DunningService(self.db)
                await dunning.process_failed_payment(sub.id, is_webhook=True)

                # SOC2: Persist an immutable billing event for audit trails.
                try:
                    from app.modules.governance.domain.security.audit_log import (
                        AuditEventType,
                        AuditLogger,
                    )

                    audit = AuditLogger(
                        db=self.db,
                        tenant_id=sub.tenant_id,
                        correlation_id=str(invoice_code or subscription_code or ""),
                    )
                    await audit.log(
                        event_type=AuditEventType.BILLING_PAYMENT_FAILED,
                        resource_type="tenant_subscription",
                        resource_id=str(sub.id),
                        details={
                            "provider": "paystack",
                            "event": "invoice.payment_failed",
                            "invoice_code": invoice_code,
                            "subscription_code": subscription_code,
                            "customer_code": customer_code,
                        },
                        success=False,
                        error_message="invoice.payment_failed",
                    )
                    await self.db.commit()
                except Exception as exc:
                    logger.warning(
                        "billing_audit_log_failed",
                        tenant_id=str(sub.tenant_id),
                        paystack_event="invoice.payment_failed",
                        error=str(exc),
                    )

                logger.info(
                    "dunning_workflow_initiated",
                    tenant_id=str(sub.tenant_id),
                    subscription_code=subscription_code,
                )
