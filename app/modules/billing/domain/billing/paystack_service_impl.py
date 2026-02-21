"""Billing service implementation for Paystack."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pricing import TenantSubscription
from app.shared.core.pricing import PricingTier

from . import paystack_shared as shared
from .paystack_client_impl import PaystackClient


class BillingService:
    """Paystack billing operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = PaystackClient()

        # Monthly plan codes
        self.plan_codes = {
            PricingTier.STARTER: shared.settings.PAYSTACK_PLAN_STARTER,
            PricingTier.GROWTH: shared.settings.PAYSTACK_PLAN_GROWTH,
            PricingTier.PRO: shared.settings.PAYSTACK_PLAN_PRO,
            PricingTier.ENTERPRISE: shared.settings.PAYSTACK_PLAN_ENTERPRISE,
        }

        # Annual plan codes (17% discount - 2 months free)
        self.annual_plan_codes = {
            PricingTier.STARTER: getattr(
                shared.settings, "PAYSTACK_PLAN_STARTER_ANNUAL", None
            ),
            PricingTier.GROWTH: getattr(
                shared.settings, "PAYSTACK_PLAN_GROWTH_ANNUAL", None
            ),
            PricingTier.PRO: getattr(shared.settings, "PAYSTACK_PLAN_PRO_ANNUAL", None),
            PricingTier.ENTERPRISE: getattr(
                shared.settings, "PAYSTACK_PLAN_ENTERPRISE_ANNUAL", None
            ),
        }

        # Monthly amounts in Kobo (NGN x 100)
        from app.shared.core.pricing import TIER_CONFIG

        self.plan_amounts: dict[PricingTier, int] = {}
        self.annual_plan_amounts: dict[PricingTier, int] = {}

        for tier, config in TIER_CONFIG.items():
            kobo_config = config.get("paystack_amount_kobo")
            if tier == PricingTier.FREE and kobo_config is None:
                continue
            # Enterprise/custom tiers may not have fixed Paystack amounts.
            if kobo_config is None:
                shared.logger.warning(
                    "paystack_amount_kobo_missing_for_tier",
                    tier=tier.value,
                )
                continue
            if not isinstance(kobo_config, dict):
                shared.logger.warning(
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
                shared.logger.warning(
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
                shared.settings,
                "PAYSTACK_DEFAULT_CHECKOUT_CURRENCY",
                shared.PAYSTACK_CHECKOUT_CURRENCY,
            )
            or shared.PAYSTACK_CHECKOUT_CURRENCY
        ).strip().upper()
        if default_currency not in {"NGN", "USD"}:
            default_currency = shared.PAYSTACK_CHECKOUT_CURRENCY

        resolved = (
            str(requested_currency).strip().upper()
            if isinstance(requested_currency, str) and requested_currency.strip()
            else default_currency
        )
        if resolved == "USD" and not bool(
            getattr(shared.settings, "PAYSTACK_ENABLE_USD_CHECKOUT", False)
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
            shared.logger.warning(
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

        if checkout_currency == shared.PAYSTACK_CHECKOUT_CURRENCY:
            # Convert to NGN using Exchange Rate Service.
            from app.shared.core.currency import ExchangeRateService

            currency_service = ExchangeRateService(self.db)
            ngn_rate = await currency_service.get_ngn_rate()
            amount_subunits = currency_service.convert_usd_to_ngn(usd_price, ngn_rate)
            fx_rate = float(ngn_rate)
            fx_provider = shared.PAYSTACK_FX_PROVIDER
        else:
            # USD checkout uses native currency subunits (cents).
            amount_subunits = int(round(float(usd_price) * 100))
            fx_rate = 1.0
            fx_provider = shared.PAYSTACK_USD_FX_PROVIDER

        try:
            # Check existing subscription
            result = await self.db.execute(
                select(TenantSubscription).where(
                    TenantSubscription.tenant_id == tenant_id
                )
            )
            sub = result.scalar_one_or_none()

            # Start transaction (WITHOUT plan_code to allow dynamic amount)
            response = await self.client.initialize_transaction(
                email=email,
                amount_kobo=amount_subunits,
                plan_code=None,
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

            shared.logger.info(
                "paystack_dynamic_tx_initialized",
                tenant_id=str(tenant_id),
                tier=tier.value,
                currency=checkout_currency,
                amount_subunits=amount_subunits,
                reference=reference,
                fx_rate=fx_rate,
                usd_price=usd_price,
            )

            try:
                from app.modules.governance.domain.security.audit_log import (
                    AuditEventType,
                    AuditLogger,
                )

                audit = AuditLogger(db=self.db, tenant_id=tenant_id, correlation_id=reference)
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
                shared.logger.warning(
                    "billing_init_audit_failed",
                    tenant_id=str(tenant_id),
                    error=str(audit_exc),
                )

            if not sub:
                import uuid

                sub = TenantSubscription(id=uuid.uuid4(), tenant_id=tenant_id, tier=tier.value)
                self.db.add(sub)
            sub.billing_currency = checkout_currency
            sub.last_charge_amount_subunits = amount_subunits
            sub.last_charge_fx_rate = fx_rate
            sub.last_charge_fx_provider = fx_provider
            sub.last_charge_reference = reference
            sub.last_charge_at = datetime.now(timezone.utc)

            await self.db.commit()

            return {"url": auth_url, "reference": reference}

        except Exception as exc:
            shared.logger.error(
                "paystack_checkout_failed", tenant_id=str(tenant_id), error=str(exc)
            )
            raise

    async def charge_renewal(self, subscription: TenantSubscription) -> bool:
        """Charge a recurring subscription using the stored authorization_code."""
        if not subscription.paystack_auth_code:
            shared.logger.error(
                "renewal_failed_no_auth_code", tenant_id=str(subscription.tenant_id)
            )
            return False

        auth_code = shared.decrypt_string(subscription.paystack_auth_code, context="api_key")
        if not auth_code:
            shared.logger.error(
                "renewal_failed_decryption_error", tenant_id=str(subscription.tenant_id)
            )
            return False

        from app.models.pricing import PricingPlan

        plan_res = await self.db.execute(
            select(PricingPlan).where(PricingPlan.id == subscription.tier)
        )
        plan_obj = plan_res.scalar_one_or_none()

        if plan_obj:
            usd_price = float(plan_obj.price_usd)
        else:
            from app.shared.core.pricing import TIER_CONFIG

            try:
                subscription_tier = PricingTier(subscription.tier)
            except ValueError:
                shared.logger.error(
                    "renewal_failed_invalid_tier",
                    tenant_id=str(subscription.tenant_id),
                    tier=subscription.tier,
                )
                return False

            config = TIER_CONFIG.get(subscription_tier)
            if not config:
                return False
            price_cfg = config["price_usd"]
            usd_price = (
                price_cfg["monthly"] if isinstance(price_cfg, dict) else float(price_cfg)
            )

        raw_currency = getattr(subscription, "billing_currency", None)
        if isinstance(raw_currency, str) and raw_currency.strip():
            renewal_currency = raw_currency.strip().upper()
        else:
            renewal_currency = shared.PAYSTACK_CHECKOUT_CURRENCY

        fx_rate: float | None = None
        fx_provider: str | None = None
        amount_subunits: int

        if renewal_currency == shared.PAYSTACK_CHECKOUT_CURRENCY:
            from app.shared.core.currency import ExchangeRateService

            currency_service = ExchangeRateService(self.db)
            ngn_rate = await currency_service.get_ngn_rate()
            amount_subunits = currency_service.convert_usd_to_ngn(usd_price, ngn_rate)
            fx_rate = float(ngn_rate)
            fx_provider = shared.PAYSTACK_FX_PROVIDER
        elif renewal_currency == "USD":
            amount_subunits = int(round(float(usd_price) * 100))
            fx_rate = 1.0
            fx_provider = shared.PAYSTACK_USD_FX_PROVIDER
        else:
            shared.logger.warning(
                "renewal_unsupported_currency_fallback_to_ngn",
                tenant_id=str(subscription.tenant_id),
                billing_currency=raw_currency,
            )
            from app.shared.core.currency import ExchangeRateService

            currency_service = ExchangeRateService(self.db)
            ngn_rate = await currency_service.get_ngn_rate()
            amount_subunits = currency_service.convert_usd_to_ngn(usd_price, ngn_rate)
            fx_rate = float(ngn_rate)
            fx_provider = shared.PAYSTACK_FX_PROVIDER
            renewal_currency = shared.PAYSTACK_CHECKOUT_CURRENCY

        from app.models.tenant import User

        user_res = await self.db.execute(
            select(User).where(User.tenant_id == subscription.tenant_id).limit(1)
        )
        user_obj = user_res.scalar_one_or_none()
        if not user_obj:
            shared.logger.error(
                "renewal_failed_no_user_found", tenant_id=str(subscription.tenant_id)
            )
            return False

        from app.shared.core.security import decrypt_string as sec_decrypt

        user_email = sec_decrypt(user_obj.email, context="pii")
        if not user_email:
            shared.logger.error(
                "renewal_failed_email_decryption_error",
                tenant_id=str(subscription.tenant_id),
            )
            return False

        try:
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
                subscription.next_payment_date = await self._resolve_renewal_next_payment_date(
                    subscription, charge_data
                )
                subscription.billing_currency = renewal_currency
                subscription.last_charge_amount_subunits = amount_subunits
                subscription.last_charge_fx_rate = fx_rate
                subscription.last_charge_fx_provider = fx_provider
                if reference:
                    subscription.last_charge_reference = str(reference)
                subscription.last_charge_at = datetime.now(timezone.utc)
                await self.db.commit()

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
                    shared.logger.warning(
                        "billing_renewal_audit_failed",
                        tenant_id=str(subscription.tenant_id),
                        error=str(audit_exc),
                    )

                return True
            return False
        except Exception as exc:
            shared.logger.error(
                "renewal_failed", tenant_id=str(subscription.tenant_id), error=str(exc)
            )
            return False

    async def cancel_subscription(self, tenant_id: UUID) -> None:
        """Cancel Paystack subscription."""
        result = await self.db.execute(
            select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
        )
        sub = result.scalar_one_or_none()

        if not sub or not sub.paystack_subscription_code or not sub.paystack_email_token:
            raise ValueError("No active subscription to cancel")

        try:
            await self.client.disable_subscription(
                code=sub.paystack_subscription_code, token=sub.paystack_email_token
            )
            sub.status = shared.SubscriptionStatus.CANCELLED.value
            sub.canceled_at = datetime.now(timezone.utc)
            await self.db.commit()

            shared.logger.info("subscription_canceled", tenant_id=str(tenant_id))

        except Exception as exc:
            shared.logger.error("cancel_failed", tenant_id=str(tenant_id), error=str(exc))
            raise
