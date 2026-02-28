from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

import app.shared.llm.budget_manager as manager_module
from app.shared.llm import budget_execution


class _Manager:
    BYOK_PLATFORM_FEE_USD = Decimal("0.0100")

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        return Decimal(str(value))

    @staticmethod
    def estimate_cost(
        prompt_tokens: int,
        completion_tokens: int,
        model: str,
        provider: str,
    ) -> Decimal:
        del prompt_tokens
        del completion_tokens
        del model
        del provider
        return Decimal("1.0000")


async def _async_value(value):
    return value


def test_budget_execution_value_coercion_helpers() -> None:
    assert budget_execution._coerce_decimal(Decimal("1.2")) == Decimal("1.2")
    assert budget_execution._coerce_decimal("2.5") == Decimal("2.5")
    assert budget_execution._coerce_decimal(True) is None
    assert budget_execution._coerce_decimal("invalid-decimal") is None

    assert budget_execution._coerce_bool(True) is True
    assert budget_execution._coerce_bool(0, default=True) is False
    assert budget_execution._coerce_bool("yes") is True
    assert budget_execution._coerce_bool("off", default=True) is False

    assert budget_execution._coerce_threshold_percent("-1") == Decimal("0")
    assert budget_execution._coerce_threshold_percent("500") == Decimal("100")
    assert budget_execution._coerce_threshold_percent("65") == Decimal("65")


def test_budget_execution_actor_and_request_type_normalization() -> None:
    assert budget_execution._normalize_actor_type("user") == "user"
    assert budget_execution._normalize_actor_type("system") == "system"
    assert budget_execution._normalize_actor_type("other") == "system"

    assert budget_execution._compose_request_type("user", "cost_analysis") == "user:cost_analysis"
    assert budget_execution._compose_request_type("system", "") == "system:unknown"
    assert budget_execution._compose_request_type("system", "user:already") == "user:already"


@pytest.mark.asyncio
async def test_check_budget_state_cache_short_circuit_paths() -> None:
    tenant_id = uuid4()
    db = AsyncMock()

    cache_hard = SimpleNamespace(
        enabled=True,
        client=SimpleNamespace(get=AsyncMock(return_value="1")),
    )
    with patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache_hard):
        state = await budget_execution.check_budget_state(_Manager, tenant_id, db)
    assert state == manager_module.BudgetStatus.HARD_LIMIT

    cache_soft = SimpleNamespace(
        enabled=True,
        client=SimpleNamespace(get=AsyncMock(side_effect=[None, "1"])),
    )
    with patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache_soft):
        state = await budget_execution.check_budget_state(_Manager, tenant_id, db)
    assert state == manager_module.BudgetStatus.SOFT_LIMIT


@pytest.mark.asyncio
async def test_check_budget_state_cache_error_is_fail_closed() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    cache = SimpleNamespace(
        enabled=True,
        client=SimpleNamespace(get=AsyncMock(side_effect=RuntimeError("redis-down"))),
    )
    with patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache):
        with pytest.raises(manager_module.BudgetExceededError):
            await budget_execution.check_budget_state(_Manager, tenant_id, db)


