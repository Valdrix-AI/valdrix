from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.optimization.adapters.aws.detector import AWSZombieDetector
from app.modules.optimization.domain.cloud_api_budget import (
    CloudAPIBudgetGovernor,
    cloud_api_scan_context,
)
from app.modules.optimization.domain.plugin import _GuardedCloudWatchClient


@pytest.mark.asyncio
async def test_cloud_api_budget_governor_denies_when_budget_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_settings = SimpleNamespace(
        CLOUD_API_BUDGET_GOVERNOR_ENABLED=True,
        CLOUD_API_BUDGET_ENFORCE=True,
        AWS_CLOUDWATCH_DAILY_CALL_BUDGET=1,
        GCP_MONITORING_DAILY_CALL_BUDGET=10,
        AZURE_MONITOR_DAILY_CALL_BUDGET=10,
        AWS_CLOUDWATCH_ESTIMATED_COST_PER_CALL_USD=0.00001,
        GCP_MONITORING_ESTIMATED_COST_PER_CALL_USD=0.0,
        AZURE_MONITOR_ESTIMATED_COST_PER_CALL_USD=0.0,
    )

    import app.modules.optimization.domain.cloud_api_budget as budget_module

    monkeypatch.setattr(budget_module, "get_settings", lambda: fake_settings)

    governor = CloudAPIBudgetGovernor()
    with cloud_api_scan_context(
        tenant_id="tenant-1",
        provider="aws",
        connection_id="conn-1",
        region="us-east-1",
        plugin="idle_instances",
    ):
        assert await governor.consume("aws_cloudwatch", operation="get_metric_data")
        assert not await governor.consume(
            "aws_cloudwatch", operation="get_metric_data"
        )


@pytest.mark.asyncio
async def test_cloud_api_budget_governor_observe_mode_allows(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_settings = SimpleNamespace(
        CLOUD_API_BUDGET_GOVERNOR_ENABLED=True,
        CLOUD_API_BUDGET_ENFORCE=False,
        AWS_CLOUDWATCH_DAILY_CALL_BUDGET=1,
        GCP_MONITORING_DAILY_CALL_BUDGET=10,
        AZURE_MONITOR_DAILY_CALL_BUDGET=10,
        AWS_CLOUDWATCH_ESTIMATED_COST_PER_CALL_USD=0.00001,
        GCP_MONITORING_ESTIMATED_COST_PER_CALL_USD=0.0,
        AZURE_MONITOR_ESTIMATED_COST_PER_CALL_USD=0.0,
    )

    import app.modules.optimization.domain.cloud_api_budget as budget_module

    monkeypatch.setattr(budget_module, "get_settings", lambda: fake_settings)

    governor = CloudAPIBudgetGovernor()
    with cloud_api_scan_context(
        tenant_id="tenant-2",
        provider="aws",
        connection_id="conn-2",
        region="us-east-1",
        plugin="idle_instances",
    ):
        assert await governor.consume("aws_cloudwatch", operation="get_metric_data")
        assert await governor.consume("aws_cloudwatch", operation="get_metric_data")


@pytest.mark.asyncio
async def test_guarded_cloudwatch_returns_empty_payload_when_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SimpleNamespace(get_metric_statistics=AsyncMock(return_value={"Datapoints": [1]}))

    import app.modules.optimization.domain.cloud_api_budget as budget_module

    monkeypatch.setattr(
        budget_module,
        "allow_expensive_cloud_api_call",
        AsyncMock(return_value=False),
    )

    guarded = _GuardedCloudWatchClient(client)
    response = await guarded.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName="CPUUtilization",
    )

    assert response == {"Datapoints": []}
    client.get_metric_statistics.assert_not_awaited()


@pytest.mark.asyncio
async def test_guarded_cloudwatch_executes_when_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {"MetricDataResults": [{"Id": "m1", "Values": [0.1]}]}
    client = SimpleNamespace(get_metric_data=AsyncMock(return_value=expected))

    import app.modules.optimization.domain.cloud_api_budget as budget_module

    monkeypatch.setattr(
        budget_module,
        "allow_expensive_cloud_api_call",
        AsyncMock(return_value=True),
    )

    guarded = _GuardedCloudWatchClient(client)
    response = await guarded.get_metric_data(MetricDataQueries=[])

    assert response == expected
    client.get_metric_data.assert_awaited_once()


def test_aws_detector_initializes_all_registered_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy_plugins = [
        SimpleNamespace(category_key="canonical_a"),
        SimpleNamespace(category_key="noncanonical_new_plugin"),
    ]

    monkeypatch.setattr(
        "app.modules.optimization.adapters.aws.detector.registry.get_plugins_for_provider",
        lambda provider: dummy_plugins,
    )
    monkeypatch.setattr("app.modules.optimization.adapters.aws.detector.aioboto3.Session", lambda: object())

    detector = AWSZombieDetector(region="us-east-1")
    assert detector.plugins == dummy_plugins


@pytest.mark.asyncio
async def test_cloud_api_budget_governor_disabled_allows(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_settings = SimpleNamespace(
        CLOUD_API_BUDGET_GOVERNOR_ENABLED=False,
        CLOUD_API_BUDGET_ENFORCE=True,
        AWS_CLOUDWATCH_DAILY_CALL_BUDGET=1,
        GCP_MONITORING_DAILY_CALL_BUDGET=1,
        AZURE_MONITOR_DAILY_CALL_BUDGET=1,
        AWS_CLOUDWATCH_ESTIMATED_COST_PER_CALL_USD=0.001,
        GCP_MONITORING_ESTIMATED_COST_PER_CALL_USD=0.001,
        AZURE_MONITOR_ESTIMATED_COST_PER_CALL_USD=0.001,
    )

    import app.modules.optimization.domain.cloud_api_budget as budget_module

    monkeypatch.setattr(budget_module, "get_settings", lambda: fake_settings)

    governor = CloudAPIBudgetGovernor()
    assert await governor.consume("gcp_monitoring", units=2, operation="list_time_series")


@pytest.mark.asyncio
async def test_cloud_api_budget_governor_ignores_non_positive_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_settings = SimpleNamespace(
        CLOUD_API_BUDGET_GOVERNOR_ENABLED=True,
        CLOUD_API_BUDGET_ENFORCE=True,
        AWS_CLOUDWATCH_DAILY_CALL_BUDGET=1,
        GCP_MONITORING_DAILY_CALL_BUDGET=1,
        AZURE_MONITOR_DAILY_CALL_BUDGET=1,
        AWS_CLOUDWATCH_ESTIMATED_COST_PER_CALL_USD=0.001,
        GCP_MONITORING_ESTIMATED_COST_PER_CALL_USD=0.001,
        AZURE_MONITOR_ESTIMATED_COST_PER_CALL_USD=0.001,
    )

    import app.modules.optimization.domain.cloud_api_budget as budget_module

    monkeypatch.setattr(budget_module, "get_settings", lambda: fake_settings)

    governor = CloudAPIBudgetGovernor()
    assert await governor.consume("aws_cloudwatch", units=0, operation="get_metric_data")
