from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import random
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enforcement import (
    EnforcementCreditGrant,
    EnforcementCreditReservationAllocation,
    EnforcementDecision,
    EnforcementDecisionLedger,
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


@pytest.mark.asyncio
async def test_concurrency_distinct_keys_do_not_oversubscribe_budget_reservations(
    db: AsyncSession,
    async_engine,
) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    seed_service = EnforcementService(db)

    policy = await seed_service.get_or_create_policy(tenant.id)
    policy.terraform_mode = EnforcementMode.HARD
    policy.terraform_mode_nonprod = EnforcementMode.HARD
    await db.commit()

    await seed_service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("100"),
        active=True,
    )

    session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def invoke_once(idx: int) -> EnforcementDecisionType:
        async with session_maker() as session:
            service = EnforcementService(session)
            result = await service.evaluate_gate(
                tenant_id=tenant.id,
                actor_id=actor_id,
                source=EnforcementSource.TERRAFORM,
                gate_input=GateInput(
                    project_id="default",
                    environment="nonprod",
                    action="terraform.apply",
                    resource_reference=f"module.ec2.aws_instance.app-{idx}",
                    estimated_monthly_delta_usd=Decimal("60"),
                    estimated_hourly_delta_usd=Decimal("0.08"),
                    metadata={"resource_type": "aws_instance", "idx": idx},
                    idempotency_key=f"oversub-{idx}",
                ),
            )
            return result.decision.decision

    decisions = await asyncio.gather(invoke_once(0), invoke_once(1))

    totals = (
        await db.execute(
            select(
                func.coalesce(func.sum(EnforcementDecision.reserved_allocation_usd), 0),
                func.coalesce(func.sum(EnforcementDecision.reserved_credit_usd), 0),
            )
            .where(EnforcementDecision.tenant_id == tenant.id)
            .where(EnforcementDecision.reservation_active.is_(True))
        )
    ).one()
    total_reserved = Decimal(str(totals[0])) + Decimal(str(totals[1]))

    assert total_reserved <= Decimal("100.0000")
    assert decisions.count(EnforcementDecisionType.ALLOW) == 1
    assert decisions.count(EnforcementDecisionType.DENY) == 1


