from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.shared.core.exceptions import BudgetExceededError, LLMFairUseExceededError
from app.shared.core.pricing import PricingTier
from app.shared.llm import budget_fair_use


class _MetricStub:
    def __init__(self) -> None:
        self.inc_calls = 0
        self.set_calls = 0

    def labels(self, **_kwargs: object) -> "_MetricStub":
        return self

    def set(self, _value: object) -> None:
        self.set_calls += 1
        return None

    def inc(self) -> None:
        self.inc_calls += 1
        return None


class _DummyManager:
    _local_inflight_counts: dict[str, int] = {}
    _local_inflight_lock = asyncio.Lock()


@pytest.fixture(autouse=True)
def _reset_local_counts() -> None:
    _DummyManager._local_inflight_counts.clear()
    _DummyManager._local_global_abuse_block_until = None


def test_fair_use_daily_soft_cap_parsing() -> None:
    settings = SimpleNamespace(
        LLM_FAIR_USE_PRO_DAILY_SOFT_CAP="1500",
        LLM_FAIR_USE_ENTERPRISE_DAILY_SOFT_CAP=0,
    )
    with patch("app.shared.llm.budget_manager.get_settings", return_value=settings):
        assert budget_fair_use.fair_use_daily_soft_cap(PricingTier.PRO) == 1500
        assert budget_fair_use.fair_use_daily_soft_cap(PricingTier.ENTERPRISE) is None
        assert budget_fair_use.fair_use_daily_soft_cap(PricingTier.FREE) is None


@pytest.mark.asyncio
async def test_count_requests_in_window_with_and_without_end() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    result = MagicMock()
    result.scalar.return_value = 7
    db.execute = AsyncMock(return_value=result)

    start = datetime.now(timezone.utc) - timedelta(days=1)
    end = datetime.now(timezone.utc)

    with_end = await budget_fair_use.count_requests_in_window(
        tenant_id=tenant_id, db=db, start=start, end=end
    )
    no_end = await budget_fair_use.count_requests_in_window(
        tenant_id=tenant_id, db=db, start=start
    )

    assert with_end == 7
    assert no_end == 7
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_acquire_inflight_slot_redis_success_and_over_limit() -> None:
    tenant_id = uuid4()
    redis_client = SimpleNamespace(
        incr=AsyncMock(side_effect=[1, 4]),
        decr=AsyncMock(),
        expire=AsyncMock(),
    )
    cache = SimpleNamespace(enabled=True, client=redis_client)

    with patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache):
        ok, current = await budget_fair_use.acquire_fair_use_inflight_slot(
            _DummyManager, tenant_id, max_inflight=2, ttl_seconds=60
        )
        denied, denied_current = await budget_fair_use.acquire_fair_use_inflight_slot(
            _DummyManager, tenant_id, max_inflight=2, ttl_seconds=60
        )

    assert ok is True
    assert current == 1
    assert denied is False
    assert denied_current == 3
    redis_client.expire.assert_awaited()
    redis_client.decr.assert_awaited_once()


@pytest.mark.asyncio
async def test_acquire_inflight_slot_redis_failure_falls_back_to_local() -> None:
    tenant_id = uuid4()
    redis_client = SimpleNamespace(
        incr=AsyncMock(side_effect=RuntimeError("redis unavailable")),
        decr=AsyncMock(),
        expire=AsyncMock(),
    )
    cache = SimpleNamespace(enabled=True, client=redis_client)

    with patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache):
        ok, current = await budget_fair_use.acquire_fair_use_inflight_slot(
            _DummyManager, tenant_id, max_inflight=2, ttl_seconds=60
        )

    assert ok is True
    assert current == 1
    assert _DummyManager._local_inflight_counts[
        budget_fair_use.fair_use_inflight_key(tenant_id)
    ] == 1


@pytest.mark.asyncio
async def test_release_slot_respects_guards_disabled_and_clears_local() -> None:
    tenant_id = uuid4()
    key = budget_fair_use.fair_use_inflight_key(tenant_id)
    _DummyManager._local_inflight_counts[key] = 3

    settings = SimpleNamespace(LLM_FAIR_USE_GUARDS_ENABLED=False)
    with patch("app.shared.llm.budget_manager.get_settings", return_value=settings):
        await budget_fair_use.release_fair_use_inflight_slot(_DummyManager, tenant_id)

    assert key not in _DummyManager._local_inflight_counts


@pytest.mark.asyncio
async def test_release_slot_redis_negative_counter_is_clamped() -> None:
    tenant_id = uuid4()
    settings = SimpleNamespace(LLM_FAIR_USE_GUARDS_ENABLED=True)
    redis_client = SimpleNamespace(
        decr=AsyncMock(return_value=-1),
        set=AsyncMock(),
    )
    cache = SimpleNamespace(enabled=True, client=redis_client)

    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache),
    ):
        await budget_fair_use.release_fair_use_inflight_slot(_DummyManager, tenant_id)

    redis_client.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_release_slot_redis_failure_falls_back_to_local_decrement() -> None:
    tenant_id = uuid4()
    key = budget_fair_use.fair_use_inflight_key(tenant_id)
    _DummyManager._local_inflight_counts[key] = 2

    settings = SimpleNamespace(LLM_FAIR_USE_GUARDS_ENABLED=True)
    redis_client = SimpleNamespace(decr=AsyncMock(side_effect=RuntimeError("boom")))
    cache = SimpleNamespace(enabled=True, client=redis_client)

    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache),
    ):
        await budget_fair_use.release_fair_use_inflight_slot(_DummyManager, tenant_id)

    assert _DummyManager._local_inflight_counts[key] == 1


