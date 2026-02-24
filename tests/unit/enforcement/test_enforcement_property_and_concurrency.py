from __future__ import annotations

import asyncio
from decimal import Decimal
import random
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enforcement import (
    EnforcementDecision,
    EnforcementDecisionType,
    EnforcementMode,
    EnforcementSource,
)
from app.models.tenant import Tenant
from app.modules.enforcement.domain.service import (
    EnforcementService,
    GateInput,
    _stable_fingerprint,
)


def _rand_decimal(rng: random.Random, lower: int, upper: int) -> Decimal:
    value = rng.randint(lower, upper)
    return Decimal(value) / Decimal("100")


def _normalize_exp(
    decision: EnforcementDecisionType,
    reserve_alloc: Decimal,
    reserve_credit: Decimal,
) -> tuple[EnforcementDecisionType, Decimal, Decimal]:
    return decision, reserve_alloc.quantize(Decimal("0.0001")), reserve_credit.quantize(
        Decimal("0.0001")
    )


async def _seed_tenant(db: AsyncSession) -> Tenant:
    tenant = Tenant(
        id=uuid4(),
        name="Enforcement Property Tenant",
        plan="enterprise",
        is_deleted=False,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


@pytest.mark.asyncio
async def test_property_budget_waterfall_invariants(db: AsyncSession) -> None:
    service = EnforcementService(db)
    rng = random.Random(20260222)

    for _ in range(120):
        monthly_delta = _rand_decimal(rng, 0, 30000)
        allocation = _rand_decimal(rng, 0, 20000)
        credits = _rand_decimal(rng, 0, 20000)
        mode = rng.choice(
            [EnforcementMode.SHADOW, EnforcementMode.SOFT, EnforcementMode.HARD]
        )

        reasons: list[str] = []
        decision, reserve_alloc, reserve_credit = service._evaluate_budget_waterfall(
            mode=mode,
            monthly_delta=monthly_delta,
            allocation_headroom=allocation,
            credits_headroom=credits,
            reasons=reasons,
        )

        normalized = _normalize_exp(decision, reserve_alloc, reserve_credit)

        if monthly_delta <= allocation:
            assert normalized == (
                EnforcementDecisionType.ALLOW,
                monthly_delta.quantize(Decimal("0.0001")),
                Decimal("0.0000"),
            )
            assert "budget_exceeded" not in reasons
            continue

        if monthly_delta <= allocation + credits:
            assert normalized == (
                EnforcementDecisionType.ALLOW_WITH_CREDITS,
                allocation.quantize(Decimal("0.0001")),
                (monthly_delta - allocation).quantize(Decimal("0.0001")),
            )
            assert "credit_waterfall_used" in reasons
            continue

        if mode == EnforcementMode.SHADOW:
            assert normalized == (
                EnforcementDecisionType.ALLOW,
                Decimal("0.0000"),
                Decimal("0.0000"),
            )
            assert "budget_exceeded" in reasons
            assert "shadow_mode_budget_override" in reasons
            continue
        if mode == EnforcementMode.SOFT:
            assert normalized == (
                EnforcementDecisionType.REQUIRE_APPROVAL,
                allocation.quantize(Decimal("0.0001")),
                credits.quantize(Decimal("0.0001")),
            )
            assert "budget_exceeded" in reasons
            assert "soft_mode_budget_escalation" in reasons
            continue
        assert normalized == (
            EnforcementDecisionType.DENY,
            Decimal("0.0000"),
            Decimal("0.0000"),
        )
        assert "budget_exceeded" in reasons


@pytest.mark.asyncio
async def test_property_fingerprint_deterministic_and_input_sensitive(db: AsyncSession) -> None:
    service = EnforcementService(db)
    _ = service  # Keep fixture intent explicit; function under test is module-level.

    base_input = GateInput(
        project_id="proj-a",
        environment="nonprod",
        action="terraform.apply",
        resource_reference="module.vpc.aws_vpc.main",
        estimated_monthly_delta_usd=Decimal("100.1250"),
        estimated_hourly_delta_usd=Decimal("0.1415"),
        metadata={"tags": ["a", "b"], "owner": "finops"},
        idempotency_key=None,
        dry_run=False,
    )

    first = _stable_fingerprint(EnforcementSource.TERRAFORM, base_input)
    second = _stable_fingerprint(EnforcementSource.TERRAFORM, base_input)
    assert first == second

    changed_action = GateInput(
        **{**base_input.__dict__, "action": "terraform.destroy"}
    )
    changed_metadata = GateInput(
        **{**base_input.__dict__, "metadata": {"tags": ["a", "b"], "owner": "ops"}}
    )

    assert _stable_fingerprint(EnforcementSource.TERRAFORM, changed_action) != first
    assert _stable_fingerprint(EnforcementSource.TERRAFORM, changed_metadata) != first


@pytest.mark.asyncio
async def test_concurrency_same_idempotency_key_dedupes_single_decision(
    db: AsyncSession,
    async_engine,
) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    seed_service = EnforcementService(db)

    await seed_service.get_or_create_policy(tenant.id)
    await db.commit()
    await seed_service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("1000"),
        active=True,
    )

    session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    request = GateInput(
        project_id="default",
        environment="nonprod",
        action="terraform.apply",
        resource_reference="module.ec2.aws_instance.web",
        estimated_monthly_delta_usd=Decimal("120"),
        estimated_hourly_delta_usd=Decimal("0.15"),
        metadata={"resource_type": "aws_instance"},
        idempotency_key="stress-idem-shared",
    )

    async def invoke_once() -> UUID:
        async with session_maker() as session:
            service = EnforcementService(session)
            result = await service.evaluate_gate(
                tenant_id=tenant.id,
                actor_id=actor_id,
                source=EnforcementSource.TERRAFORM,
                gate_input=request,
            )
            return result.decision.id

    decision_ids = await asyncio.gather(*[invoke_once() for _ in range(8)])

    assert len(set(decision_ids)) == 1

    decision_count = (
        await db.execute(
            select(func.count())
            .select_from(EnforcementDecision)
            .where(EnforcementDecision.tenant_id == tenant.id)
        )
    ).scalar_one()
    assert decision_count == 1


@pytest.mark.asyncio
async def test_concurrency_distinct_idempotency_keys_create_distinct_decisions(
    db: AsyncSession,
    async_engine,
) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    seed_service = EnforcementService(db)

    await seed_service.get_or_create_policy(tenant.id)
    await db.commit()
    await seed_service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("2000"),
        active=True,
    )

    session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def invoke_once(idx: int) -> UUID:
        async with session_maker() as session:
            service = EnforcementService(session)
            result = await service.evaluate_gate(
                tenant_id=tenant.id,
                actor_id=actor_id,
                source=EnforcementSource.K8S_ADMISSION,
                gate_input=GateInput(
                    project_id="default",
                    environment="nonprod",
                    action="admission.validate",
                    resource_reference=f"deployments/apps/web-{idx}",
                    estimated_monthly_delta_usd=Decimal("20"),
                    estimated_hourly_delta_usd=Decimal("0.03"),
                    metadata={"resource_type": "k8s_deployment", "idx": idx},
                    idempotency_key=f"stress-idem-{idx}",
                ),
            )
            return result.decision.id

    decision_ids = await asyncio.gather(*[invoke_once(idx) for idx in range(6)])

    assert len(set(decision_ids)) == 6

    decision_count = (
        await db.execute(
            select(func.count())
            .select_from(EnforcementDecision)
            .where(EnforcementDecision.tenant_id == tenant.id)
        )
    ).scalar_one()
    assert decision_count == 6