@pytest.mark.asyncio
async def test_concurrency_reconcile_same_idempotency_key_settles_credit_once(
    db: AsyncSession,
    async_engine,
) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    seed_service = EnforcementService(db)

    await seed_service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("2500"),
        default_ttl_seconds=900,
    )
    await seed_service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("10"),
        active=True,
    )
    credit_grant = await seed_service.create_credit_grant(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        total_amount_usd=Decimal("100"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        reason="concurrency reconcile replay",
    )
    gate = await seed_service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.app.aws_instance.concurrency-reconcile",
            estimated_monthly_delta_usd=Decimal("30"),
            estimated_hourly_delta_usd=Decimal("0.11"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key="concurrency-reconcile-seed-1",
        ),
    )
    assert gate.approval is not None
    assert gate.decision.reservation_active is True
    assert gate.decision.reserved_allocation_usd == Decimal("10.0000")
    assert gate.decision.reserved_credit_usd == Decimal("20.0000")

    session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def invoke_reconcile_once() -> tuple[str, Decimal, Decimal, datetime]:
        async with session_maker() as session:
            service = EnforcementService(session)
            result = await service.reconcile_reservation(
                tenant_id=tenant.id,
                decision_id=gate.decision.id,
                actor_id=actor_id,
                actual_monthly_delta_usd=Decimal("15"),
                notes="concurrency replay stable",
                idempotency_key="concurrency-reconcile-shared-1",
            )
            return (
                result.status,
                result.released_reserved_usd,
                result.drift_usd,
                result.reconciled_at,
            )

    first, second = await asyncio.gather(
        invoke_reconcile_once(),
        invoke_reconcile_once(),
    )
    assert first[:3] == second[:3]

    decision = (
        await db.execute(
            select(EnforcementDecision)
            .where(EnforcementDecision.id == gate.decision.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert decision.reservation_active is False
    assert decision.reserved_allocation_usd == Decimal("0")
    assert decision.reserved_credit_usd == Decimal("0")

    allocations = (
        await db.execute(
            select(EnforcementCreditReservationAllocation).where(
                EnforcementCreditReservationAllocation.decision_id == gate.decision.id
            )
        )
    ).scalars().all()
    assert len(allocations) == 1
    assert allocations[0].active is False
    assert allocations[0].consumed_amount_usd == Decimal("5.0000")
    assert allocations[0].released_amount_usd == Decimal("15.0000")

    refreshed_credit = (
        await db.execute(
            select(EnforcementCreditGrant).where(
                EnforcementCreditGrant.id == credit_grant.id
            ).execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert refreshed_credit.remaining_amount_usd == Decimal("95.0000")


@pytest.mark.asyncio
async def test_concurrency_reconcile_same_idempotency_key_payload_conflict(
    db: AsyncSession,
    async_engine,
) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    seed_service = EnforcementService(db)

    await seed_service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("2500"),
        default_ttl_seconds=900,
    )
    await seed_service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("10"),
        active=True,
    )
    await seed_service.create_credit_grant(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        total_amount_usd=Decimal("100"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        reason="concurrency reconcile mismatch",
    )
    gate = await seed_service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.app.aws_instance.concurrency-conflict",
            estimated_monthly_delta_usd=Decimal("30"),
            estimated_hourly_delta_usd=Decimal("0.11"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key="concurrency-reconcile-seed-2",
        ),
    )
    assert gate.approval is not None
    assert gate.decision.reservation_active is True

    session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def invoke(actual_delta: Decimal) -> tuple[str, int | str]:
        async with session_maker() as session:
            service = EnforcementService(session)
            try:
                result = await service.reconcile_reservation(
                    tenant_id=tenant.id,
                    decision_id=gate.decision.id,
                    actor_id=actor_id,
                    actual_monthly_delta_usd=actual_delta,
                    notes="concurrency conflict replay",
                    idempotency_key="concurrency-reconcile-shared-2",
                )
                return ("ok", result.status)
            except HTTPException as exc:
                return ("err", exc.status_code)

    left, right = await asyncio.gather(
        invoke(Decimal("15")),
        invoke(Decimal("16")),
    )
    results = [left, right]
    assert results.count(("err", 409)) == 1
    assert len([item for item in results if item[0] == "ok"]) == 1

    decision = (
        await db.execute(
            select(EnforcementDecision)
            .where(EnforcementDecision.id == gate.decision.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert decision.reservation_active is False

    reconciliation = (decision.response_payload or {}).get("reservation_reconciliation", {})
    actual_delta = Decimal(str(reconciliation["actual_monthly_delta_usd"]))
    expected_consumed = min(
        Decimal("20.0000"),
        max(Decimal("0.0000"), actual_delta - Decimal("10.0000")),
    ).quantize(Decimal("0.0001"))
    expected_released = (Decimal("20.0000") - expected_consumed).quantize(
        Decimal("0.0001")
    )

    allocations = (
        await db.execute(
            select(EnforcementCreditReservationAllocation).where(
                EnforcementCreditReservationAllocation.decision_id == gate.decision.id
            )
        )
    ).scalars().all()
    assert len(allocations) == 1
    allocation = allocations[0]
    assert allocation.active is False
    assert allocation.consumed_amount_usd == expected_consumed
    assert allocation.released_amount_usd == expected_released


@pytest.mark.asyncio
async def test_concurrency_reconcile_overdue_claims_each_reservation_once(
    db: AsyncSession,
    async_engine,
) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    seed_service = EnforcementService(db)

    await seed_service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("2500"),
        default_ttl_seconds=900,
    )
    await seed_service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("1000"),
        active=True,
    )
    gate = await seed_service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.app.aws_instance.concurrency-overdue",
            estimated_monthly_delta_usd=Decimal("75"),
            estimated_hourly_delta_usd=Decimal("0.11"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key="concurrency-reconcile-overdue-seed-1",
        ),
    )
    assert gate.approval is not None
    stale_decision = (
        await db.execute(
            select(EnforcementDecision)
            .where(EnforcementDecision.id == gate.decision.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    stale_decision.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    await db.commit()

    session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def invoke_once() -> tuple[int, Decimal, list[UUID]]:
        async with session_maker() as session:
            service = EnforcementService(session)
            summary = await service.reconcile_overdue_reservations(
                tenant_id=tenant.id,
                actor_id=actor_id,
                older_than_seconds=3600,
                limit=50,
            )
            return summary.released_count, summary.total_released_usd, summary.decision_ids

    left, right = await asyncio.gather(invoke_once(), invoke_once())
    released_count_total = left[0] + right[0]
    released_usd_total = left[1] + right[1]
    flattened_ids = [*left[2], *right[2]]

    assert released_count_total == 1
    assert released_usd_total == Decimal("75.0000")
    assert flattened_ids.count(gate.decision.id) == 1

    refreshed = (
        await db.execute(
            select(EnforcementDecision)
            .where(EnforcementDecision.id == gate.decision.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert refreshed.reservation_active is False
    ledger_rows = (
        await db.execute(
            select(EnforcementDecisionLedger)
            .where(EnforcementDecisionLedger.decision_id == gate.decision.id)
            .order_by(
                EnforcementDecisionLedger.recorded_at.asc(),
                EnforcementDecisionLedger.id.asc(),
            )
        )
    ).scalars().all()
    # Initial gate + one overdue reconcile snapshot across concurrent runners.
    assert len(ledger_rows) == 2