@pytest.mark.asyncio
async def test_enforce_daily_analysis_limit_invalid_or_exhausted_limits() -> None:
    tenant_id = uuid4()
    db = AsyncMock()

    with (
        patch("app.shared.llm.budget_manager.get_tenant_tier", new=AsyncMock(return_value=PricingTier.PRO)),
        patch("app.shared.core.pricing.get_tier_limit", return_value="invalid"),
        patch("app.shared.llm.budget_fair_use.count_requests_in_window", new=AsyncMock()) as count_window,
    ):
        await budget_fair_use.enforce_daily_analysis_limit(_DummyManager, tenant_id, db)
        count_window.assert_not_awaited()

    with (
        patch("app.shared.llm.budget_manager.get_tenant_tier", new=AsyncMock(return_value=PricingTier.PRO)),
        patch("app.shared.core.pricing.get_tier_limit", return_value=0),
    ):
        with pytest.raises(BudgetExceededError):
            await budget_fair_use.enforce_daily_analysis_limit(_DummyManager, tenant_id, db)


@pytest.mark.asyncio
async def test_enforce_daily_analysis_limit_requires_user_context_for_user_actor() -> None:
    tenant_id = uuid4()
    db = AsyncMock()

    with pytest.raises(BudgetExceededError) as exc:
        await budget_fair_use.enforce_daily_analysis_limit(
            _DummyManager,
            tenant_id,
            db,
            user_id=None,
            actor_type="user",
        )
    assert exc.value.details.get("gate") == "actor_context"


@pytest.mark.asyncio
async def test_enforce_daily_analysis_limit_enforces_system_cap() -> None:
    tenant_id = uuid4()
    db = AsyncMock()

    def _tier_limit_side_effect(_tier: PricingTier, key: str):
        mapping = {
            "llm_analyses_per_day": 100,
            "llm_system_analyses_per_day": 1,
        }
        return mapping.get(key)

    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=PricingTier.STARTER),
        ),
        patch(
            "app.shared.core.pricing.get_tier_limit",
            side_effect=_tier_limit_side_effect,
        ),
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(side_effect=[0, 1]),
        ),
    ):
        with pytest.raises(BudgetExceededError) as exc:
            await budget_fair_use.enforce_daily_analysis_limit(
                _DummyManager,
                tenant_id,
                db,
                actor_type="system",
            )
    assert exc.value.details.get("gate") == "daily_system"

    with (
        patch("app.shared.llm.budget_manager.get_tenant_tier", new=AsyncMock(return_value=PricingTier.PRO)),
        patch("app.shared.core.pricing.get_tier_limit", return_value=2),
        patch("app.shared.llm.budget_fair_use.count_requests_in_window", new=AsyncMock(return_value=2)),
    ):
        with pytest.raises(BudgetExceededError):
            await budget_fair_use.enforce_daily_analysis_limit(_DummyManager, tenant_id, db)


@pytest.mark.asyncio
async def test_enforce_fair_use_guards_disabled_or_unsupported_tier() -> None:
    tenant_id = uuid4()
    db = AsyncMock()

    settings_disabled = SimpleNamespace(LLM_FAIR_USE_GUARDS_ENABLED=False)
    with patch("app.shared.llm.budget_manager.get_settings", return_value=settings_disabled):
        assert (
            await budget_fair_use.enforce_fair_use_guards(
                _DummyManager, tenant_id, db, PricingTier.PRO
            )
            is False
        )

    settings_enabled = SimpleNamespace(LLM_FAIR_USE_GUARDS_ENABLED=True)
    with patch("app.shared.llm.budget_manager.get_settings", return_value=settings_enabled):
        assert (
            await budget_fair_use.enforce_fair_use_guards(
                _DummyManager, tenant_id, db, PricingTier.FREE
            )
            is False
        )


def test_classify_client_ip_risk_buckets() -> None:
    assert budget_fair_use._classify_client_ip(None) == ("unknown", 50)
    assert budget_fair_use._classify_client_ip("not-an-ip") == ("invalid", 80)
    assert budget_fair_use._classify_client_ip("127.0.0.1")[0] == "loopback"
    assert budget_fair_use._classify_client_ip("10.0.0.5")[0] == "private"
    assert budget_fair_use._classify_client_ip("8.8.8.8")[0] == "public_v4"


@pytest.mark.asyncio
async def test_record_authenticated_abuse_signal_metrics_and_high_risk_audit() -> None:
    tenant_id = uuid4()
    metric = _MetricStub()
    with (
        patch("app.shared.llm.budget_manager.LLM_AUTH_ABUSE_SIGNALS", metric),
        patch("app.shared.llm.budget_manager.LLM_AUTH_IP_RISK_SCORE", metric),
        patch("app.shared.llm.budget_manager.audit_log") as mock_audit,
    ):
        await budget_fair_use.record_authenticated_abuse_signal(
            manager_cls=_DummyManager,
            tenant_id=tenant_id,
            db=AsyncMock(),
            tier=PricingTier.PRO,
            actor_type="user",
            user_id=uuid4(),
            client_ip="127.0.0.1",
        )
    assert metric.inc_calls == 1
    assert metric.set_calls == 1
    mock_audit.assert_called_once()


