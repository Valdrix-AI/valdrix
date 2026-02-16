from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.carbon_factors import CarbonFactorSet, CarbonFactorUpdateLog
from app.modules.reporting.domain.calculator import (
    build_carbon_factor_payload,
    compute_carbon_factor_checksum,
)

logger = structlog.get_logger()


class CarbonFactorGuardrailError(ValueError):
    pass


class CarbonFactorService:
    """
    Manage carbon factor set lifecycle:
    - seed builtin factors
    - stage factor updates
    - activate staged updates (manual/auto with guardrails)
    - provide active payload for calculation/evidence
    """

    # Guardrails for auto-activation to prevent silently changing customer reporting.
    MAX_DEFAULT_INTENSITY_PCT_CHANGE = 0.50  # 50%
    MAX_DEFAULT_INTENSITY_GCO2_KWH = 2000

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _parse_factor_date(value: Any) -> date:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            # Accept YYYY-MM-DD or full ISO timestamps.
            raw = value.strip()
            return date.fromisoformat(raw[:10])
        raise ValueError(f"Invalid factor_timestamp: {value!r}")

    @staticmethod
    def _validate_payload(payload: dict[str, Any]) -> None:
        required_keys = {
            "region_carbon_intensity",
            "service_energy_factors_by_provider",
            "cloud_pue",
            "embodied_emissions_factor",
            "factor_source",
            "factor_version",
            "factor_timestamp",
            "methodology_version",
        }
        missing = [key for key in sorted(required_keys) if key not in payload]
        if missing:
            raise ValueError(
                f"Carbon factor payload is missing required keys: {', '.join(missing)}"
            )

        region_intensity = payload.get("region_carbon_intensity")
        if not isinstance(region_intensity, dict) or not region_intensity:
            raise ValueError("region_carbon_intensity must be a non-empty object")
        if "default" not in region_intensity:
            raise ValueError("region_carbon_intensity must include a 'default' entry")

        energy_factors = payload.get("service_energy_factors_by_provider")
        if not isinstance(energy_factors, dict) or not energy_factors:
            raise ValueError(
                "service_energy_factors_by_provider must be a non-empty object"
            )

        for key in ("cloud_pue", "embodied_emissions_factor"):
            value = payload.get(key)
            if not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f"{key} must be a positive number")

        for key in ("factor_source", "factor_version", "methodology_version"):
            value = payload.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} must be a non-empty string")

        _ = CarbonFactorService._parse_factor_date(payload.get("factor_timestamp"))

    async def get_active(self) -> CarbonFactorSet | None:
        stmt = (
            select(CarbonFactorSet)
            .where(CarbonFactorSet.is_active.is_(True))
            .order_by(
                desc(CarbonFactorSet.activated_at), desc(CarbonFactorSet.created_at)
            )
            .limit(1)
        )
        from typing import cast
        return cast(CarbonFactorSet | None, await self.db.scalar(stmt))

    async def ensure_active(self) -> CarbonFactorSet:
        active = await self.get_active()
        if active is not None:
            return active

        payload = build_carbon_factor_payload()
        checksum = compute_carbon_factor_checksum(payload)
        factor_timestamp = self._parse_factor_date(payload.get("factor_timestamp"))
        now = datetime.now(timezone.utc)

        seeded = CarbonFactorSet(
            status="active",
            is_active=True,
            factor_source=str(payload.get("factor_source")),
            factor_version=str(payload.get("factor_version")),
            factor_timestamp=factor_timestamp,
            methodology_version=str(payload.get("methodology_version")),
            factors_checksum_sha256=checksum,
            payload=payload,
            activated_at=now,
        )
        self.db.add(seeded)
        await self.db.flush()

        self.db.add(
            CarbonFactorUpdateLog(
                action="seeded",
                message="Seeded builtin carbon factor set",
                old_factor_set_id=None,
                new_factor_set_id=seeded.id,
                old_checksum_sha256=None,
                new_checksum_sha256=checksum,
                details={"factor_version": seeded.factor_version},
                actor_user_id=None,
            )
        )
        await self.db.flush()
        # Persist the seeded factor set even when called from read-only endpoints
        # (for example GET /api/v1/carbon). Without this, the seed is rolled back
        # when the request-scoped session closes.
        try:
            await self.db.commit()
        except IntegrityError:
            # Concurrency: multiple workers may try to seed at the same time.
            # Roll back and return whichever active factor set won.
            await self.db.rollback()
            active = await self.get_active()
            if active is not None:
                return active
            raise
        logger.info(
            "carbon_factors_seeded",
            factor_set_id=str(seeded.id),
            version=seeded.factor_version,
        )
        return seeded

    async def stage(
        self,
        payload: dict[str, Any],
        *,
        actor_user_id: UUID | None = None,
        message: str | None = None,
    ) -> CarbonFactorSet:
        self._validate_payload(payload)
        checksum = compute_carbon_factor_checksum(payload)
        factor_timestamp = self._parse_factor_date(payload.get("factor_timestamp"))

        existing = await self.db.scalar(
            select(CarbonFactorSet)
            .where(CarbonFactorSet.factors_checksum_sha256 == checksum)
            .limit(1)
        )
        if existing is not None:
            return existing

        staged = CarbonFactorSet(
            status="staged",
            is_active=False,
            factor_source=str(payload.get("factor_source")),
            factor_version=str(payload.get("factor_version")),
            factor_timestamp=factor_timestamp,
            methodology_version=str(payload.get("methodology_version")),
            factors_checksum_sha256=checksum,
            payload=payload,
            created_by_user_id=actor_user_id,
        )
        self.db.add(staged)
        await self.db.flush()

        self.db.add(
            CarbonFactorUpdateLog(
                action="staged",
                message=message,
                old_factor_set_id=None,
                new_factor_set_id=staged.id,
                old_checksum_sha256=None,
                new_checksum_sha256=checksum,
                details={
                    "factor_version": staged.factor_version,
                    "factor_timestamp": staged.factor_timestamp.isoformat(),
                },
                actor_user_id=actor_user_id,
            )
        )
        await self.db.flush()
        return staged

    async def activate(
        self,
        factor_set: CarbonFactorSet,
        *,
        actor_user_id: UUID | None = None,
        action: str = "manual_activated",
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> CarbonFactorSet:
        active = await self.ensure_active()
        if factor_set.id == active.id and factor_set.is_active:
            return factor_set

        now = datetime.now(timezone.utc)
        active.is_active = False
        active.status = "archived"
        active.deactivated_at = now
        self.db.add(active)

        factor_set.is_active = True
        factor_set.status = "active"
        factor_set.activated_at = now
        factor_set.deactivated_at = None
        self.db.add(factor_set)

        self.db.add(
            CarbonFactorUpdateLog(
                action=action,
                message=message,
                old_factor_set_id=active.id,
                new_factor_set_id=factor_set.id,
                old_checksum_sha256=active.factors_checksum_sha256,
                new_checksum_sha256=factor_set.factors_checksum_sha256,
                details=details or {},
                actor_user_id=actor_user_id,
            )
        )
        await self.db.flush()
        logger.info(
            "carbon_factors_activated",
            action=action,
            old_factor_set_id=str(active.id),
            new_factor_set_id=str(factor_set.id),
            version=factor_set.factor_version,
        )
        return factor_set

    def _guardrail_auto_activation(
        self, *, active: CarbonFactorSet, candidate: CarbonFactorSet
    ) -> None:
        if candidate.factor_timestamp <= active.factor_timestamp:
            raise CarbonFactorGuardrailError(
                "Candidate factor_timestamp must be newer than the active factor set."
            )

        old_default = int(
            (active.payload or {}).get("region_carbon_intensity", {}).get("default", 0)
            or 0
        )
        new_default = int(
            (candidate.payload or {})
            .get("region_carbon_intensity", {})
            .get("default", 0)
            or 0
        )
        if new_default <= 0 or new_default > self.MAX_DEFAULT_INTENSITY_GCO2_KWH:
            raise CarbonFactorGuardrailError(
                f"Candidate default region intensity is out of bounds: {new_default} gCO2/kWh."
            )
        if old_default > 0:
            pct_change = abs(new_default - old_default) / old_default
            if pct_change > self.MAX_DEFAULT_INTENSITY_PCT_CHANGE:
                raise CarbonFactorGuardrailError(
                    f"Candidate default region intensity changes by {pct_change:.0%} which exceeds "
                    f"the auto-activation guardrail ({self.MAX_DEFAULT_INTENSITY_PCT_CHANGE:.0%})."
                )

    async def auto_activate_latest(self) -> dict[str, Any]:
        active = await self.ensure_active()
        candidate = await self.db.scalar(
            select(CarbonFactorSet)
            .where(CarbonFactorSet.status == "staged")
            .order_by(
                desc(CarbonFactorSet.factor_timestamp), desc(CarbonFactorSet.created_at)
            )
            .limit(1)
        )
        if candidate is None:
            return {"status": "no_update", "active_factor_set_id": str(active.id)}

        if candidate.factors_checksum_sha256 == active.factors_checksum_sha256:
            candidate.status = "archived"
            self.db.add(candidate)
            await self.db.flush()
            return {"status": "duplicate", "active_factor_set_id": str(active.id)}

        try:
            self._guardrail_auto_activation(active=active, candidate=candidate)
        except CarbonFactorGuardrailError as exc:
            candidate.status = "blocked"
            self.db.add(candidate)
            self.db.add(
                CarbonFactorUpdateLog(
                    action="blocked_guardrail",
                    message=str(exc),
                    old_factor_set_id=active.id,
                    new_factor_set_id=candidate.id,
                    old_checksum_sha256=active.factors_checksum_sha256,
                    new_checksum_sha256=candidate.factors_checksum_sha256,
                    details={
                        "active_version": active.factor_version,
                        "candidate_version": candidate.factor_version,
                        "active_timestamp": active.factor_timestamp.isoformat(),
                        "candidate_timestamp": candidate.factor_timestamp.isoformat(),
                    },
                    actor_user_id=None,
                )
            )
            await self.db.flush()
            return {
                "status": "blocked_guardrail",
                "reason": str(exc),
                "active_factor_set_id": str(active.id),
                "candidate_factor_set_id": str(candidate.id),
            }

        await self.activate(
            candidate,
            actor_user_id=None,
            action="auto_activated",
            message="Auto-activated staged carbon factor update after guardrails passed.",
            details={
                "active_version": active.factor_version,
                "candidate_version": candidate.factor_version,
            },
        )
        return {
            "status": "activated",
            "active_factor_set_id": str(candidate.id),
            "version": candidate.factor_version,
        }

    async def get_active_payload(self) -> dict[str, Any]:
        active = await self.ensure_active()
        if not isinstance(active.payload, dict):
            return build_carbon_factor_payload()
        return dict(active.payload)
