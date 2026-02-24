from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException

from app.shared.core.auth import CurrentUser


def tenant_or_403(user: CurrentUser) -> UUID:
    if user.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return user.tenant_id