@pytest.mark.asyncio
async def test_check_budget_state_budget_paths() -> None:
    tenant_id = uuid4()
    cache = SimpleNamespace(
        enabled=True,
        client=SimpleNamespace(
            get=AsyncMock(return_value=None),
            set=AsyncMock(),
        ),
    )
    db = AsyncMock()

    with patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache):
        # No budget row -> OK
        no_budget_result = MagicMock()
        no_budget_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=no_budget_result)
        assert (
            await budget_execution.check_budget_state(_Manager, tenant_id, db)
            == manager_module.BudgetStatus.OK
        )

        # Invalid numeric values -> OK
        invalid_budget = SimpleNamespace(
            monthly_limit_usd="invalid",
            monthly_spend_usd="10",
            pending_reservations_usd="0",
            alert_threshold_percent=80,
            hard_limit=True,
        )
        invalid_result = MagicMock()
        invalid_result.scalar_one_or_none.return_value = invalid_budget
        db.execute = AsyncMock(return_value=invalid_result)
        assert (
            await budget_execution.check_budget_state(_Manager, tenant_id, db)
            == manager_module.BudgetStatus.OK
        )

        # Hard-limit exceeded -> exception + cache block
        hard_budget = SimpleNamespace(
            monthly_limit_usd=Decimal("10"),
            monthly_spend_usd=Decimal("10"),
            pending_reservations_usd=Decimal("0"),
            alert_threshold_percent=80,
            hard_limit=True,
        )
        hard_result = MagicMock()
        hard_result.scalar_one_or_none.return_value = hard_budget
        db.execute = AsyncMock(return_value=hard_result)
        with pytest.raises(manager_module.BudgetExceededError):
            await budget_execution.check_budget_state(_Manager, tenant_id, db)

        # Soft-limit from hard-limit disabled path
        soft_budget = SimpleNamespace(
            monthly_limit_usd=Decimal("10"),
            monthly_spend_usd=Decimal("10"),
            pending_reservations_usd=Decimal("0"),
            alert_threshold_percent=80,
            hard_limit=False,
        )
        soft_result = MagicMock()
        soft_result.scalar_one_or_none.return_value = soft_budget
        db.execute = AsyncMock(return_value=soft_result)
        assert (
            await budget_execution.check_budget_state(_Manager, tenant_id, db)
            == manager_module.BudgetStatus.SOFT_LIMIT
        )

        # Threshold alert path -> SOFT_LIMIT
        threshold_budget = SimpleNamespace(
            monthly_limit_usd=Decimal("100"),
            monthly_spend_usd=Decimal("75"),
            pending_reservations_usd=Decimal("10"),
            alert_threshold_percent=Decimal("80"),
            hard_limit=False,
        )
        threshold_result = MagicMock()
        threshold_result.scalar_one_or_none.return_value = threshold_budget
        db.execute = AsyncMock(return_value=threshold_result)
        assert (
            await budget_execution.check_budget_state(_Manager, tenant_id, db)
            == manager_module.BudgetStatus.SOFT_LIMIT
        )


@pytest.mark.asyncio
async def test_check_budget_and_alert_handles_no_budget_and_already_sent() -> None:
    tenant_id = uuid4()
    db = AsyncMock()

    no_budget_result = MagicMock()
    no_budget_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=no_budget_result)
    await budget_execution.check_budget_and_alert(
        _Manager,
        tenant_id,
        db,
        Decimal("1.0000"),
    )

    current_month = datetime.now(timezone.utc)
    budget = SimpleNamespace(
        monthly_limit_usd=Decimal("100"),
        alert_threshold_percent=Decimal("80"),
        alert_sent_at=current_month,
    )
    budget_result = MagicMock()
    budget_result.scalar_one_or_none.return_value = budget
    usage_result = MagicMock()
    usage_result.scalar.return_value = Decimal("90")
    db.execute = AsyncMock(side_effect=[budget_result, usage_result])

    with patch("app.shared.llm.budget_manager.audit_log") as audit_log:
        await budget_execution.check_budget_and_alert(
            _Manager,
            tenant_id,
            db,
            Decimal("1.0000"),
        )
    audit_log.assert_not_called()


@pytest.mark.asyncio
async def test_check_budget_and_alert_dispatch_paths() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    budget = SimpleNamespace(
        monthly_limit_usd=Decimal("100"),
        alert_threshold_percent=Decimal("80"),
        alert_sent_at=None,
    )
    budget_result = MagicMock()
    budget_result.scalar_one_or_none.return_value = budget
    usage_result = MagicMock()
    usage_result.scalar.return_value = Decimal("90")
    db.execute = AsyncMock(side_effect=[budget_result, usage_result])

    with (
        patch("app.shared.llm.budget_manager.audit_log") as audit_log,
        patch(
            "app.modules.notifications.domain.get_tenant_slack_service",
            new=AsyncMock(return_value=None),
        ),
    ):
        await budget_execution.check_budget_and_alert(
            _Manager,
            tenant_id,
            db,
            Decimal("1.0000"),
        )
    audit_log.assert_called_once()
    assert budget.alert_sent_at is not None

    budget.alert_sent_at = None
    db.execute = AsyncMock(side_effect=[budget_result, usage_result])
    slack = SimpleNamespace(send_alert=AsyncMock(side_effect=RuntimeError("slack-fail")))
    with (
        patch("app.shared.llm.budget_manager.audit_log"),
        patch(
            "app.modules.notifications.domain.get_tenant_slack_service",
            new=AsyncMock(return_value=slack),
        ),
    ):
        await budget_execution.check_budget_and_alert(
            _Manager,
            tenant_id,
            db,
            Decimal("1.0000"),
        )


