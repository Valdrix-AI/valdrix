from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, cast
from uuid import UUID

from fastapi import HTTPException


def decode_approval_token(
    approval_token: str,
    *,
    get_settings_fn: Callable[[], Any],
    jwt_module: Any,
) -> Mapping[str, Any]:
    settings = get_settings_fn()
    primary_secret = str(getattr(settings, "SUPABASE_JWT_SECRET", "") or "").strip()
    if len(primary_secret) < 32:
        raise HTTPException(
            status_code=503,
            detail="Approval token signing key is not configured",
        )
    fallback_secrets = [
        str(value or "").strip()
        for value in list(
            getattr(settings, "ENFORCEMENT_APPROVAL_TOKEN_FALLBACK_SECRETS", []) or []
        )
        if len(str(value or "").strip()) >= 32
    ]
    candidate_secrets: list[str] = []
    for secret in [primary_secret, *fallback_secrets]:
        if secret and secret not in candidate_secrets:
            candidate_secrets.append(secret)

    issuer = str(getattr(settings, "API_URL", "")).rstrip("/")
    expired_error: Exception | None = None
    expired_error_type = getattr(jwt_module, "ExpiredSignatureError")
    invalid_token_type = getattr(jwt_module, "InvalidTokenError")
    for candidate_secret in candidate_secrets:
        try:
            payload = jwt_module.decode(
                approval_token,
                candidate_secret,
                algorithms=["HS256"],
                audience="enforcement_gate",
                issuer=issuer,
                options={
                    "require": [
                        "exp",
                        "iat",
                        "nbf",
                        "tenant_id",
                        "project_id",
                        "decision_id",
                        "approval_id",
                        "source",
                        "environment",
                        "request_fingerprint",
                        "max_monthly_delta_usd",
                        "max_hourly_delta_usd",
                        "resource_reference",
                        "token_type",
                    ]
                },
            )
            token_type = str(payload.get("token_type", "")).strip()
            if token_type != "enforcement_approval":
                continue
            return cast(Mapping[str, Any], payload)
        except expired_error_type as exc:
            expired_error = exc
            continue
        except invalid_token_type:
            continue

    if expired_error is not None:
        raise HTTPException(
            status_code=409,
            detail="Approval token has expired",
        ) from expired_error
    raise HTTPException(
        status_code=401,
        detail="Invalid approval token",
    )


def extract_token_context_payload(
    payload: Mapping[str, Any],
    *,
    source_enum: type[Any],
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[[Any], Decimal],
) -> dict[str, Any]:
    def _uuid_claim(key: str) -> UUID:
        raw = payload.get(key)
        try:
            return UUID(str(raw))
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=401,
                detail="Invalid approval token",
            ) from exc

    source_raw = str(payload.get("source", "")).strip().lower()
    try:
        source = source_enum(source_raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid approval token",
        ) from exc

    try:
        max_monthly_delta = quantize_fn(
            to_decimal_fn(payload.get("max_monthly_delta_usd")),
            "0.0001",
        )
        max_hourly_delta = quantize_fn(
            to_decimal_fn(payload.get("max_hourly_delta_usd")),
            "0.000001",
        )
    except InvalidOperation as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid approval token",
        ) from exc

    exp_raw = payload.get("exp")
    if not isinstance(exp_raw, (int, float, str)):
        raise HTTPException(status_code=401, detail="Invalid approval token")
    try:
        expires_at = datetime.fromtimestamp(int(exp_raw), tz=timezone.utc)
    except (TypeError, ValueError, OSError) as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid approval token",
        ) from exc

    request_fingerprint = str(payload.get("request_fingerprint", "")).strip()
    if len(request_fingerprint) != 64:
        raise HTTPException(status_code=401, detail="Invalid approval token")

    resource_reference = str(payload.get("resource_reference", "")).strip()
    if not resource_reference:
        raise HTTPException(status_code=401, detail="Invalid approval token")
    project_id = str(payload.get("project_id", "")).strip()
    if not project_id:
        raise HTTPException(status_code=401, detail="Invalid approval token")

    return {
        "approval_id": _uuid_claim("approval_id"),
        "decision_id": _uuid_claim("decision_id"),
        "tenant_id": _uuid_claim("tenant_id"),
        "project_id": project_id,
        "source": source,
        "environment": str(payload.get("environment", "")).strip(),
        "request_fingerprint": request_fingerprint,
        "resource_reference": resource_reference,
        "max_monthly_delta_usd": max_monthly_delta,
        "max_hourly_delta_usd": max_hourly_delta,
        "expires_at": expires_at,
    }


def build_approval_token(
    *,
    decision: Any,
    approval: Any,
    expires_at: datetime,
    get_settings_fn: Callable[[], Any],
    utcnow_fn: Callable[[], datetime],
    to_decimal_fn: Callable[[Any], Decimal],
    jwt_module: Any,
) -> str:
    settings = get_settings_fn()
    secret = str(getattr(settings, "SUPABASE_JWT_SECRET", "") or "").strip()
    if len(secret) < 32:
        raise HTTPException(
            status_code=503,
            detail="Approval token signing key is not configured",
        )

    now = utcnow_fn()
    payload: dict[str, Any] = {
        "iss": str(getattr(settings, "API_URL", "")).rstrip("/"),
        "aud": "enforcement_gate",
        "sub": f"enforcement_approval:{approval.id}",
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "tenant_id": str(decision.tenant_id),
        "project_id": decision.project_id,
        "decision_id": str(decision.id),
        "approval_id": str(approval.id),
        "source": decision.source.value,
        "environment": decision.environment,
        "request_fingerprint": decision.request_fingerprint,
        "max_monthly_delta_usd": str(to_decimal_fn(decision.estimated_monthly_delta_usd)),
        "max_hourly_delta_usd": str(to_decimal_fn(decision.estimated_hourly_delta_usd)),
        "resource_reference": decision.resource_reference,
        "token_type": "enforcement_approval",
    }

    headers: dict[str, str] | None = None
    signing_kid = str(getattr(settings, "JWT_SIGNING_KID", "") or "").strip()
    if signing_kid:
        headers = {"kid": signing_kid}

    return cast(
        str,
        jwt_module.encode(
            payload,
            secret,
            algorithm="HS256",
            headers=headers,
        ),
    )