@pytest.mark.asyncio
async def test_enforce_fair_use_guards_soft_daily_and_concurrency_paths() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    metric = _MetricStub()
    settings = SimpleNamespace(
        LLM_FAIR_USE_GUARDS_ENABLED=True,
        LLM_FAIR_USE_PRO_DAILY_SOFT_CAP=2,
        LLM_FAIR_USE_ENTERPRISE_DAILY_SOFT_CAP=5,
        LLM_FAIR_USE_PER_MINUTE_CAP=0,
        LLM_FAIR_USE_PER_TENANT_CONCURRENCY_CAP=1,
        LLM_FAIR_USE_CONCURRENCY_LEASE_TTL_SECONDS=45,
    )

    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_OBSERVED", metric),
        patch("app.shared.llm.budget_manager.LLM_PRE_AUTH_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_EVALUATIONS", metric),
        patch("app.shared.llm.budget_manager.audit_log"),
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(return_value=2),
        ),
    ):
        with pytest.raises(LLMFairUseExceededError) as daily_exc:
            await budget_fair_use.enforce_fair_use_guards(
                _DummyManager, tenant_id, db, PricingTier.PRO
            )
    assert daily_exc.value.details.get("gate") == "soft_daily"

    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_OBSERVED", metric),
        patch("app.shared.llm.budget_manager.LLM_PRE_AUTH_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_EVALUATIONS", metric),
        patch("app.shared.llm.budget_manager.audit_log"),
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(return_value=0),
        ),
        patch(
            "app.shared.llm.budget_fair_use.acquire_fair_use_inflight_slot",
            new=AsyncMock(return_value=(False, 3)),
        ),
    ):
        with pytest.raises(LLMFairUseExceededError) as conc_exc:
            await budget_fair_use.enforce_fair_use_guards(
                _DummyManager, tenant_id, db, PricingTier.PRO
            )
    assert conc_exc.value.details.get("gate") == "concurrency"


@pytest.mark.asyncio
async def test_enforce_fair_use_guards_allow_path_with_invalid_per_minute_cap() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    metric = _MetricStub()
    settings = SimpleNamespace(
        LLM_FAIR_USE_GUARDS_ENABLED=True,
        LLM_FAIR_USE_PRO_DAILY_SOFT_CAP=100,
        LLM_FAIR_USE_ENTERPRISE_DAILY_SOFT_CAP=100,
        LLM_FAIR_USE_PER_MINUTE_CAP="invalid",
        LLM_FAIR_USE_PER_TENANT_CONCURRENCY_CAP=0,
        LLM_FAIR_USE_CONCURRENCY_LEASE_TTL_SECONDS="invalid",
    )

    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_OBSERVED", metric),
        patch("app.shared.llm.budget_manager.LLM_PRE_AUTH_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_EVALUATIONS", metric),
        patch("app.shared.llm.budget_manager.audit_log"),
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(return_value=0),
        ),
    ):
        acquired = await budget_fair_use.enforce_fair_use_guards(
            _DummyManager, tenant_id, db, PricingTier.PRO
        )

    assert acquired is False


@pytest.mark.asyncio
async def test_enforce_daily_analysis_limit_applies_per_user_quota() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    db = AsyncMock()
    metric = _MetricStub()

    def _tier_limit(_tier: PricingTier, limit_name: str) -> int:
        if limit_name == "llm_analyses_per_day":
            return 10
        if limit_name == "llm_analyses_per_user_per_day":
            return 1
        return 0

    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=PricingTier.PRO),
        ),
        patch("app.shared.core.pricing.get_tier_limit", side_effect=_tier_limit),
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(side_effect=[0, 1]),
        ),
        patch("app.shared.llm.budget_manager.LLM_PRE_AUTH_DENIALS", metric),
        patch("app.shared.llm.budget_manager.audit_log"),
    ):
        with pytest.raises(BudgetExceededError) as exc:
            await budget_fair_use.enforce_daily_analysis_limit(
                _DummyManager,
                tenant_id,
                db,
                user_id=user_id,
            )

    assert exc.value.details.get("gate") == "daily_user"
    assert exc.value.details.get("daily_user_limit") == 1
    assert exc.value.details.get("user_requests_today") == 1


@pytest.mark.asyncio
async def test_enforce_global_abuse_guard_triggers_burst_block() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    metric = _MetricStub()
    _DummyManager._local_global_abuse_block_until = None
    settings = SimpleNamespace(
        LLM_GLOBAL_ABUSE_GUARDS_ENABLED=True,
        LLM_GLOBAL_ABUSE_KILL_SWITCH=False,
        LLM_GLOBAL_ABUSE_PER_MINUTE_CAP=9,
        LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD=3,
        LLM_GLOBAL_ABUSE_BLOCK_SECONDS=60,
    )
    result = MagicMock()
    result.one_or_none.return_value = (9, 3)
    db.execute = AsyncMock(return_value=result)
    cache = SimpleNamespace(enabled=False, client=None)

    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_OBSERVED", metric),
        patch("app.shared.llm.budget_manager.LLM_PRE_AUTH_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_EVALUATIONS", metric),
        patch("app.shared.llm.budget_manager.audit_log"),
    ):
        with pytest.raises(LLMFairUseExceededError) as exc:
            await budget_fair_use.enforce_global_abuse_guard(
                _DummyManager,
                tenant_id,
                db,
                PricingTier.PRO,
            )

    assert exc.value.details.get("gate") == "global_abuse"
    assert exc.value.details.get("reason") == "burst_detected"


