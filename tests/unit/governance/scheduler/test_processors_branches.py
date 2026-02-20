from __future__ import annotations

import asyncio
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.remediation import RemediationAction
from app.modules.governance.domain.scheduler.processors import (
    AnalysisProcessor,
    SavingsProcessor,
)


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


def _make_tenant() -> MagicMock:
    tenant = MagicMock()
    tenant.id = uuid4()
    tenant.name = "Tenant A"
    tenant.notification_settings = MagicMock(
        slack_enabled=False,
        digest_schedule="daily",
        slack_channel_override=None,
    )
    tenant.aws_connections = []
    tenant.azure_connections = []
    tenant.gcp_connections = []
    tenant.saas_connections = []
    tenant.license_connections = []
    tenant.platform_connections = []
    tenant.hybrid_connections = []
    return tenant


def test_collect_connections_and_row_normalization_branches() -> None:
    processor = AnalysisProcessor()
    tenant = _make_tenant()
    tenant.aws_connections = [MagicMock(provider="aws")]
    tenant.saas_connections = [MagicMock(provider="saas")]
    tenant.license_connections = [MagicMock(provider="license")]
    tenant.platform_connections = [MagicMock(provider="platform")]
    tenant.hybrid_connections = [MagicMock(provider="hybrid")]

    connections = processor._collect_connections(tenant)
    assert len(connections) == 5

    naive = datetime(2026, 1, 1, 12, 0, 0)
    assert processor._as_datetime(naive).tzinfo is not None
    assert processor._as_datetime(date(2026, 1, 2)).tzinfo is not None
    assert processor._as_datetime("bad").tzinfo is not None

    summary = processor._build_usage_summary_from_rows(
        rows=[
            {"cost_usd": 0},
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "cost_usd": "10.5",
                "amount_raw": "2",
                "currency": None,
                "service": None,
                "tags": "invalid",
            },
        ],
        tenant_id=str(tenant.id),
        provider="saas",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
    )
    assert summary is not None
    assert float(summary.total_cost) == 10.5
    assert summary.records[0].currency == "USD"
    assert summary.records[0].service == "unknown"
    assert summary.records[0].tags == {}

    empty = processor._build_usage_summary_from_rows(
        rows=[{"cost_usd": -1}],
        tenant_id=str(tenant.id),
        provider="saas",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
    )
    assert empty is None


@pytest.mark.asyncio
async def test_process_tenant_no_connections_short_circuit(mock_db: AsyncMock) -> None:
    processor = AnalysisProcessor()
    tenant = _make_tenant()

    with patch(
        "app.modules.governance.domain.scheduler.processors.LLMFactory.create"
    ) as llm_create:
        await processor.process_tenant(mock_db, tenant, date.today(), date.today())
    llm_create.assert_not_called()


