from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.modules.optimization.adapters.aws.plugins import storage as storage_plugins


class AsyncContext:
    def __init__(self, obj):
        self._obj = obj

    async def __aenter__(self):
        return self._obj

    async def __aexit__(self, *args):
        return None


class FailingAsyncContext:
    def __init__(self, exc: Exception):
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *args):
        return None


class AsyncPaginator:
    def __init__(self, pages):
        self._pages = pages
        self._iter = iter([])

    def paginate(self, *args, **kwargs):
        self._iter = iter(self._pages)
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _client_error(code: str = "AccessDenied", operation: str = "TestOperation") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


def test_storage_plugin_category_keys() -> None:
    assert storage_plugins.UnattachedVolumesPlugin().category_key == "unattached_volumes"
    assert storage_plugins.OldSnapshotsPlugin().category_key == "old_snapshots"
    assert storage_plugins.IdleS3BucketsPlugin().category_key == "idle_s3_buckets"
    assert storage_plugins.EmptyEfsPlugin().category_key == "empty_efs_volumes"


@pytest.mark.asyncio
async def test_unattached_volumes_metric_check_failure_logs_and_still_emits_zombie(monkeypatch):
    plugin = storage_plugins.UnattachedVolumesPlugin()
    ec2 = MagicMock()
    ec2.get_paginator.return_value = AsyncPaginator(
        [
            {
                "Volumes": [
                    {
                        "VolumeId": "vol-err",
                        "Size": 8,
                        "CreateTime": datetime.now(timezone.utc) - timedelta(days=30),
                    }
                ]
            }
        ]
    )
    cloudwatch = MagicMock()
    cloudwatch.get_metric_data = AsyncMock(side_effect=_client_error(operation="GetMetricData"))

    def client_factory(service_name):
        return ec2 if service_name == "ec2" else cloudwatch

    monkeypatch.setattr(
        plugin, "_get_client", lambda *args, **kwargs: AsyncContext(client_factory(args[1]))
    )

    with (
        patch.object(storage_plugins, "logger") as logger_mock,
        patch(
            "app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste",
            side_effect=[12.345, 1.234],
        ),
    ):
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert len(zombies) == 1
    assert zombies[0]["resource_id"] == "vol-err"
    assert zombies[0]["monthly_cost"] == 12.35
    assert zombies[0]["backup_cost_monthly"] == 1.23
    assert zombies[0]["confidence_score"] == 0.98
    logger_mock.warning.assert_called_once()


@pytest.mark.asyncio
async def test_unattached_volumes_skips_when_recent_ops_present(monkeypatch):
    plugin = storage_plugins.UnattachedVolumesPlugin()
    ec2 = MagicMock()
    ec2.get_paginator.return_value = AsyncPaginator(
        [
            {
                "Volumes": [
                    {
                        "VolumeId": "vol-active",
                        "Size": 20,
                        "CreateTime": datetime.now(timezone.utc) - timedelta(days=5),
                    }
                ]
            }
        ]
    )
    cloudwatch = MagicMock()
    cloudwatch.get_metric_data = AsyncMock(
        return_value={"MetricDataResults": [{"Values": [10]}, {"Values": [5]}]}
    )

    def client_factory(service_name):
        return ec2 if service_name == "ec2" else cloudwatch

    monkeypatch.setattr(
        plugin, "_get_client", lambda *args, **kwargs: AsyncContext(client_factory(args[1]))
    )

    with patch(
        "app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste"
    ) as pricing_mock:
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert zombies == []
    pricing_mock.assert_not_called()


@pytest.mark.asyncio
async def test_unattached_volumes_outer_client_error_logs_and_returns_empty(monkeypatch):
    plugin = storage_plugins.UnattachedVolumesPlugin()
    monkeypatch.setattr(
        plugin,
        "_get_client",
        lambda *args, **kwargs: FailingAsyncContext(_client_error(operation="DescribeVolumes")),
    )

    with patch.object(storage_plugins, "logger") as logger_mock:
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert zombies == []
    logger_mock.warning.assert_called_once()
    assert logger_mock.warning.call_args.args[0] == "volume_scan_error"
    assert "DescribeVolumes" in logger_mock.warning.call_args.kwargs["error"]


@pytest.mark.asyncio
async def test_old_snapshots_outer_client_error_logs_and_returns_empty(monkeypatch):
    plugin = storage_plugins.OldSnapshotsPlugin()
    monkeypatch.setattr(
        plugin,
        "_get_client",
        lambda *args, **kwargs: FailingAsyncContext(_client_error(operation="DescribeSnapshots")),
    )

    with patch.object(storage_plugins, "logger") as logger_mock:
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert zombies == []
    logger_mock.warning.assert_called_once()
    assert logger_mock.warning.call_args.args[0] == "snapshot_scan_error"


@pytest.mark.asyncio
async def test_old_snapshots_skips_recent_snapshot(monkeypatch):
    plugin = storage_plugins.OldSnapshotsPlugin()
    recent_time = datetime.now(timezone.utc) - timedelta(days=10)
    ec2 = MagicMock()
    ec2.get_paginator.return_value = AsyncPaginator(
        [{"Snapshots": [{"SnapshotId": "snap-recent", "StartTime": recent_time, "VolumeSize": 5}]}]
    )
    monkeypatch.setattr(plugin, "_get_client", lambda *args, **kwargs: AsyncContext(ec2))

    with patch(
        "app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste"
    ) as pricing_mock:
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert zombies == []
    pricing_mock.assert_not_called()


