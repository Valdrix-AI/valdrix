"""
Analysis and Report Job Handlers
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_job import BackgroundJob
from app.modules.governance.domain.jobs.handlers.base import BaseJobHandler


def _parse_iso_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError("Expected ISO date string")


class ZombieAnalysisHandler(BaseJobHandler):
    """Run async AI analysis over already-detected zombie payload."""

    timeout_seconds = 300

    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        tenant_id = job.tenant_id
        if tenant_id is None:
            raise ValueError("tenant_id required for zombie_analysis")

        payload = job.payload or {}
        zombies_payload = payload.get("zombies")
        if not isinstance(zombies_payload, dict):
            raise ValueError("zombies payload required for zombie_analysis")
        requested_by_user_id_raw = payload.get("requested_by_user_id")
        requested_by_user_id: UUID | None = None
        if requested_by_user_id_raw is not None:
            try:
                requested_by_user_id = UUID(str(requested_by_user_id_raw))
            except (TypeError, ValueError):
                requested_by_user_id = None
        requested_client_ip = payload.get("requested_client_ip")
        if not isinstance(requested_client_ip, str):
            requested_client_ip = None

        tenant_uuid = UUID(str(tenant_id))
        from app.shared.core.pricing import (
            FeatureFlag,
            get_tenant_tier,
            is_feature_enabled,
        )

        tier = await get_tenant_tier(tenant_uuid, db)
        if not is_feature_enabled(tier, FeatureFlag.LLM_ANALYSIS):
            tier_value = tier.value if hasattr(tier, "value") else str(tier)
            return {
                "status": "skipped",
                "tenant_id": str(tenant_uuid),
                "reason": "llm_analysis_not_enabled",
                "tier": tier_value,
            }

        from app.shared.llm.factory import LLMFactory
        from app.shared.llm.zombie_analyzer import ZombieAnalyzer

        analyzer = ZombieAnalyzer(LLMFactory.create())
        ai_analysis = await analyzer.analyze(
            detection_results=zombies_payload,
            tenant_id=tenant_uuid,
            db=db,
            user_id=requested_by_user_id,
            client_ip=requested_client_ip,
        )

        return {
            "status": "completed",
            "tenant_id": str(tenant_uuid),
            "analysis": ai_analysis,
        }


class ReportGenerationHandler(BaseJobHandler):
    """
    Generate deterministic reporting artifacts via domain services.

    Supported payload values:
    - report_type: close_package | leadership_kpis
    - start_date/end_date: ISO date strings (defaults to trailing 30-day window)
    - provider: optional provider filter
    """

    timeout_seconds = 600

    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        tenant_id = job.tenant_id
        if tenant_id is None:
            raise ValueError("tenant_id required for report_generation")

        payload = job.payload or {}
        report_type = str(payload.get("report_type") or "close_package").strip().lower()
        end_date = (
            _parse_iso_date(payload["end_date"])
            if payload.get("end_date")
            else date.today()
        )
        start_date = (
            _parse_iso_date(payload["start_date"])
            if payload.get("start_date")
            else end_date - timedelta(days=30)
        )
        provider = payload.get("provider")
        tenant_uuid = UUID(str(tenant_id))

        if report_type == "close_package":
            from app.modules.reporting.domain.reconciliation import (
                CostReconciliationService,
            )

            close_package = await CostReconciliationService(db).generate_close_package(
                tenant_id=tenant_uuid,
                start_date=start_date,
                end_date=end_date,
                enforce_finalized=bool(payload.get("enforce_finalized", True)),
                provider=provider if isinstance(provider, str) else None,
                max_restatement_entries=(
                    int(payload["max_restatement_entries"])
                    if payload.get("max_restatement_entries") is not None
                    else None
                ),
            )
            return {
                "status": "completed",
                "tenant_id": str(tenant_uuid),
                "report_type": "close_package",
                "report": close_package,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        if report_type == "leadership_kpis":
            from app.modules.reporting.domain.leadership_kpis import LeadershipKpiService
            from app.shared.core.pricing import get_tenant_tier

            tier = await get_tenant_tier(tenant_uuid, db)
            leadership_payload = await LeadershipKpiService(db).compute(
                tenant_id=tenant_uuid,
                tier=tier,
                start_date=start_date,
                end_date=end_date,
                provider=provider if isinstance(provider, str) else None,
                include_preliminary=bool(payload.get("include_preliminary", False)),
                top_services_limit=int(payload.get("top_services_limit", 10)),
            )
            return {
                "status": "completed",
                "tenant_id": str(tenant_uuid),
                "report_type": "leadership_kpis",
                "report": leadership_payload.model_dump()
                if hasattr(leadership_payload, "model_dump")
                else leadership_payload,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        raise ValueError(
            "Unsupported report_type. Expected one of: close_package, leadership_kpis"
        )