@pytest.mark.asyncio
async def test_process_tenant_unsupported_provider_skips_zombie_detection(
    mock_db: AsyncMock,
) -> None:
    processor = AnalysisProcessor()
    tenant = _make_tenant()
    conn = MagicMock()
    conn.id = uuid4()
    conn.provider = "custom_provider"
    tenant.saas_connections = [conn]

    adapter = MagicMock()
    adapter.get_cost_and_usage = AsyncMock(
        return_value=[
            {"timestamp": "2026-02-01T00:00:00Z", "cost_usd": 5, "service": "custom"}
        ]
    )

    analyzer = MagicMock()
    analyzer.analyze = AsyncMock(return_value={"recommendations": [], "insights": []})

    carbon_calc = MagicMock()
    carbon_calc.calculate_from_costs.return_value = {"total_co2_kg": 1}

    with (
        patch(
            "app.modules.governance.domain.scheduler.processors.AdapterFactory.get_adapter",
            return_value=adapter,
        ),
        patch(
            "app.modules.governance.domain.scheduler.processors.LLMFactory.create",
            return_value=MagicMock(),
        ),
        patch(
            "app.modules.governance.domain.scheduler.processors.FinOpsAnalyzer",
            return_value=analyzer,
        ),
        patch(
            "app.modules.governance.domain.scheduler.processors.CarbonCalculator",
            return_value=carbon_calc,
        ),
        patch(
            "app.modules.governance.domain.scheduler.processors.ZombieDetectorFactory.get_detector"
        ) as get_detector,
    ):
        await processor.process_tenant(mock_db, tenant, date.today(), date.today())

    get_detector.assert_not_called()
    analyzer.analyze.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_tenant_slack_digest_and_zombie_error_branch(
    mock_db: AsyncMock,
) -> None:
    processor = AnalysisProcessor()

    tenant = _make_tenant()
    tenant.notification_settings.slack_enabled = True
    tenant.notification_settings.digest_schedule = "weekly"
    tenant.notification_settings.slack_channel_override = "#override"

    conn = MagicMock()
    conn.id = uuid4()
    conn.provider = "aws"
    conn.region = "us-east-1"
    tenant.aws_connections = [conn]

    usage_summary = MagicMock()
    usage_summary.records = [MagicMock(amount=12.0, service="EC2")]
    usage_summary.total_cost = 12.0

    adapter = MagicMock()
    adapter.get_daily_costs = AsyncMock(return_value=usage_summary)

    analyzer = MagicMock()
    analyzer.analyze = AsyncMock(return_value={"recommendations": [], "insights": []})

    carbon_calc = MagicMock()
    carbon_calc.calculate_from_costs.return_value = {"total_co2_kg": 3.2}

    slack_instance = MagicMock()
    slack_instance.send_digest = AsyncMock()

    with (
        patch(
            "app.modules.governance.domain.scheduler.processors.AdapterFactory.get_adapter",
            return_value=adapter,
        ),
        patch(
            "app.modules.governance.domain.scheduler.processors.LLMFactory.create",
            return_value=MagicMock(),
        ),
        patch(
            "app.modules.governance.domain.scheduler.processors.FinOpsAnalyzer",
            return_value=analyzer,
        ),
        patch(
            "app.modules.governance.domain.scheduler.processors.CarbonCalculator",
            return_value=carbon_calc,
        ),
        patch(
            "app.modules.governance.domain.scheduler.processors.ZombieDetectorFactory.get_detector",
            side_effect=RuntimeError("detector unavailable"),
        ),
        patch(
            "app.modules.notifications.domain.get_tenant_slack_service",
            new=AsyncMock(return_value=slack_instance),
        ),
    ):
        await processor.process_tenant(mock_db, tenant, date.today(), date.today())

    slack_instance.send_digest.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_tenant_connection_timeout_and_error_paths(
    mock_db: AsyncMock,
) -> None:
    processor = AnalysisProcessor()
    tenant = _make_tenant()
    conn1 = MagicMock()
    conn1.id = uuid4()
    conn1.provider = "aws"
    conn2 = MagicMock()
    conn2.id = uuid4()
    conn2.provider = "aws"
    tenant.aws_connections = [conn1, conn2]

    timeout_adapter = MagicMock()
    timeout_adapter.get_daily_costs = AsyncMock(side_effect=asyncio.TimeoutError())
    failure_adapter = MagicMock()
    failure_adapter.get_daily_costs = AsyncMock(side_effect=RuntimeError("boom"))

    with (
        patch(
            "app.modules.governance.domain.scheduler.processors.AdapterFactory.get_adapter",
            side_effect=[timeout_adapter, failure_adapter],
        ),
        patch(
            "app.modules.governance.domain.scheduler.processors.LLMFactory.create",
            return_value=MagicMock(),
        ),
        patch(
            "app.modules.governance.domain.scheduler.processors.FinOpsAnalyzer",
            return_value=MagicMock(analyze=AsyncMock()),
        ),
        patch(
            "app.modules.governance.domain.scheduler.processors.CarbonCalculator",
            return_value=MagicMock(
                calculate_from_costs=MagicMock(return_value={"total_co2_kg": 0})
            ),
        ),
    ):
        await processor.process_tenant(mock_db, tenant, date.today(), date.today())


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("delete volume now", RemediationAction.DELETE_VOLUME),
        ("Stop Instance", RemediationAction.STOP_INSTANCE),
        ("terminate instance", RemediationAction.TERMINATE_INSTANCE),
        ("deallocate azure vm", RemediationAction.DEALLOCATE_AZURE_VM),
        ("stop gcp instance", RemediationAction.STOP_GCP_INSTANCE),
        ("resize this", RemediationAction.RESIZE_INSTANCE),
        ("delete snapshot old", RemediationAction.DELETE_SNAPSHOT),
        ("release elastic ip", RemediationAction.RELEASE_ELASTIC_IP),
        ("stop rds", RemediationAction.STOP_RDS_INSTANCE),
        ("delete rds", RemediationAction.DELETE_RDS_INSTANCE),
        ("revoke github seat", RemediationAction.REVOKE_GITHUB_SEAT),
        ("reclaim license seat", RemediationAction.RECLAIM_LICENSE_SEAT),
        ("manual review required", RemediationAction.MANUAL_REVIEW),
        ("no match", None),
    ],
)
def test_map_action_to_enum(text: str, expected: RemediationAction | None) -> None:
    processor = SavingsProcessor()
    assert processor._map_action_to_enum(text) == expected