@pytest.mark.asyncio
async def test_enforce_global_abuse_guard_kill_switch() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    metric = _MetricStub()
    settings = SimpleNamespace(
        LLM_GLOBAL_ABUSE_GUARDS_ENABLED=True,
        LLM_GLOBAL_ABUSE_KILL_SWITCH=True,
        LLM_GLOBAL_ABUSE_PER_MINUTE_CAP=9,
        LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD=3,
        LLM_GLOBAL_ABUSE_BLOCK_SECONDS=60,
    )

    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch("app.shared.llm.budget_manager.LLM_PRE_AUTH_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_EVALUATIONS", metric),
    ):
        with pytest.raises(LLMFairUseExceededError) as exc:
            await budget_fair_use.enforce_global_abuse_guard(
                _DummyManager,
                tenant_id,
                db,
                PricingTier.PRO,
            )

    assert exc.value.details.get("reason") == "kill_switch"


def test_as_bool_and_as_int_edge_cases() -> None:
    assert budget_fair_use._as_bool(True, default=False) is True
    assert budget_fair_use._as_bool(0, default=True) is False
    assert budget_fair_use._as_bool("yes", default=False) is True
    assert budget_fair_use._as_bool("off", default=True) is False
    assert budget_fair_use._as_bool("not-a-bool", default=True) is True
    assert budget_fair_use._as_bool(object(), default=False) is False

    assert budget_fair_use._as_int(True, default=7) == 7
    assert budget_fair_use._as_int(5, default=0) == 5
    assert budget_fair_use._as_int(5.9, default=0) == 5
    assert budget_fair_use._as_int(" 19 ", default=0) == 19
    assert budget_fair_use._as_int("bad", default=3) == 3
    assert budget_fair_use._as_int(object(), default=2) == 2


def test_fair_use_daily_soft_cap_invalid_values() -> None:
    settings = SimpleNamespace(
        LLM_FAIR_USE_PRO_DAILY_SOFT_CAP="not-a-number",
        LLM_FAIR_USE_ENTERPRISE_DAILY_SOFT_CAP="-10",
    )
    with patch("app.shared.llm.budget_manager.get_settings", return_value=settings):
        assert budget_fair_use.fair_use_daily_soft_cap(PricingTier.PRO) is None
        assert budget_fair_use.fair_use_daily_soft_cap(PricingTier.ENTERPRISE) is None


@pytest.mark.asyncio
async def test_count_requests_in_window_user_filter_and_none_scalar() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    result = MagicMock()
    result.scalar.return_value = None
    db.execute = AsyncMock(return_value=result)

    value = await budget_fair_use.count_requests_in_window(
        tenant_id=tenant_id,
        db=db,
        start=datetime.now(timezone.utc) - timedelta(minutes=5),
        end=datetime.now(timezone.utc),
        user_id=uuid4(),
    )

    assert value == 0
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_enforce_daily_analysis_limit_short_circuit_paths() -> None:
    tenant_id = uuid4()
    db = AsyncMock()

    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=PricingTier.PRO),
        ),
        patch("app.shared.core.pricing.get_tier_limit", return_value=None),
    ):
        await budget_fair_use.enforce_daily_analysis_limit(_DummyManager, tenant_id, db)

    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=PricingTier.PRO),
        ),
        patch("app.shared.core.pricing.get_tier_limit", return_value=10),
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(return_value=1),
        ),
    ):
        await budget_fair_use.enforce_daily_analysis_limit(_DummyManager, tenant_id, db)


@pytest.mark.asyncio
async def test_enforce_daily_analysis_limit_user_limit_edges() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    db = AsyncMock()
    metric = _MetricStub()

    def _invalid_user_limit(_tier: PricingTier, limit_name: str) -> object:
        if limit_name == "llm_analyses_per_day":
            return 10
        if limit_name == "llm_analyses_per_user_per_day":
            return "invalid"
        return None

    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=PricingTier.PRO),
        ),
        patch("app.shared.core.pricing.get_tier_limit", side_effect=_invalid_user_limit),
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(return_value=1),
        ),
    ):
        await budget_fair_use.enforce_daily_analysis_limit(
            _DummyManager, tenant_id, db, user_id=user_id
        )

    def _zero_user_limit(_tier: PricingTier, limit_name: str) -> object:
        if limit_name == "llm_analyses_per_day":
            return 10
        if limit_name == "llm_analyses_per_user_per_day":
            return 0
        return None

    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=PricingTier.PRO),
        ),
        patch("app.shared.core.pricing.get_tier_limit", side_effect=_zero_user_limit),
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(return_value=0),
        ),
        patch("app.shared.llm.budget_manager.LLM_PRE_AUTH_DENIALS", metric),
        patch("app.shared.llm.budget_manager.audit_log"),
    ):
        with pytest.raises(BudgetExceededError) as exc:
            await budget_fair_use.enforce_daily_analysis_limit(
                _DummyManager, tenant_id, db, user_id=user_id
            )
    assert exc.value.details.get("gate") == "daily_user"
    assert exc.value.details.get("user_requests_today") == 0

    def _valid_user_limit(_tier: PricingTier, limit_name: str) -> object:
        if limit_name == "llm_analyses_per_day":
            return 10
        if limit_name == "llm_analyses_per_user_per_day":
            return 5
        return None

    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=PricingTier.PRO),
        ),
        patch("app.shared.core.pricing.get_tier_limit", side_effect=_valid_user_limit),
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(side_effect=[1, 2]),
        ),
    ):
        await budget_fair_use.enforce_daily_analysis_limit(
            _DummyManager, tenant_id, db, user_id=user_id
        )