@pytest.mark.parametrize(
    ("tier", "expected_limit", "fair_use_enabled"),
    [
        (manager_module.PricingTier.FREE, 1.0, False),
        (manager_module.PricingTier.GROWTH, 10.0, False),
        (manager_module.PricingTier.PRO, 50.0, True),
    ],
)
@pytest.mark.asyncio
async def test_check_and_reserve_budget_auto_bootstrap_tier_defaults_and_actor_normalization(
    tier, expected_limit, fair_use_enabled
) -> None:
    tenant_id = uuid4()

    db = AsyncMock()
    db.flush = AsyncMock()

    def _add_side_effect(obj):
        if getattr(obj, "budget_reset_at", None) is None:
            obj.budget_reset_at = datetime.now(timezone.utc)
        if getattr(obj, "monthly_spend_usd", None) is None:
            obj.monthly_spend_usd = Decimal("0.0")
        if getattr(obj, "pending_reservations_usd", None) is None:
            obj.pending_reservations_usd = Decimal("0.0")

    db.add = MagicMock(side_effect=_add_side_effect)
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

    manager = SimpleNamespace(
        estimate_cost=_Manager.estimate_cost,
        _to_decimal=_Manager._to_decimal,
        _enforce_daily_analysis_limit=AsyncMock(),
        _release_fair_use_inflight_slot=AsyncMock(),
    )
    settings = SimpleNamespace(LLM_FAIR_USE_GUARDS_ENABLED=fair_use_enabled)

    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(side_effect=[tier, tier]),
        ) as get_tier,
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch(
            "app.shared.llm.budget_execution.record_authenticated_abuse_signal",
            new=AsyncMock(),
        ) as abuse_signal,
        patch(
            "app.shared.llm.budget_execution.enforce_global_abuse_guard",
            new=AsyncMock(),
        ) as global_guard,
        patch(
            "app.shared.llm.budget_execution.enforce_fair_use_guards",
            new=AsyncMock(return_value=False),
        ) as fair_use_guard,
    ):
        cost = await budget_execution.check_and_reserve_budget(
            manager,
            tenant_id,
            db,
            provider="openai",
            model="gpt-4o",
            prompt_tokens=10,
            completion_tokens=10,
            user_id=uuid4(),
            actor_type="system",
        )

    assert cost == Decimal("1.0000")
    get_tier.assert_awaited()
    abuse_signal.assert_awaited_once()
    assert abuse_signal.await_args.kwargs["actor_type"] == "user"
    global_guard.assert_awaited_once()
    if fair_use_enabled:
        fair_use_guard.assert_awaited_once()
    else:
        fair_use_guard.assert_not_called()

    added_budget = db.add.call_args[0][0]
    assert added_budget.monthly_limit_usd == expected_limit
    assert db.flush.await_count >= 2


@pytest.mark.asyncio
async def test_check_and_reserve_budget_resets_monthly_window_before_reserving() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    db.flush = AsyncMock()

    prior_month = datetime(2025, 1, 15, tzinfo=timezone.utc)
    budget = SimpleNamespace(
        monthly_limit_usd=Decimal("100"),
        monthly_spend_usd=Decimal("5"),
        pending_reservations_usd=Decimal("2"),
        budget_reset_at=prior_month,
    )
    db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=lambda: budget)
    )

    manager = SimpleNamespace(
        estimate_cost=_Manager.estimate_cost,
        _to_decimal=_Manager._to_decimal,
        _enforce_daily_analysis_limit=AsyncMock(),
        _release_fair_use_inflight_slot=AsyncMock(),
    )
    settings = SimpleNamespace(LLM_FAIR_USE_GUARDS_ENABLED=False)

    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=manager_module.PricingTier.PRO),
        ),
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch(
            "app.shared.llm.budget_execution.record_authenticated_abuse_signal",
            new=AsyncMock(),
        ),
        patch(
            "app.shared.llm.budget_execution.enforce_global_abuse_guard",
            new=AsyncMock(),
        ),
    ):
        await budget_execution.check_and_reserve_budget(
            manager,
            tenant_id,
            db,
            prompt_tokens=1,
            completion_tokens=1,
        )

    assert budget.monthly_spend_usd == Decimal("0.0")
    assert budget.pending_reservations_usd == Decimal("1.0000")
    assert budget.budget_reset_at.month != prior_month.month


