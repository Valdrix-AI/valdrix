from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.shared.core.exceptions import LLMFairUseExceededError
from app.shared.core.pricing import PricingTier
from app.shared.llm.budget_manager import LLMBudgetManager


@pytest.mark.asyncio
async def test_fair_use_guards_disabled_noop() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    LLMBudgetManager._local_inflight_counts.clear()

    settings = SimpleNamespace(LLM_FAIR_USE_GUARDS_ENABLED=False)
    with patch("app.shared.llm.budget_manager.get_settings", return_value=settings):
        acquired = await LLMBudgetManager._enforce_fair_use_guards(
            tenant_id=tenant_id,
            db=db,
            tier=PricingTier.PRO,
        )

    assert acquired is False
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_fair_use_per_minute_denial_is_429() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    LLMBudgetManager._local_inflight_counts.clear()

    db.execute.side_effect = [
        MagicMock(scalar=lambda: 0),  # daily count
        MagicMock(scalar=lambda: 1),  # last-minute count
    ]
    settings = SimpleNamespace(
        LLM_FAIR_USE_GUARDS_ENABLED=True,
        LLM_FAIR_USE_PRO_DAILY_SOFT_CAP=1200,
        LLM_FAIR_USE_ENTERPRISE_DAILY_SOFT_CAP=4000,
        LLM_FAIR_USE_PER_MINUTE_CAP=1,
        LLM_FAIR_USE_PER_TENANT_CONCURRENCY_CAP=4,
        LLM_FAIR_USE_CONCURRENCY_LEASE_TTL_SECONDS=180,
    )

    with patch("app.shared.llm.budget_manager.get_settings", return_value=settings):
        with pytest.raises(LLMFairUseExceededError) as exc:
            await LLMBudgetManager._enforce_fair_use_guards(
                tenant_id=tenant_id,
                db=db,
                tier=PricingTier.PRO,
            )

    assert exc.value.status_code == 429
    assert exc.value.code == "llm_fair_use_exceeded"
    assert exc.value.details.get("gate") == "per_minute"


@pytest.mark.asyncio
async def test_fair_use_concurrency_guard_local_fallback() -> None:
    tenant_id = uuid4()
    LLMBudgetManager._local_inflight_counts.clear()

    settings = SimpleNamespace(
        LLM_FAIR_USE_GUARDS_ENABLED=True,
        LLM_FAIR_USE_PRO_DAILY_SOFT_CAP=1200,
        LLM_FAIR_USE_ENTERPRISE_DAILY_SOFT_CAP=4000,
        LLM_FAIR_USE_PER_MINUTE_CAP=30,
        LLM_FAIR_USE_PER_TENANT_CONCURRENCY_CAP=1,
        LLM_FAIR_USE_CONCURRENCY_LEASE_TTL_SECONDS=180,
    )
    cache_stub = SimpleNamespace(enabled=False, client=None)

    with (
        patch("app.shared.llm.budget_manager.get_settings", return_value=settings),
        patch(
            "app.shared.llm.budget_manager.get_cache_service", return_value=cache_stub
        ),
    ):
        db_first = AsyncMock()
        db_first.execute.side_effect = [
            MagicMock(scalar=lambda: 0),  # daily count
            MagicMock(scalar=lambda: 0),  # last-minute count
        ]
        acquired = await LLMBudgetManager._enforce_fair_use_guards(
            tenant_id=tenant_id,
            db=db_first,
            tier=PricingTier.PRO,
        )
        assert acquired is True

        db_second = AsyncMock()
        db_second.execute.side_effect = [
            MagicMock(scalar=lambda: 0),  # daily count
            MagicMock(scalar=lambda: 0),  # last-minute count
        ]
        with pytest.raises(LLMFairUseExceededError) as exc:
            await LLMBudgetManager._enforce_fair_use_guards(
                tenant_id=tenant_id,
                db=db_second,
                tier=PricingTier.PRO,
            )
        assert exc.value.details.get("gate") == "concurrency"

        await LLMBudgetManager._release_fair_use_inflight_slot(tenant_id)

        db_third = AsyncMock()
        db_third.execute.side_effect = [
            MagicMock(scalar=lambda: 0),  # daily count
            MagicMock(scalar=lambda: 0),  # last-minute count
        ]
        acquired_again = await LLMBudgetManager._enforce_fair_use_guards(
            tenant_id=tenant_id,
            db=db_third,
            tier=PricingTier.PRO,
        )
        assert acquired_again is True
        await LLMBudgetManager._release_fair_use_inflight_slot(tenant_id)