@pytest.mark.asyncio
async def test_enforce_global_abuse_guard_disabled_and_temporal_block() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    metric = _MetricStub()

    disabled = SimpleNamespace(LLM_GLOBAL_ABUSE_GUARDS_ENABLED=False)
    with patch("app.shared.llm.budget_manager.get_settings", return_value=disabled):
        await budget_fair_use.enforce_global_abuse_guard(
            _DummyManager, tenant_id, db, PricingTier.PRO
        )

    settings = SimpleNamespace(
        LLM_GLOBAL_ABUSE_GUARDS_ENABLED=True,
        LLM_GLOBAL_ABUSE_KILL_SWITCH=False,
        LLM_GLOBAL_ABUSE_PER_MINUTE_CAP=999,
        LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD=999,
        LLM_GLOBAL_ABUSE_BLOCK_SECONDS=90,
    )
    _DummyManager._local_global_abuse_block_until = datetime.now(timezone.utc) + timedelta(
        seconds=120
    )
    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch("app.shared.llm.budget_manager.LLM_PRE_AUTH_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_EVALUATIONS", metric),
    ):
        with pytest.raises(LLMFairUseExceededError) as exc:
            await budget_fair_use.enforce_global_abuse_guard(
                _DummyManager, tenant_id, db, PricingTier.PRO
            )
    assert exc.value.details.get("reason") == "temporal_block"


@pytest.mark.asyncio
async def test_enforce_global_abuse_guard_cache_get_and_result_fallbacks() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    metric = _MetricStub()
    settings = SimpleNamespace(
        LLM_GLOBAL_ABUSE_GUARDS_ENABLED=True,
        LLM_GLOBAL_ABUSE_KILL_SWITCH=False,
        LLM_GLOBAL_ABUSE_PER_MINUTE_CAP=100,
        LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD=100,
        LLM_GLOBAL_ABUSE_BLOCK_SECONDS=60,
    )

    cache_blocking = SimpleNamespace(
        enabled=True,
        client=SimpleNamespace(get=AsyncMock(return_value="1")),
    )
    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache_blocking),
        patch("app.shared.llm.budget_manager.LLM_PRE_AUTH_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_EVALUATIONS", metric),
    ):
        with pytest.raises(LLMFairUseExceededError) as exc:
            await budget_fair_use.enforce_global_abuse_guard(
                _DummyManager, tenant_id, db, PricingTier.PRO
            )
    assert exc.value.details.get("reason") == "temporal_block"

    # Force result fallback path: no one_or_none(), first() returns None.
    result = SimpleNamespace(first=lambda: None)
    db.execute = AsyncMock(return_value=result)
    cache_erroring = SimpleNamespace(
        enabled=True,
        client=SimpleNamespace(get=AsyncMock(side_effect=RuntimeError("redis-get-error"))),
    )
    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache_erroring),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_OBSERVED", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_EVALUATIONS", metric),
    ):
        await budget_fair_use.enforce_global_abuse_guard(
            _DummyManager, tenant_id, db, PricingTier.PRO
        )


@pytest.mark.asyncio
async def test_enforce_global_abuse_guard_trigger_with_cache_set_failure() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    metric = _MetricStub()
    settings = SimpleNamespace(
        LLM_GLOBAL_ABUSE_GUARDS_ENABLED=True,
        LLM_GLOBAL_ABUSE_KILL_SWITCH=False,
        LLM_GLOBAL_ABUSE_PER_MINUTE_CAP=1,
        LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD=1,
        LLM_GLOBAL_ABUSE_BLOCK_SECONDS=30,
    )
    result = MagicMock()
    result.one_or_none.return_value = (5, 2)
    db.execute = AsyncMock(return_value=result)
    cache = SimpleNamespace(
        enabled=True,
        client=SimpleNamespace(
            get=AsyncMock(return_value=None),
            set=AsyncMock(side_effect=RuntimeError("redis-set-error")),
        ),
    )

    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_OBSERVED", metric),
        patch("app.shared.llm.budget_manager.LLM_PRE_AUTH_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_EVALUATIONS", metric),
        patch("app.shared.llm.budget_manager.audit_log"),
    ):
        with pytest.raises(LLMFairUseExceededError) as exc:
            await budget_fair_use.enforce_global_abuse_guard(
                _DummyManager, tenant_id, db, PricingTier.PRO
            )
    assert exc.value.details.get("reason") == "burst_detected"


