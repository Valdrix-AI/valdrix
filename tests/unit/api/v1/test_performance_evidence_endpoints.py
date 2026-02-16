import uuid
from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_capture_and_list_load_test_evidence(async_client, app, db, test_tenant):
    from app.shared.core.auth import CurrentUser, get_current_user, UserRole
    from app.shared.core.pricing import PricingTier
    from app.models.tenant import User
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )
    from sqlalchemy import select

    admin_user = CurrentUser(
        id=uuid.uuid4(),
        email="admin-perf@valdrix.io",
        tenant_id=test_tenant.id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    db.add(
        User(
            id=admin_user.id,
            tenant_id=test_tenant.id,
            email=admin_user.email,
            role=UserRole.ADMIN,
        )
    )
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        payload = {
            "profile": "ops",
            "target_url": "http://127.0.0.1:8000",
            "endpoints": ["/health"],
            "duration_seconds": 10,
            "concurrent_users": 2,
            "ramp_up_seconds": 0,
            "request_timeout": 5.0,
            "results": {
                "total_requests": 100,
                "successful_requests": 99,
                "failed_requests": 1,
                "throughput_rps": 10.5,
                "avg_response_time": 0.15,
                "median_response_time": 0.12,
                "p95_response_time": 0.35,
                "p99_response_time": 0.5,
                "min_response_time": 0.01,
                "max_response_time": 1.0,
                "errors_sample": ["HTTP 503: upstream unavailable"],
            },
            "rounds": 2,
            "min_throughput_rps": 9.75,
            "runs": [
                {
                    "run_index": 1,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "results": {
                        "total_requests": 50,
                        "successful_requests": 50,
                        "failed_requests": 0,
                        "throughput_rps": 10.0,
                        "avg_response_time": 0.12,
                        "median_response_time": 0.11,
                        "p95_response_time": 0.25,
                        "p99_response_time": 0.4,
                        "min_response_time": 0.01,
                        "max_response_time": 0.8,
                        "errors_sample": [],
                    },
                }
            ],
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "runner": "scripts/load_test_api.py",
            "meets_targets": False,
            "thresholds": {
                "max_p95_seconds": 0.25,
                "max_error_rate_percent": 0.5,
            },
        }

        resp = await async_client.post(
            "/api/v1/audit/performance/load-test/evidence", json=payload
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "captured"
        assert body["load_test"]["profile"] == "ops"
        assert body["load_test"]["rounds"] == 2

        list_resp = await async_client.get(
            "/api/v1/audit/performance/load-test/evidence", params={"limit": 10}
        )
        assert list_resp.status_code == 200
        listed = list_resp.json()
        assert listed["total"] >= 1
        assert listed["items"][0]["load_test"]["target_url"] == "http://127.0.0.1:8000"

        row = await db.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == test_tenant.id,
                AuditLog.event_type
                == AuditEventType.PERFORMANCE_LOAD_TEST_CAPTURED.value,
            )
        )
        assert row is not None
    finally:
        app.dependency_overrides.pop(get_current_user, None)
