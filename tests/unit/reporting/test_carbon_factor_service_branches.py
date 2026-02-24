from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.carbon_factors import CarbonFactorSet, CarbonFactorUpdateLog
from app.modules.reporting.domain.calculator import build_carbon_factor_payload
from app.modules.reporting.domain.carbon_factors import (
    CarbonFactorGuardrailError,
    CarbonFactorService,
)


def _payload(
    *,
    factor_version: str,
    factor_timestamp: str,
    default_intensity: int,
) -> dict[str, object]:
    payload = build_carbon_factor_payload()
    payload["factor_version"] = factor_version
    payload["factor_timestamp"] = factor_timestamp
    region_intensity = dict(payload.get("region_carbon_intensity") or {})
    region_intensity["default"] = int(default_intensity)
    payload["region_carbon_intensity"] = region_intensity
    return payload


def _factor_set(*, version: str, ts: date, default: int, active: bool) -> CarbonFactorSet:
    return CarbonFactorSet(
        status="active" if active else "staged",
        is_active=active,
        factor_source="test-source",
        factor_version=version,
        factor_timestamp=ts,
        methodology_version="test-method",
        factors_checksum_sha256=(version + "0" * 64)[:64],
        payload={"region_carbon_intensity": {"default": default}},
    )


@pytest.mark.asyncio
async def test_parse_factor_date_accepts_multiple_shapes() -> None:
    assert CarbonFactorService._parse_factor_date(date(2026, 2, 1)) == date(2026, 2, 1)
    assert CarbonFactorService._parse_factor_date(
        datetime(2026, 2, 2, tzinfo=timezone.utc)
    ) == date(2026, 2, 2)
    assert CarbonFactorService._parse_factor_date("2026-02-03T00:00:00Z") == date(
        2026, 2, 3
    )
    with pytest.raises(ValueError, match="Invalid factor_timestamp"):
        CarbonFactorService._parse_factor_date(123)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda p: p.pop("factor_version"),
            "missing required keys",
        ),
        (
            lambda p: p.__setitem__("region_carbon_intensity", {}),
            "region_carbon_intensity must be a non-empty object",
        ),
        (
            lambda p: p.__setitem__("service_energy_factors_by_provider", {}),
            "service_energy_factors_by_provider must be a non-empty object",
        ),
        (
            lambda p: p.__setitem__("cloud_pue", 0),
            "cloud_pue must be a positive number",
        ),
        (
            lambda p: p.__setitem__("factor_source", "   "),
            "factor_source must be a non-empty string",
        ),
        (
            lambda p: p.__setitem__("factor_timestamp", "invalid"),
            "Invalid isoformat string",
        ),
    ],
)
async def test_validate_payload_rejects_invalid_inputs(mutate, expected: str) -> None:
    payload = _payload(
        factor_version="2026-02-20-v1",
        factor_timestamp="2026-02-20",
        default_intensity=420,
    )
    mutate(payload)

    with pytest.raises(ValueError, match=expected):
        CarbonFactorService._validate_payload(payload)


@pytest.mark.asyncio
async def test_ensure_active_seeds_once_and_returns_existing(db) -> None:
    service = CarbonFactorService(db)

    first = await service.ensure_active()
    second = await service.ensure_active()

    assert first.id == second.id
    assert first.is_active is True
    logs = list((await db.execute(select(CarbonFactorUpdateLog))).scalars().all())
    assert any(log.action == "seeded" for log in logs)


@pytest.mark.asyncio
async def test_stage_returns_existing_for_duplicate_checksum(db) -> None:
    service = CarbonFactorService(db)
    payload = _payload(
        factor_version="2026-02-21-v1",
        factor_timestamp="2026-02-21",
        default_intensity=430,
    )

    first = await service.stage(payload)
    second = await service.stage(dict(payload))

    assert first.id == second.id
    rows = list((await db.execute(select(CarbonFactorSet))).scalars().all())
    assert len([row for row in rows if row.factors_checksum_sha256 == first.factors_checksum_sha256]) == 1


@pytest.mark.asyncio
async def test_activate_noop_when_factor_is_already_active(db) -> None:
    service = CarbonFactorService(db)
    active = await service.ensure_active()
    before = list((await db.execute(select(CarbonFactorUpdateLog))).scalars().all())

    result = await service.activate(active)

    after = list((await db.execute(select(CarbonFactorUpdateLog))).scalars().all())
    assert result.id == active.id
    assert len(after) == len(before)