@pytest.mark.asyncio
async def test_acquire_slot_additional_cache_and_local_branches() -> None:
    tenant_id = uuid4()

    # Callable incr/decr but non-callable expire should still succeed.
    cache_no_expire = SimpleNamespace(
        enabled=True,
        client=SimpleNamespace(
            incr=AsyncMock(return_value=1),
            decr=AsyncMock(),
            expire=None,
        ),
    )
    with patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache_no_expire):
        ok, current = await budget_fair_use.acquire_fair_use_inflight_slot(
            _DummyManager, tenant_id, max_inflight=2, ttl_seconds=60
        )
    assert ok is True
    assert current == 1

    # Missing decr callable falls back to local lock/count map.
    cache_missing_decr = SimpleNamespace(
        enabled=True,
        client=SimpleNamespace(incr=AsyncMock(return_value=1)),
    )
    with patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache_missing_decr):
        ok_local, current_local = await budget_fair_use.acquire_fair_use_inflight_slot(
            _DummyManager, tenant_id, max_inflight=1, ttl_seconds=60
        )
    assert ok_local is True
    assert current_local >= 1

    # Pure local over-limit branch.
    local_tenant_id = uuid4()
    cache_disabled = SimpleNamespace(enabled=False, client=None)
    with patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache_disabled):
        allowed, _ = await budget_fair_use.acquire_fair_use_inflight_slot(
            _DummyManager, local_tenant_id, max_inflight=1, ttl_seconds=60
        )
        denied, denied_current = await budget_fair_use.acquire_fair_use_inflight_slot(
            _DummyManager, local_tenant_id, max_inflight=1, ttl_seconds=60
        )
    assert allowed is True
    assert denied is False
    assert denied_current >= 0


@pytest.mark.asyncio
async def test_release_slot_additional_local_fallback_paths() -> None:
    tenant_id = uuid4()
    key = budget_fair_use.fair_use_inflight_key(tenant_id)
    _DummyManager._local_inflight_counts[key] = 1

    settings = SimpleNamespace(LLM_FAIR_USE_GUARDS_ENABLED=True)
    cache_without_decr = SimpleNamespace(enabled=True, client=SimpleNamespace(decr=None))
    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch(
            "app.shared.llm.budget_manager.get_cache_service",
            return_value=cache_without_decr,
        ),
    ):
        await budget_fair_use.release_fair_use_inflight_slot(_DummyManager, tenant_id)
    assert key not in _DummyManager._local_inflight_counts

    # Negative decr but non-callable set path.
    _DummyManager._local_inflight_counts[key] = 2
    cache_negative_no_set = SimpleNamespace(
        enabled=True,
        client=SimpleNamespace(decr=AsyncMock(return_value=-2), set=None),
    )
    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch(
            "app.shared.llm.budget_manager.get_cache_service",
            return_value=cache_negative_no_set,
        ),
    ):
        await budget_fair_use.release_fair_use_inflight_slot(_DummyManager, tenant_id)


@pytest.mark.asyncio
async def test_enforce_fair_use_guards_per_minute_and_concurrency_edges() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    metric = _MetricStub()

    per_minute_settings = SimpleNamespace(
        LLM_FAIR_USE_GUARDS_ENABLED=True,
        LLM_FAIR_USE_PRO_DAILY_SOFT_CAP="invalid",
        LLM_FAIR_USE_ENTERPRISE_DAILY_SOFT_CAP="invalid",
        LLM_FAIR_USE_PER_MINUTE_CAP=1,
        LLM_FAIR_USE_PER_TENANT_CONCURRENCY_CAP=2,
        LLM_FAIR_USE_CONCURRENCY_LEASE_TTL_SECONDS=45,
    )
    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=per_minute_settings),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_OBSERVED", metric),
        patch("app.shared.llm.budget_manager.LLM_PRE_AUTH_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_EVALUATIONS", metric),
        patch("app.shared.llm.budget_manager.audit_log"),
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(return_value=1),
        ),
    ):
        with pytest.raises(LLMFairUseExceededError) as exc:
            await budget_fair_use.enforce_fair_use_guards(
                _DummyManager, tenant_id, db, PricingTier.PRO
            )
    assert exc.value.details.get("gate") == "per_minute"

    invalid_concurrency_settings = SimpleNamespace(
        LLM_FAIR_USE_GUARDS_ENABLED=True,
        LLM_FAIR_USE_PRO_DAILY_SOFT_CAP=100,
        LLM_FAIR_USE_ENTERPRISE_DAILY_SOFT_CAP=100,
        LLM_FAIR_USE_PER_MINUTE_CAP=0,
        LLM_FAIR_USE_PER_TENANT_CONCURRENCY_CAP="bad",
        LLM_FAIR_USE_CONCURRENCY_LEASE_TTL_SECONDS=45,
    )
    with (
        patch(
            "app.shared.llm.budget_manager.get_settings",
            return_value=invalid_concurrency_settings,
        ),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_OBSERVED", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_EVALUATIONS", metric),
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(return_value=0),
        ),
    ):
        assert (
            await budget_fair_use.enforce_fair_use_guards(
                _DummyManager, tenant_id, db, PricingTier.PRO
            )
            is False
        )

    invalid_ttl_settings = SimpleNamespace(
        LLM_FAIR_USE_GUARDS_ENABLED=True,
        LLM_FAIR_USE_PRO_DAILY_SOFT_CAP=100,
        LLM_FAIR_USE_ENTERPRISE_DAILY_SOFT_CAP=100,
        LLM_FAIR_USE_PER_MINUTE_CAP=0,
        LLM_FAIR_USE_PER_TENANT_CONCURRENCY_CAP=2,
        LLM_FAIR_USE_CONCURRENCY_LEASE_TTL_SECONDS="bad",
    )
    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=invalid_ttl_settings),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_OBSERVED", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_EVALUATIONS", metric),
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(return_value=0),
        ),
        patch(
            "app.shared.llm.budget_fair_use.acquire_fair_use_inflight_slot",
            new=AsyncMock(return_value=(True, 1)),
        ),
    ):
        assert (
            await budget_fair_use.enforce_fair_use_guards(
                _DummyManager, tenant_id, db, PricingTier.PRO
            )
            is True
        )


