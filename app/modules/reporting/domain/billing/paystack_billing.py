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
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID
import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pricing import TenantSubscription
from app.shared.core.config import get_settings
from app.shared.core.pricing import PricingTier
from app.shared.core.security import encrypt_string, decrypt_string

logger = structlog.get_logger()
settings = get_settings()


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

    def __init__(self):
        if not settings.PAYSTACK_SECRET_KEY:
            raise ValueError("PAYSTACK_SECRET_KEY not configured")
        
        self.headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json"
        }

    async def _request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method,
                    f"{self.BASE_URL}/{endpoint}",
                    headers=self.headers,
                    json=data,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error("paystack_api_error", endpoint=endpoint, error=str(e))
                raise

    async def initialize_transaction(self, email: str, amount_kobo: int, plan_code: Optional[str], callback_url: str, metadata: Dict) -> Dict:
        """Initialize a transaction to start a subscription."""
        data = {
            "email": email,
            "amount": amount_kobo,
            "callback_url": callback_url,
            "metadata": metadata
        }
        if plan_code:
            data["plan"] = plan_code
            
        return await self._request("POST", "transaction/initialize", data)

    async def charge_authorization(self, email: str, amount_kobo: int, authorization_code: str, metadata: Dict) -> Dict:
        """Charge a stored authorization code (recurring billing)."""
        data = {
            "email": email,
            "amount": amount_kobo,
            "authorization_code": authorization_code,
            "metadata": metadata
        }
        return await self._request("POST", "transaction/charge_authorization", data)

    async def verify_transaction(self, reference: str) -> Dict:
        """Verify transaction status."""
        return await self._request("GET", f"transaction/verify/{reference}")

    async def fetch_subscription(self, code_or_token: str) -> Dict:
        """Fetch subscription details."""
        return await self._request("GET", f"subscription/{code_or_token}")

    async def disable_subscription(self, code: str, token: str) -> Dict:
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
            PricingTier.STARTER: getattr(settings, 'PAYSTACK_PLAN_STARTER_ANNUAL', None),
            PricingTier.GROWTH: getattr(settings, 'PAYSTACK_PLAN_GROWTH_ANNUAL', None),
            PricingTier.PRO: getattr(settings, 'PAYSTACK_PLAN_PRO_ANNUAL', None),
            PricingTier.ENTERPRISE: getattr(settings, 'PAYSTACK_PLAN_ENTERPRISE_ANNUAL', None),
        }
        
        # Monthly amounts in Kobo (NGN x 100)
        from app.shared.core.pricing import TIER_CONFIG
        self.plan_amounts = {}
        self.annual_plan_amounts = {}
        
        for tier, config in TIER_CONFIG.items():
            kobo_config = config.get("paystack_amount_kobo")
            if tier in {PricingTier.FREE, PricingTier.TRIAL} and kobo_config is None:
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
            if not isinstance(monthly, (int, float)) or not isinstance(annual, (int, float)):
                logger.warning(
                    "paystack_amount_kobo_values_invalid_for_tier",
                    tier=tier.value,
                    monthly=monthly,
                    annual=annual,
                )
                continue
            self.plan_amounts[tier] = int(monthly)
            self.annual_plan_amounts[tier] = int(annual)

    async def create_checkout_session(
        self,
        tenant_id: UUID,
        tier: PricingTier,
        email: str,
        callback_url: str,
        billing_cycle: str = "monthly"
    ) -> Dict[str, Any]:
        """
        Initialize Paystack transaction for subscription using dynamic currency.
        We no longer use fixed Paystack Plans to support fluctuating exchange rates.
        """
        if tier == PricingTier.TRIAL:
            raise ValueError("Cannot checkout trial tier")

        is_annual = billing_cycle.lower() == "annual"
        
        # 1. Look up USD price from TIER_CONFIG (or DB fallback)
        from app.shared.core.pricing import TIER_CONFIG
        config = TIER_CONFIG.get(tier)
        if not config:
            raise ValueError(f"Invalid tier: {tier}")
            
        usd_price = config["price_usd"]["annual"] if is_annual else config["price_usd"]["monthly"]

        # 2. Convert to NGN using Exchange Rate Service
        from app.modules.reporting.domain.billing.currency import ExchangeRateService
        currency_service = ExchangeRateService(self.db)
        ngn_rate = await currency_service.get_ngn_rate()
        amount_kobo = currency_service.convert_usd_to_ngn(usd_price, ngn_rate)

        try:
            # Check existing subscription
            result = await self.db.execute(
                select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
            )
            sub = result.scalar_one_or_none()
            
            # Start transaction (WITHOUT plan_code to allow dynamic amount)
            # We pass plan_code as None here because initialize_transaction supports it
            response = await self.client.initialize_transaction(
                email=email,
                amount_kobo=amount_kobo,
                plan_code=None,  # Dynamic billing uses authorization_code later
                callback_url=callback_url,
                metadata={
                    "tenant_id": str(tenant_id), 
                    "tier": tier.value,
                    "billing_cycle": billing_cycle,
                    "usd_price": usd_price,
                    "exchange_rate": ngn_rate
                }
            )

            auth_url = response["data"]["authorization_url"]
            reference = response["data"]["reference"]

            logger.info("paystack_dynamic_tx_initialized",
                       tenant_id=str(tenant_id),
                       tier=tier.value,
                       amount_ngn=amount_kobo/100,
                       reference=reference)

            # Create/Update local record placeholder
            if not sub:
                import uuid
                sub = TenantSubscription(id=uuid.uuid4(), tenant_id=tenant_id, tier=tier.value)
                from app.shared.core.async_utils import maybe_await
                await maybe_await(self.db.add(sub))
            
            await self.db.commit()

            return {
                "url": auth_url,
                "reference": reference
            }

        except Exception as e:
            logger.error("paystack_checkout_failed", tenant_id=str(tenant_id), error=str(e))
            raise

    async def charge_renewal(self, subscription: TenantSubscription) -> bool:
        """
        Charges a recurring subscription using the stored authorization_code.
        This allows for dynamic pricing based on current exchange rates.
        """
        if not subscription.paystack_auth_code:
            logger.error("renewal_failed_no_auth_code", tenant_id=str(subscription.tenant_id))
            return False

        # SEC-10: Decrypt Authorization Code for use
        auth_code = decrypt_string(subscription.paystack_auth_code, context="api_key")
        if not auth_code:
            logger.error("renewal_failed_decryption_error", tenant_id=str(subscription.tenant_id))
            return False

        # 1. Determine USD price from DB
        from app.models.pricing import PricingPlan
        plan_res = await self.db.execute(select(PricingPlan).where(PricingPlan.id == subscription.tier))
        plan_obj = plan_res.scalar_one_or_none()
        
        if plan_obj:
            usd_price = float(plan_obj.price_usd)
        else:
            # Fallback to TIER_CONFIG
            from app.shared.core.pricing import TIER_CONFIG
            config = TIER_CONFIG.get(subscription.tier)
            if not config:
                return False
            # Handle both int and dict cases for safety
            price_cfg = config["price_usd"]
            usd_price = price_cfg["monthly"] if isinstance(price_cfg, dict) else float(price_cfg)

        # 2. Get latest exchange rate
        from app.modules.reporting.domain.billing.currency import ExchangeRateService
        currency_service = ExchangeRateService(self.db)
        ngn_rate = await currency_service.get_ngn_rate()
        amount_kobo = currency_service.convert_usd_to_ngn(usd_price, ngn_rate)

        # 3. Fetch User email linked to tenant
        from app.models.tenant import User
        user_res = await self.db.execute(select(User).where(User.tenant_id == subscription.tenant_id).limit(1))
        user_obj = user_res.scalar_one_or_none()
        if not user_obj:
            logger.error("renewal_failed_no_user_found", tenant_id=str(subscription.tenant_id))
            return False
            
        from app.shared.core.security import decrypt_string as sec_decrypt # Avoid naming collision
        user_email = sec_decrypt(user_obj.email, context="pii")

        try:
            # Paystack Charge Authorization API
            client = PaystackClient()
            response = await client.charge_authorization(
                email=user_email,
                amount_kobo=amount_kobo,
                authorization_code=auth_code,
                metadata={
                    "tenant_id": str(subscription.tenant_id),
                    "type": "renewal",
                    "plan": subscription.tier
                }
            )
            
            if response.get("status") and response["data"].get("status") == "success":
                subscription.next_payment_date = datetime.now(timezone.utc) + timedelta(days=30)
                await self.db.commit()
                return True
            return False
        except Exception as e:
            logger.error("renewal_failed", tenant_id=str(subscription.tenant_id), error=str(e))
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
                code=sub.paystack_subscription_code,
                token=sub.paystack_email_token
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

    async def handle(self, payload: bytes, signature: str) -> Dict[str, str]:
        """Verify and process webhook."""
        from fastapi import HTTPException
        if not self.verify_signature(payload, signature):
            raise HTTPException(401, "Invalid signature")

        import json
        event = json.loads(payload)
        event_type = event.get("event")
        data = event.get("data", {})

        logger.info("paystack_webhook_received", paystack_event=event_type)

        handlers = {
            "subscription.create": self._handle_subscription_create,
            "subscription.disable": self._handle_subscription_disable,
            "charge.success": self._handle_charge_success,
            "invoice.payment_failed": self._handle_invoice_failed
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
            settings.PAYSTACK_SECRET_KEY.encode(),
            payload,
            hashlib.sha512
        ).hexdigest()

        is_valid = hmac.compare_digest(expected, signature)
        if not is_valid:
            logger.warning("paystack_webhook_invalid_signature", provided_sig=signature[:8] + "...")
            
        return is_valid

    async def _handle_subscription_create(self, data: Dict) -> None:
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
                msg="No matching tenant - subscription may have been created before charge.success"
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
        await self.db.commit()
        
        logger.info(
            "subscription_create_processed",
            subscription_code=subscription_code,
            customer_code=customer_code
        )

    async def _handle_charge_success(self, data: Dict) -> None:
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
                email_hash=_email_hash(customer_email)
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
                    email_hash=_email_hash(customer_email)
                )
            else:
                logger.error("webhook_email_lookup_failed", email_hash=_email_hash(customer_email))

        if not tenant_id:
            logger.error("webhook_tenant_lookup_failed_no_identifier", reference=data.get("reference"))
            return

        # In subscription context, data includes authorization (for future charges)
        _ = data.get("authorization", {})
        
        # If this is a subscription charge, we might get plan info
        # plan = data.get("plan", {}) # F841: Local variable `plan` is assigned to but never used
        
        if tenant_id:

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
                from app.shared.core.async_utils import maybe_await
                await maybe_await(self.db.add(sub))
            
            sub.paystack_customer_code = customer_code
            
            # SEC-10: Encrypt and Capture Authorization Code for Dynamic Recurring Billing
            authorization = data.get("authorization", {})
            auth_code = authorization.get("authorization_code")
            if auth_code:
                sub.paystack_auth_code = encrypt_string(auth_code, context="api_key")
                logger.info("paystack_auth_token_encrypted_and_captured", tenant_id=str(tenant_id))

            sub.tier = tier or sub.tier
            sub.status = SubscriptionStatus.ACTIVE.value
            
            await self.db.commit()
            logger.info("paystack_subscription_activated", tenant_id=str(tenant_id))


    async def _handle_subscription_disable(self, data: Dict) -> None:
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

    async def _handle_invoice_failed(self, data: Dict) -> None:
        """Handle failed payment - trigger dunning workflow."""
        invoice_code = data.get("invoice_code")
        subscription_code = data.get("subscription_code")
        customer_code = data.get("customer", {}).get("customer_code")
        
        logger.warning(
            "invoice_payment_failed",
            invoice_code=invoice_code,
            subscription_code=subscription_code,
            customer_code=customer_code,
            msg="Payment failed - initiating dunning workflow"
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
                from app.modules.reporting.domain.billing.dunning_service import DunningService
                dunning = DunningService(self.db)
                await dunning.process_failed_payment(sub.id, is_webhook=True)
                
                logger.info(
                    "dunning_workflow_initiated",
                    tenant_id=str(sub.tenant_id),
                    subscription_code=subscription_code
                )
