"""Webhook handler implementation for Paystack billing events."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pricing import TenantSubscription
from app.modules.billing.domain.billing.entitlement_policy import sync_tenant_plan
from app.shared.core.pricing import PricingTier

from . import paystack_shared as shared


class WebhookHandler:
    """Paystack Webhook Handler."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def handle(
        self, request: Request, payload: bytes, signature: str
    ) -> dict[str, str]:
        """Verify and process webhook."""
        from fastapi import HTTPException

        content_type = request.headers.get("Content-Type", "")
        if "application/json" not in content_type.lower():
            shared.logger.warning(
                "paystack_webhook_invalid_content_type", content_type=content_type
            )
            raise HTTPException(400, "Unsupported media type: expected application/json")

        if not self.verify_signature(payload, signature):
            raise HTTPException(401, "Invalid signature")

        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            shared.logger.error("paystack_webhook_invalid_json", payload_len=len(payload))
            raise HTTPException(400, "Invalid JSON payload")

        event_type = event.get("event")
        data = event.get("data", {})

        shared.logger.info("paystack_webhook_received", paystack_event=event_type)

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
            shared.logger.warning("paystack_webhook_missing_signature")
            return False

        if not shared.settings.PAYSTACK_SECRET_KEY:
            shared.logger.error("paystack_secret_key_not_configured")
            return False

        expected = hmac.new(
            shared.settings.PAYSTACK_SECRET_KEY.encode(), payload, hashlib.sha512
        ).hexdigest()

        is_valid = hmac.compare_digest(expected, signature)
        if not is_valid:
            shared.logger.warning(
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
            shared.logger.warning("subscription_create_missing_customer_code", data=data)
            return

        result = await self.db.execute(
            select(TenantSubscription).where(
                TenantSubscription.paystack_customer_code == customer_code
            )
        )
        sub = result.scalar_one_or_none()

        if not sub:
            shared.logger.warning(
                "subscription_create_tenant_not_found",
                customer_code=customer_code,
                msg="No matching tenant - subscription may have been created before charge.success",
            )
            return

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
                shared.logger.warning("invalid_next_payment_date", date=next_payment_date_str)

        sub.status = shared.SubscriptionStatus.ACTIVE.value
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
            shared.logger.warning(
                "billing_audit_log_failed",
                tenant_id=str(sub.tenant_id),
                paystack_event="subscription.create",
                error=str(exc),
            )

        await self.db.commit()

        shared.logger.info(
            "subscription_create_processed",
            subscription_code=subscription_code,
            customer_code=customer_code,
        )

    async def _handle_charge_success(self, data: dict[str, Any]) -> None:
        """Handle successful charge - primary activation point."""
        metadata = data.get("metadata", {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError, ValueError):
                metadata = {}

        tenant_id_str = metadata.get("tenant_id")
        tier = metadata.get("tier")
        shared.logger.info("paystack_webhook_data_parsed", tenant_id=tenant_id_str, tier=tier)

        customer = data.get("customer", {})
        customer_code = customer.get("customer_code")
        customer_email = customer.get("email")
        charge_amount_raw = data.get("amount")
        charge_currency = str(data.get("currency") or shared.PAYSTACK_CHECKOUT_CURRENCY).upper()
        charge_reference = data.get("reference")

        tenant_id = None
        if tenant_id_str:
            try:
                tenant_id = UUID(tenant_id_str)
            except ValueError:
                shared.logger.warning("invalid_tenant_id_in_metadata", tenant_id=tenant_id_str)

        if not tenant_id and customer_email:
            from app.models.tenant import User
            from app.shared.core.security import generate_blind_index

            shared.logger.info(
                "webhook_metadata_missing_attempting_email_lookup",
                email_hash=shared.email_hash(customer_email),
            )
            email_bidx = generate_blind_index(customer_email)

            user_result = await self.db.execute(
                select(User).where(User.email_bidx == email_bidx)
            )
            user = user_result.scalar_one_or_none()
            if user:
                tenant_id = user.tenant_id
                shared.logger.info(
                    "webhook_email_lookup_success",
                    tenant_id=str(tenant_id),
                    email_hash=shared.email_hash(customer_email),
                )
            else:
                shared.logger.error(
                    "webhook_email_lookup_failed",
                    email_hash=shared.email_hash(customer_email),
                )

        if not tenant_id:
            shared.logger.error(
                "webhook_tenant_lookup_failed_no_identifier",
                reference=data.get("reference"),
            )
            return

        if tenant_id:
            resolved_tier: PricingTier | None = None
            if tier:
                try:
                    resolved_tier = PricingTier(str(tier).strip().lower())
                except ValueError:
                    shared.logger.warning(
                        "paystack_webhook_invalid_tier",
                        tenant_id=str(tenant_id),
                        tier=tier,
                    )

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

            authorization = data.get("authorization", {})
            auth_code = authorization.get("authorization_code")
            if auth_code:
                sub.paystack_auth_code = shared.encrypt_string(auth_code, context="api_key")
                shared.logger.info(
                    "paystack_auth_token_encrypted_and_captured",
                    tenant_id=str(tenant_id),
                )

            if resolved_tier is not None:
                sub.tier = resolved_tier.value
            sub.status = shared.SubscriptionStatus.ACTIVE.value
            sub.billing_currency = charge_currency
            if isinstance(charge_amount_raw, (int, float, str)):
                try:
                    sub.last_charge_amount_subunits = int(charge_amount_raw)
                except (TypeError, ValueError):
                    shared.logger.warning(
                        "paystack_charge_amount_invalid",
                        tenant_id=str(tenant_id),
                        amount=charge_amount_raw,
                    )
            fx_rate_raw = metadata.get("exchange_rate")
            if isinstance(fx_rate_raw, (int, float, str)):
                try:
                    sub.last_charge_fx_rate = float(fx_rate_raw)
                except (TypeError, ValueError):
                    shared.logger.warning(
                        "paystack_fx_rate_invalid",
                        tenant_id=str(tenant_id),
                        exchange_rate=fx_rate_raw,
                    )
            fx_provider = metadata.get("fx_provider")
            if isinstance(fx_provider, str) and fx_provider.strip():
                sub.last_charge_fx_provider = fx_provider.strip().lower()
            elif charge_currency == shared.PAYSTACK_CHECKOUT_CURRENCY:
                sub.last_charge_fx_provider = shared.PAYSTACK_FX_PROVIDER
            if charge_reference:
                sub.last_charge_reference = str(charge_reference)
            sub.last_charge_at = datetime.now(timezone.utc)

            if resolved_tier is not None:
                await sync_tenant_plan(
                    db=self.db,
                    tenant_id=tenant_id,
                    tier=resolved_tier,
                    source="paystack_charge_success",
                )

            try:
                from app.modules.governance.domain.security.audit_log import (
                    AuditEventType,
                    AuditLogger,
                )

                reference = data.get("reference")
                correlation_id = str(reference) if reference else None
                audit = AuditLogger(db=self.db, tenant_id=tenant_id, correlation_id=correlation_id)
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
                shared.logger.warning(
                    "billing_audit_log_failed",
                    tenant_id=str(tenant_id),
                    paystack_event="charge.success",
                    error=str(exc),
                )

            await self.db.commit()
            shared.logger.info("paystack_subscription_activated", tenant_id=str(tenant_id))

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
                sub.status = shared.SubscriptionStatus.CANCELLED.value
                sub.canceled_at = datetime.now(timezone.utc)
                await self.db.commit()

    async def _handle_invoice_failed(self, data: dict[str, Any]) -> None:
        """Handle failed payment - trigger dunning workflow."""
        invoice_code = data.get("invoice_code")
        subscription_code = data.get("subscription_code")
        customer_code = data.get("customer", {}).get("customer_code")

        shared.logger.warning(
            "invoice_payment_failed",
            invoice_code=invoice_code,
            subscription_code=subscription_code,
            customer_code=customer_code,
            msg="Payment failed - initiating dunning workflow",
        )

        if subscription_code:
            result = await self.db.execute(
                select(TenantSubscription).where(
                    TenantSubscription.paystack_subscription_code == subscription_code
                )
            )
            sub = result.scalar_one_or_none()

            if sub:
                from app.modules.billing.domain.billing.dunning_service import DunningService

                dunning = DunningService(self.db)
                await dunning.process_failed_payment(sub.id, is_webhook=True)

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
                    shared.logger.warning(
                        "billing_audit_log_failed",
                        tenant_id=str(sub.tenant_id),
                        paystack_event="invoice.payment_failed",
                        error=str(exc),
                    )

                shared.logger.info(
                    "dunning_workflow_initiated",
                    tenant_id=str(sub.tenant_id),
                    subscription_code=subscription_code,
                )