@pytest.mark.asyncio
async def test_count_requests_and_daily_limit_normalization_branches() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar=lambda: 0))

    # Covers actor_type normalization branch in count_requests_in_window.
    await budget_fair_use.count_requests_in_window(
        tenant_id=tenant_id,
        db=db,
        start=datetime.now(timezone.utc) - timedelta(hours=1),
        actor_type="user",
    )

    # Covers invalid actor_type fallback in daily limit enforcement.
    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=PricingTier.PRO),
        ),
        patch("app.shared.core.pricing.get_tier_limit", return_value=None),
    ):
        await budget_fair_use.enforce_daily_analysis_limit(
            _DummyManager,
            tenant_id,
            db,
            actor_type="invalid",
        )

    # Covers system-actor branch where system limit is absent.
    def _no_system_limit(_tier: PricingTier, key: str) -> object:
        if key == "llm_analyses_per_day":
            return 10
        if key == "llm_system_analyses_per_day":
            return None
        return None

    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=PricingTier.PRO),
        ),
        patch("app.shared.core.pricing.get_tier_limit", side_effect=_no_system_limit),
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(return_value=0),
        ),
    ):
        await budget_fair_use.enforce_daily_analysis_limit(
            _DummyManager,
            tenant_id,
            db,
            actor_type="system",
        )


@pytest.mark.asyncio
async def test_enforce_daily_limit_system_and_user_short_circuit_branches() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    metric = _MetricStub()

    def _invalid_system_limit(_tier: PricingTier, key: str) -> object:
        if key == "llm_analyses_per_day":
            return 5
        if key == "llm_system_analyses_per_day":
            return "invalid"
        return None

    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=PricingTier.PRO),
        ),
        patch("app.shared.core.pricing.get_tier_limit", side_effect=_invalid_system_limit),
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(return_value=0),
        ),
    ):
        await budget_fair_use.enforce_daily_analysis_limit(
            _DummyManager,
            tenant_id,
            db,
            actor_type="system",
        )

    def _zero_system_limit(_tier: PricingTier, key: str) -> object:
        if key == "llm_analyses_per_day":
            return 5
        if key == "llm_system_analyses_per_day":
            return 0
        return None

    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=PricingTier.PRO),
        ),
        patch("app.shared.core.pricing.get_tier_limit", side_effect=_zero_system_limit),
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(return_value=0),
        ),
        patch("app.shared.llm.budget_manager.LLM_PRE_AUTH_DENIALS", metric),
    ):
        with pytest.raises(BudgetExceededError) as exc:
            await budget_fair_use.enforce_daily_analysis_limit(
                _DummyManager,
                tenant_id,
                db,
                actor_type="system",
            )
    assert exc.value.details["gate"] == "daily_system"

    def _no_user_limit(_tier: PricingTier, key: str) -> object:
        if key == "llm_analyses_per_day":
            return 5
        if key == "llm_analyses_per_user_per_day":
            return None
        return None

    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=PricingTier.PRO),
        ),
        patch("app.shared.core.pricing.get_tier_limit", side_effect=_no_user_limit),
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(return_value=0),
        ),
    ):
        await budget_fair_use.enforce_daily_analysis_limit(
            _DummyManager,
            tenant_id,
            db,
            user_id=uuid4(),
        )

    # user_id absent short-circuit.
    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=PricingTier.PRO),
        ),
        patch("app.shared.core.pricing.get_tier_limit", return_value=5),
        patch(
            "app.shared.llm.budget_fair_use.count_requests_in_window",
            new=AsyncMock(return_value=0),
        ),
    ):
        await budget_fair_use.enforce_daily_analysis_limit(
            _DummyManager,
            tenant_id,
            db,
            user_id=None,
            actor_type="system",
        )


def test_classify_ip_additional_buckets() -> None:
    assert budget_fair_use._classify_client_ip("169.254.10.10")[0] == "link_local"
    assert budget_fair_use._classify_client_ip("ff00::1")[0] == "reserved"
    assert budget_fair_use._classify_client_ip("2001:4860:4860::8888")[0] == "public_v6"