@pytest.mark.asyncio
async def test_check_and_reserve_budget_releases_slot_on_budget_exceeded() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    db.flush = AsyncMock()
    budget = SimpleNamespace(
        monthly_limit_usd=Decimal("1"),
        monthly_spend_usd=Decimal("1"),
        pending_reservations_usd=Decimal("0"),
        budget_reset_at=datetime.now(timezone.utc),
    )
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: budget))

    release_slot = AsyncMock()
    manager = SimpleNamespace(
        estimate_cost=_Manager.estimate_cost,
        _to_decimal=_Manager._to_decimal,
        _enforce_daily_analysis_limit=AsyncMock(),
        _release_fair_use_inflight_slot=release_slot,
    )
    settings = SimpleNamespace(LLM_FAIR_USE_GUARDS_ENABLED=True)
    metric_counter = SimpleNamespace(inc=MagicMock())
    metric = SimpleNamespace(labels=MagicMock(return_value=metric_counter))

    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=manager_module.PricingTier.PRO),
        ),
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch("app.shared.llm.budget_manager.LLM_PRE_AUTH_DENIALS", metric),
        patch(
            "app.shared.llm.budget_execution.record_authenticated_abuse_signal",
            new=AsyncMock(),
        ),
        patch(
            "app.shared.llm.budget_execution.enforce_global_abuse_guard",
            new=AsyncMock(),
        ),
        patch(
            "app.shared.llm.budget_execution.enforce_fair_use_guards",
            new=AsyncMock(return_value=True),
        ),
        pytest.raises(manager_module.BudgetExceededError),
    ):
        await budget_execution.check_and_reserve_budget(
            manager,
            tenant_id,
            db,
            prompt_tokens=1,
            completion_tokens=1,
        )

    release_slot.assert_awaited_once_with(tenant_id)


@pytest.mark.asyncio
async def test_check_and_reserve_budget_logs_and_releases_slot_on_unexpected_error() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=RuntimeError("db-down"))

    release_slot = AsyncMock()
    manager = SimpleNamespace(
        estimate_cost=_Manager.estimate_cost,
        _to_decimal=_Manager._to_decimal,
        _enforce_daily_analysis_limit=AsyncMock(),
        _release_fair_use_inflight_slot=release_slot,
    )
    settings = SimpleNamespace(LLM_FAIR_USE_GUARDS_ENABLED=True)

    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=manager_module.PricingTier.PRO),
        ),
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch(
            "app.shared.llm.budget_execution.record_authenticated_abuse_signal",
            new=AsyncMock(),
        ),
        patch(
            "app.shared.llm.budget_execution.enforce_global_abuse_guard",
            new=AsyncMock(),
        ),
        patch(
            "app.shared.llm.budget_execution.enforce_fair_use_guards",
            new=AsyncMock(return_value=True),
        ),
        patch("app.shared.llm.budget_manager.logger") as logger,
        pytest.raises(RuntimeError, match="db-down"),
    ):
        await budget_execution.check_and_reserve_budget(
            manager,
            tenant_id,
            db,
            prompt_tokens=1,
            completion_tokens=1,
        )

    release_slot.assert_awaited_once_with(tenant_id)
    logger.exception.assert_called_once()