@pytest.mark.asyncio
async def test_guardrail_auto_activation_branches() -> None:
    service = CarbonFactorService(MagicMock())
    active = _factor_set(
        version="active-v1",
        ts=date(2026, 2, 1),
        default=400,
        active=True,
    )
    newer_ok = _factor_set(
        version="candidate-v1",
        ts=date(2026, 2, 2),
        default=500,
        active=False,
    )

    service._guardrail_auto_activation(active=active, candidate=newer_ok)

    with pytest.raises(CarbonFactorGuardrailError, match="must be newer"):
        service._guardrail_auto_activation(
            active=active,
            candidate=_factor_set(
                version="candidate-v-old",
                ts=date(2026, 2, 1),
                default=450,
                active=False,
            ),
        )

    with pytest.raises(CarbonFactorGuardrailError, match="out of bounds"):
        service._guardrail_auto_activation(
            active=active,
            candidate=_factor_set(
                version="candidate-v-high",
                ts=date(2026, 2, 2),
                default=3000,
                active=False,
            ),
        )

    with pytest.raises(CarbonFactorGuardrailError, match="exceeds the auto-activation"):
        service._guardrail_auto_activation(
            active=active,
            candidate=_factor_set(
                version="candidate-v-delta",
                ts=date(2026, 2, 2),
                default=700,
                active=False,
            ),
        )


@pytest.mark.asyncio
async def test_auto_activate_latest_no_update_and_duplicate(db) -> None:
    service = CarbonFactorService(db)
    active = await service.ensure_active()

    no_update = await service.auto_activate_latest()
    assert no_update["status"] == "no_update"
    assert no_update["active_factor_set_id"] == str(active.id)

    duplicate_candidate = CarbonFactorSet(
        status="staged",
        is_active=False,
        factor_source=active.factor_source,
        factor_version="dup-v1",
        factor_timestamp=active.factor_timestamp,
        methodology_version=active.methodology_version,
        factors_checksum_sha256=active.factors_checksum_sha256,
        payload=active.payload,
    )
    db.add(duplicate_candidate)
    await db.flush()

    duplicate = await service.auto_activate_latest()
    await db.refresh(duplicate_candidate)

    assert duplicate["status"] == "duplicate"
    assert duplicate_candidate.status == "archived"


@pytest.mark.asyncio
async def test_auto_activate_latest_blocked_and_activated_paths(db) -> None:
    service = CarbonFactorService(db)
    active = await service.ensure_active()

    blocked_payload = _payload(
        factor_version="blocked-v1",
        factor_timestamp=(active.factor_timestamp + timedelta(days=1)).isoformat(),
        default_intensity=3000,
    )
    blocked_candidate = await service.stage(blocked_payload)
    blocked = await service.auto_activate_latest()
    await db.refresh(blocked_candidate)

    assert blocked["status"] == "blocked_guardrail"
    assert blocked_candidate.status == "blocked"
    logs = list((await db.execute(select(CarbonFactorUpdateLog))).scalars().all())
    assert any(log.action == "blocked_guardrail" for log in logs)

    old_default = int(
        (active.payload or {}).get("region_carbon_intensity", {}).get("default", 400)
    )
    activated_payload = _payload(
        factor_version="active-v2",
        factor_timestamp=(active.factor_timestamp + timedelta(days=2)).isoformat(),
        default_intensity=min(old_default + 20, 500),
    )
    candidate = await service.stage(activated_payload)
    activated = await service.auto_activate_latest()
    now_active = await service.get_active()

    assert activated["status"] == "activated"
    assert activated["active_factor_set_id"] == str(candidate.id)
    assert now_active is not None
    assert now_active.id == candidate.id


@pytest.mark.asyncio
async def test_get_active_payload_falls_back_to_builtin_payload() -> None:
    service = CarbonFactorService(MagicMock())
    with patch.object(
        service,
        "ensure_active",
        new=AsyncMock(return_value=SimpleNamespace(payload=["bad-payload"])),
    ):
        payload = await service.get_active_payload()

    assert isinstance(payload, dict)
    assert "region_carbon_intensity" in payload