@pytest.mark.asyncio
async def test_record_authenticated_abuse_signal_low_risk_and_actor_normalization() -> None:
    tenant_id = uuid4()
    metric = _MetricStub()
    with (
        patch("app.shared.llm.budget_manager.LLM_AUTH_ABUSE_SIGNALS", metric),
        patch("app.shared.llm.budget_manager.LLM_AUTH_IP_RISK_SCORE", metric),
        patch("app.shared.llm.budget_manager.audit_log") as mock_audit,
    ):
        await budget_fair_use.record_authenticated_abuse_signal(
            manager_cls=_DummyManager,
            tenant_id=tenant_id,
            db=AsyncMock(),
            tier=PricingTier.PRO,
            actor_type="unknown",
            user_id=uuid4(),
            client_ip="10.0.0.8",
        )
    # private IP => risk < 70 => no audit
    mock_audit.assert_not_called()


@pytest.mark.asyncio
async def test_record_authenticated_abuse_signal_system_actor_with_user_id_normalizes() -> None:
    tenant_id = uuid4()
    metric = _MetricStub()
    with (
        patch("app.shared.llm.budget_manager.LLM_AUTH_ABUSE_SIGNALS", metric),
        patch("app.shared.llm.budget_manager.LLM_AUTH_IP_RISK_SCORE", metric),
        patch("app.shared.llm.budget_manager.audit_log") as mock_audit,
    ):
        await budget_fair_use.record_authenticated_abuse_signal(
            manager_cls=_DummyManager,
            tenant_id=tenant_id,
            db=AsyncMock(),
            tier=PricingTier.PRO,
            actor_type="system",
            user_id=uuid4(),
            client_ip="10.1.0.1",
        )
    # normalized to user; low risk so no audit.
    mock_audit.assert_not_called()


@pytest.mark.asyncio
async def test_global_abuse_guard_row_parsing_and_cache_set_non_callable() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    metric = _MetricStub()
    settings = SimpleNamespace(
        LLM_GLOBAL_ABUSE_GUARDS_ENABLED=True,
        LLM_GLOBAL_ABUSE_KILL_SWITCH=False,
        LLM_GLOBAL_ABUSE_PER_MINUTE_CAP=1,
        LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD=1,
        LLM_GLOBAL_ABUSE_BLOCK_SECONDS=45,
    )

    # Covers first() fallback and int parsing exceptions.
    result = SimpleNamespace(first=lambda: ("not-int", object()))
    db.execute = AsyncMock(return_value=result)
    cache = SimpleNamespace(enabled=False, client=None)
    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_OBSERVED", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_EVALUATIONS", metric),
    ):
        await budget_fair_use.enforce_global_abuse_guard(
            _DummyManager, tenant_id, db, PricingTier.PRO
        )

    # Covers triggered path with cache.set non-callable branch.
    result_triggered = MagicMock()
    result_triggered.one_or_none.return_value = (5, 5)
    db.execute = AsyncMock(return_value=result_triggered)
    cache_non_callable_set = SimpleNamespace(
        enabled=True,
        client=SimpleNamespace(get=AsyncMock(return_value=None), set=None),
    )
    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch(
            "app.shared.llm.budget_manager.get_cache_service",
            return_value=cache_non_callable_set,
        ),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_OBSERVED", metric),
        patch("app.shared.llm.budget_manager.LLM_PRE_AUTH_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_DENIALS", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_EVALUATIONS", metric),
        patch("app.shared.llm.budget_manager.audit_log"),
    ):
        with pytest.raises(LLMFairUseExceededError):
            await budget_fair_use.enforce_global_abuse_guard(
                _DummyManager, tenant_id, db, PricingTier.PRO
            )


@pytest.mark.asyncio
async def test_inflight_slot_local_zero_pop_and_release_non_negative_decr() -> None:
    tenant_id = uuid4()
    cache_disabled = SimpleNamespace(enabled=False, client=None)
    with patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache_disabled):
        # max_inflight=0 forces over-limit path with next_value=0 => pop()
        ok, current = await budget_fair_use.acquire_fair_use_inflight_slot(
            _DummyManager, tenant_id, max_inflight=0, ttl_seconds=30
        )
    assert ok is False
    assert current == 0

    # Covers release path where decr is callable and current is not negative.
    settings = SimpleNamespace(LLM_FAIR_USE_GUARDS_ENABLED=True)
    cache_non_negative = SimpleNamespace(
        enabled=True,
        client=SimpleNamespace(decr=AsyncMock(return_value=0)),
    )
    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch(
            "app.shared.llm.budget_manager.get_cache_service",
            return_value=cache_non_negative,
        ),
    ):
        await budget_fair_use.release_fair_use_inflight_slot(_DummyManager, tenant_id)


@pytest.mark.asyncio
async def test_global_abuse_guard_result_without_first_and_one_or_none() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    metric = _MetricStub()
    settings = SimpleNamespace(
        LLM_GLOBAL_ABUSE_GUARDS_ENABLED=True,
        LLM_GLOBAL_ABUSE_KILL_SWITCH=False,
        LLM_GLOBAL_ABUSE_PER_MINUTE_CAP=1000,
        LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD=1000,
        LLM_GLOBAL_ABUSE_BLOCK_SECONDS=60,
    )
    db.execute = AsyncMock(return_value=SimpleNamespace())
    cache = SimpleNamespace(enabled=False, client=None)

    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_OBSERVED", metric),
        patch("app.shared.llm.budget_manager.LLM_FAIR_USE_EVALUATIONS", metric),
    ):
        await budget_fair_use.enforce_global_abuse_guard(
            _DummyManager, tenant_id, db, PricingTier.PRO
        )
