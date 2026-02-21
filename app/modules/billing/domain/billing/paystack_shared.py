"""Shared runtime state and primitives for Paystack billing modules."""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Optional

import structlog

from app.shared.core.config import get_settings
from app.shared.core.security import decrypt_string as _decrypt_string
from app.shared.core.security import encrypt_string as _encrypt_string

logger = structlog.get_logger()
settings = get_settings()
PAYSTACK_CHECKOUT_CURRENCY = "NGN"
PAYSTACK_FX_PROVIDER = "cbn_nfem"
PAYSTACK_USD_FX_PROVIDER = "native_usd"

encrypt_string = _encrypt_string
decrypt_string = _decrypt_string


class SubscriptionStatus(str, Enum):
    """Paystack subscription statuses."""

    ACTIVE = "active"
    NON_RENEWING = "non-renewing"
    ATTENTION = "attention"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


def email_hash(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:12]