@pytest.mark.asyncio
async def test_check_and_reserve_budget_unexpected_error_without_concurrency_slot() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=RuntimeError("db-down-no-slot"))

    release_slot = AsyncMock()
    manager = SimpleNamespace(
        estimate_cost=_Manager.estimate_cost,
        _to_decimal=_Manager._to_decimal,
        _enforce_daily_analysis_limit=AsyncMock(),
        _release_fair_use_inflight_slot=release_slot,
    )
    settings = SimpleNamespace(LLM_FAIR_USE_GUARDS_ENABLED=True)

    with (
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=manager_module.PricingTier.PRO),
        ),
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch(
            "app.shared.llm.budget_execution.record_authenticated_abuse_signal",
            new=AsyncMock(),
        ),
        patch(
            "app.shared.llm.budget_execution.enforce_global_abuse_guard",
            new=AsyncMock(),
        ),
        patch(
            "app.shared.llm.budget_execution.enforce_fair_use_guards",
            new=AsyncMock(return_value=False),
        ),
        patch("app.shared.llm.budget_manager.logger") as logger,
        pytest.raises(RuntimeError, match="db-down-no-slot"),
    ):
        await budget_execution.check_and_reserve_budget(
            manager,
            tenant_id,
            db,
            prompt_tokens=1,
            completion_tokens=1,
        )

    release_slot.assert_not_awaited()
    logger.exception.assert_called_once()


@pytest.mark.asyncio
async def test_record_usage_entry_handles_awaitable_budget_accessor_and_metric_debug_failure() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    budget = SimpleNamespace(
        pending_reservations_usd="invalid",
        monthly_spend_usd=Decimal("1.0"),
    )
    result = SimpleNamespace(scalar_one_or_none=lambda: _async_value(budget))

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    manager = SimpleNamespace(
        BYOK_PLATFORM_FEE_USD=Decimal("0.0100"),
        estimate_cost=_Manager.estimate_cost,
        _to_decimal=_Manager._to_decimal,
        _check_budget_and_alert=AsyncMock(),
        _release_fair_use_inflight_slot=AsyncMock(),
    )

    with (
        patch("app.shared.llm.budget_manager.LLMUsage") as usage_model,
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(side_effect=RuntimeError("tier-metric-fail")),
        ),
        patch("app.shared.llm.budget_manager.logger") as logger,
    ):
        await budget_execution.record_usage_entry(
            manager,
            tenant_id,
            db,
            model="gpt-4o",
            prompt_tokens=10,
            completion_tokens=5,
            request_type="analysis",
            user_id=user_id,
            actor_type="system",
        )

    _, kwargs = usage_model.call_args
    assert kwargs["request_type"] == "user:analysis"
    assert budget.pending_reservations_usd == "invalid"
    assert budget.monthly_spend_usd == Decimal("1.0")
    logger.debug.assert_called_once()
    manager._check_budget_and_alert.assert_awaited_once()
    manager._release_fair_use_inflight_slot.assert_awaited_once_with(tenant_id)


@pytest.mark.asyncio
async def test_record_usage_entry_non_callable_budget_accessor_path() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=None))
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    manager = SimpleNamespace(
        BYOK_PLATFORM_FEE_USD=Decimal("0.0100"),
        estimate_cost=_Manager.estimate_cost,
        _to_decimal=_Manager._to_decimal,
        _check_budget_and_alert=AsyncMock(),
        _release_fair_use_inflight_slot=AsyncMock(),
    )
    metric_counter = SimpleNamespace(inc=MagicMock())
    metric = SimpleNamespace(labels=MagicMock(return_value=metric_counter))

    with (
        patch("app.shared.llm.budget_manager.LLMUsage", return_value=object()),
        patch(
            "app.shared.llm.budget_manager.get_tenant_tier",
            new=AsyncMock(return_value=manager_module.PricingTier.PRO),
        ),
        patch("app.shared.llm.budget_manager.LLM_SPEND_USD", metric),
    ):
        await budget_execution.record_usage_entry(
            manager,
            tenant_id,
            db,
            model="gpt-4o",
            prompt_tokens=5,
            completion_tokens=5,
        )

    manager._check_budget_and_alert.assert_awaited_once()
    manager._release_fair_use_inflight_slot.assert_awaited_once_with(tenant_id)