@pytest.mark.asyncio
async def test_idle_s3_buckets_empty_bucket_detection_and_access_check_warning(monkeypatch):
    plugin = storage_plugins.IdleS3BucketsPlugin()
    s3 = MagicMock()
    s3.list_buckets = AsyncMock(
        return_value={
            "Buckets": [
                {"Name": "empty-bucket"},
                {"Name": "used-bucket"},
                {"Name": "error-bucket"},
            ]
        }
    )
    s3.list_objects_v2 = AsyncMock(
        side_effect=[
            {},  # empty-bucket
            {"Contents": [{"Key": "obj"}]},  # used-bucket
            _client_error(operation="ListObjectsV2"),  # error-bucket
        ]
    )
    s3.list_object_versions = AsyncMock(
        side_effect=[
            {},  # empty-bucket
            {"Versions": [{"VersionId": "1"}]},  # used-bucket
        ]
    )
    monkeypatch.setattr(plugin, "_get_client", lambda *args, **kwargs: AsyncContext(s3))

    with patch.object(storage_plugins, "logger") as logger_mock:
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert len(zombies) == 1
    assert zombies[0]["resource_id"] == "empty-bucket"
    assert zombies[0]["action"] == "delete_s3_bucket"
    logger_mock.warning.assert_called_once()


@pytest.mark.asyncio
async def test_idle_s3_buckets_outer_client_error_logs_and_returns_empty(monkeypatch):
    plugin = storage_plugins.IdleS3BucketsPlugin()
    monkeypatch.setattr(
        plugin,
        "_get_client",
        lambda *args, **kwargs: FailingAsyncContext(_client_error(operation="ListBuckets")),
    )

    with patch.object(storage_plugins, "logger") as logger_mock:
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert zombies == []
    logger_mock.warning.assert_called_once()
    assert logger_mock.warning.call_args.args[0] == "s3_scan_error"


@pytest.mark.asyncio
async def test_empty_efs_plugin_covers_unmounted_zero_conn_and_metric_error(monkeypatch):
    plugin = storage_plugins.EmptyEfsPlugin()
    efs = MagicMock()
    efs.get_paginator.return_value = AsyncPaginator(
        [
            {
                "FileSystems": [
                    {
                        "FileSystemId": "fs-unmounted",
                        "NumberOfMountTargets": 0,
                        "SizeInBytes": {"Value": 10 * (1024**3)},
                    },
                    {
                        "FileSystemId": "fs-idle",
                        "NumberOfMountTargets": 1,
                        "SizeInBytes": {"Value": 2 * (1024**3)},
                    },
                    {
                        "FileSystemId": "fs-metric-error",
                        "NumberOfMountTargets": 1,
                        "SizeInBytes": {"Value": 1 * (1024**3)},
                    },
                ]
            }
        ]
    )
    cloudwatch = MagicMock()
    cloudwatch.get_metric_statistics = AsyncMock(
        side_effect=[
            {"Datapoints": [{"Sum": 0}]},
            _client_error(operation="GetMetricStatistics"),
        ]
    )

    def client_factory(service_name):
        return efs if service_name == "efs" else cloudwatch

    monkeypatch.setattr(
        plugin, "_get_client", lambda *args, **kwargs: AsyncContext(client_factory(args[1]))
    )

    with patch.object(storage_plugins, "logger") as logger_mock:
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert {z["resource_id"] for z in zombies} == {"fs-unmounted", "fs-idle"}
    unmounted = next(z for z in zombies if z["resource_id"] == "fs-unmounted")
    idle = next(z for z in zombies if z["resource_id"] == "fs-idle")
    assert unmounted["confidence_score"] == 1.0
    assert "0 mount targets" in unmounted["explainability_notes"]
    assert idle["confidence_score"] == 0.90
    assert "0 client connections" in idle["explainability_notes"]
    logger_mock.warning.assert_called_once()


@pytest.mark.asyncio
async def test_empty_efs_plugin_skips_when_client_connections_exist(monkeypatch):
    plugin = storage_plugins.EmptyEfsPlugin()
    efs = MagicMock()
    efs.get_paginator.return_value = AsyncPaginator(
        [
            {
                "FileSystems": [
                    {
                        "FileSystemId": "fs-busy",
                        "NumberOfMountTargets": 1,
                        "SizeInBytes": {"Value": 4 * (1024**3)},
                    }
                ]
            }
        ]
    )
    cloudwatch = MagicMock()
    cloudwatch.get_metric_statistics = AsyncMock(return_value={"Datapoints": [{"Sum": 3}]})

    def client_factory(service_name):
        return efs if service_name == "efs" else cloudwatch

    monkeypatch.setattr(
        plugin, "_get_client", lambda *args, **kwargs: AsyncContext(client_factory(args[1]))
    )

    zombies = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert zombies == []


@pytest.mark.asyncio
async def test_empty_efs_plugin_outer_client_error_logs_and_returns_empty(monkeypatch):
    plugin = storage_plugins.EmptyEfsPlugin()
    monkeypatch.setattr(
        plugin,
        "_get_client",
        lambda *args, **kwargs: FailingAsyncContext(
            _client_error(operation="DescribeFileSystems")
        ),
    )

    with patch.object(storage_plugins, "logger") as logger_mock:
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert zombies == []
    logger_mock.warning.assert_called_once()
    assert logger_mock.warning.call_args.args[0] == "efs_scan_error"