@pytest.mark.asyncio
async def test_savings_processor_non_safe_action_and_parse_fallback(
    mock_db: AsyncMock,
) -> None:
    processor = SavingsProcessor()
    tenant_id = uuid4()

    rec = MagicMock()
    rec.autonomous_ready = True
    rec.confidence = "0.95"
    rec.action = "Delete Volume"
    rec.resource = "vol-1"
    rec.resource_type = "ebs"
    rec.estimated_savings = "not-a-number"

    analysis_result = MagicMock(recommendations=[rec])

    with patch(
        "app.modules.optimization.domain.remediation.RemediationService"
    ) as remediation_cls:
        remediation = remediation_cls.return_value
        remediation.create_request = AsyncMock(return_value=MagicMock(id=uuid4()))
        remediation.approve = AsyncMock()
        remediation.execute = AsyncMock()

        await processor.process_recommendations(
            mock_db, tenant_id, analysis_result, provider="aws"
        )

    remediation.create_request.assert_awaited_once()
    remediation.approve.assert_not_awaited()
    remediation.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_savings_processor_unsupported_and_execution_error(
    mock_db: AsyncMock,
) -> None:
    processor = SavingsProcessor()
    tenant_id = uuid4()

    unsupported = MagicMock(
        autonomous_ready=True,
        confidence="high",
        action="Do Magic",
        resource="r1",
        resource_type="unknown",
        estimated_savings="$2/month",
    )
    safe = MagicMock(
        autonomous_ready=True,
        confidence="high",
        action="Stop Instance",
        resource="i-1",
        resource_type="ec2",
        estimated_savings="$2/month",
    )
    low_confidence = MagicMock(
        autonomous_ready=True,
        confidence="0.2",
        action="Stop Instance",
        resource="i-2",
        resource_type="ec2",
        estimated_savings="$2/month",
    )

    analysis_result = MagicMock(recommendations=[unsupported, safe, low_confidence])

    with patch(
        "app.modules.optimization.domain.remediation.RemediationService"
    ) as remediation_cls:
        remediation = remediation_cls.return_value
        remediation.create_request = AsyncMock(
            side_effect=RuntimeError("request failed")
        )
        remediation.approve = AsyncMock()
        remediation.execute = AsyncMock()

        await processor.process_recommendations(
            mock_db, tenant_id, analysis_result, provider="aws"
        )

    remediation.create_request.assert_awaited_once()
    remediation.approve.assert_not_awaited()
    remediation.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_savings_processor_skips_invalid_provider_before_request(
    mock_db: AsyncMock,
) -> None:
    processor = SavingsProcessor()
    tenant_id = uuid4()
    rec = MagicMock(
        autonomous_ready=True,
        confidence="high",
        action="Stop Instance",
        resource="i-custom",
        resource_type="vm",
        estimated_savings="$12/month",
    )
    analysis_result = MagicMock(recommendations=[rec])

    with patch(
        "app.modules.optimization.domain.remediation.RemediationService"
    ) as remediation_cls:
        remediation = remediation_cls.return_value
        remediation.create_request = AsyncMock()
        remediation.approve = AsyncMock()
        remediation.execute = AsyncMock()

        await processor.process_recommendations(
            mock_db,
            tenant_id,
            analysis_result,
            provider="custom_provider",
        )

    remediation.create_request.assert_not_awaited()
    remediation.approve.assert_not_awaited()
    remediation.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_savings_processor_forwards_provider_and_connection_id(
    mock_db: AsyncMock,
) -> None:
    processor = SavingsProcessor()
    tenant_id = uuid4()
    connection_id = uuid4()
    rec = MagicMock(
        autonomous_ready=True,
        confidence="high",
        action="Stop Instance",
        resource="resource-1",
        resource_type="vm",
        estimated_savings="$8/month",
    )
    analysis_result = MagicMock(recommendations=[rec])

    created_request = MagicMock(id=uuid4())
    executed_request = MagicMock(status=MagicMock(value="completed"))
    with patch(
        "app.modules.optimization.domain.remediation.RemediationService"
    ) as remediation_cls:
        remediation = remediation_cls.return_value
        remediation.create_request = AsyncMock(return_value=created_request)
        remediation.approve = AsyncMock()
        remediation.execute = AsyncMock(return_value=executed_request)

        await processor.process_recommendations(
            mock_db,
            tenant_id,
            analysis_result,
            provider="platform",
            connection_id=connection_id,
        )

    remediation.create_request.assert_awaited_once()
    forwarded_kwargs = remediation.create_request.await_args.kwargs
    assert forwarded_kwargs["provider"] == "platform"
    assert forwarded_kwargs["connection_id"] == connection_id