@pytest.mark.asyncio
async def test_record_usage_entry_logs_rollback_failure_warning() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))
    db.add = MagicMock(side_effect=RuntimeError("add-failed"))
    db.rollback = AsyncMock(side_effect=RuntimeError("rollback-failed"))

    manager = SimpleNamespace(
        BYOK_PLATFORM_FEE_USD=Decimal("0.0100"),
        estimate_cost=_Manager.estimate_cost,
        _to_decimal=_Manager._to_decimal,
        _check_budget_and_alert=AsyncMock(),
        _release_fair_use_inflight_slot=AsyncMock(),
    )

    with (
        patch("app.shared.llm.budget_manager.LLMUsage", return_value=object()),
        patch("app.shared.llm.budget_manager.logger") as logger,
    ):
        await budget_execution.record_usage_entry(
            manager,
            tenant_id,
            db,
            model="gpt-4o",
            prompt_tokens=1,
            completion_tokens=1,
        )

    logger.error.assert_called_once()
    logger.warning.assert_called_once()
    manager._release_fair_use_inflight_slot.assert_awaited_once_with(tenant_id)


@pytest.mark.asyncio
async def test_record_usage_entry_error_without_rollback_callable() -> None:
    tenant_id = uuid4()
    db = SimpleNamespace(
        execute=AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None)),
        add=MagicMock(side_effect=RuntimeError("add-failed-no-rollback")),
        flush=AsyncMock(),
        commit=AsyncMock(),
    )

    manager = SimpleNamespace(
        BYOK_PLATFORM_FEE_USD=Decimal("0.0100"),
        estimate_cost=_Manager.estimate_cost,
        _to_decimal=_Manager._to_decimal,
        _check_budget_and_alert=AsyncMock(),
        _release_fair_use_inflight_slot=AsyncMock(),
    )

    with (
        patch("app.shared.llm.budget_manager.LLMUsage", return_value=object()),
        patch("app.shared.llm.budget_manager.logger") as logger,
    ):
        await budget_execution.record_usage_entry(
            manager,
            tenant_id,
            db,  # type: ignore[arg-type]
            model="gpt-4o",
            prompt_tokens=1,
            completion_tokens=1,
        )

    logger.error.assert_called_once()
    logger.warning.assert_not_called()
    manager._release_fair_use_inflight_slot.assert_awaited_once_with(tenant_id)


@pytest.mark.asyncio
async def test_check_budget_state_handles_awaitable_budget_accessor() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=SimpleNamespace(scalar_one_or_none=lambda: _async_value(None))
    )
    cache = SimpleNamespace(enabled=False, client=None)

    with patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache):
        state = await budget_execution.check_budget_state(_Manager, tenant_id, db)

    assert state == manager_module.BudgetStatus.OK


@pytest.mark.asyncio
async def test_check_budget_state_non_callable_budget_accessor_defaults_ok() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=None))
    cache = SimpleNamespace(enabled=False, client=None)

    with patch("app.shared.llm.budget_manager.get_cache_service", return_value=cache):
        state = await budget_execution.check_budget_state(_Manager, tenant_id, db)

    assert state == manager_module.BudgetStatus.OK


@pytest.mark.asyncio
async def test_check_budget_and_alert_awaitable_budget_accessor_invalid_limit_returns_early() -> None:
    tenant_id = uuid4()
    invalid_budget = SimpleNamespace(
        monthly_limit_usd="invalid",
        alert_threshold_percent=Decimal("80"),
        alert_sent_at=None,
    )
    db = AsyncMock()
    usage_result = SimpleNamespace(scalar=lambda: Decimal("5"))
    db.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(scalar_one_or_none=lambda: _async_value(invalid_budget)),
            usage_result,
        ]
    )

    await budget_execution.check_budget_and_alert(
        _Manager,
        tenant_id,
        db,
        Decimal("1.0000"),
    )

    assert db.execute.await_count == 2


def test_budget_execution_helper_additional_edge_defaults() -> None:
    assert budget_execution._coerce_bool("maybe", default=True) is True
    assert budget_execution._normalize_actor_type(None) == "system"
    assert budget_execution._compose_request_type("system", "   ") == "system:unknown"
