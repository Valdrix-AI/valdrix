from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.governance.domain.jobs.cur_ingestion import CURIngestionJob


def _scalars_result(rows: list[object]) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


def _conn(**overrides: object) -> SimpleNamespace:
    base = {
        "id": "conn-1",
        "region": "us-east-1",
        "cur_prefix": "cur",
        "cur_report_name": "valdrix-cur",
        "aws_account_id": "123456789012",
        "cur_bucket_name": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_execute_raises_when_no_db_session_available() -> None:
    job = CURIngestionJob()
    with pytest.raises(RuntimeError, match="Database session is required"):
        await job._execute(tenant_id="tenant-1")


@pytest.mark.asyncio
async def test_execute_with_connection_id_filter_path_calls_ingest_once() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalars_result([_conn(id="conn-9")]))
    job = CURIngestionJob(db=db)

    with patch.object(job, "ingest_for_connection", new=AsyncMock()) as ingest_mock:
        await job._execute(connection_id="conn-9", tenant_id="tenant-1")

    db.execute.assert_awaited_once()
    ingest_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_find_latest_cur_key_warns_when_no_manifest_files_exist() -> None:
    job = CURIngestionJob()
    conn = _conn()
    mock_s3 = MagicMock()
    mock_s3.list_objects_v2.return_value = {
        "Contents": [
            {
                "Key": "cur/valdrix-cur/2026-02-01/data.parquet",
                "LastModified": datetime(2026, 2, 1, tzinfo=timezone.utc),
            }
        ]
    }

    with (
        patch(
            "app.modules.governance.domain.jobs.cur_ingestion.resolve_aws_region_hint",
            return_value="us-east-1",
        ),
        patch("boto3.client", return_value=mock_s3),
        patch("app.modules.governance.domain.jobs.cur_ingestion.logger") as logger_mock,
    ):
        key = await job._find_latest_cur_key(conn, "cur-bucket")

    assert key is None
    logger_mock.warning.assert_called_once_with(
        "cur_manifest_not_found", bucket="cur-bucket", report="valdrix-cur"
    )


@pytest.mark.asyncio
async def test_find_latest_cur_key_warns_when_manifest_has_no_report_keys() -> None:
    job = CURIngestionJob()
    conn = _conn()
    mock_s3 = MagicMock()
    manifest_key = "cur/valdrix-cur/2026-02-01/valdrix-cur-Manifest.json"
    mock_s3.list_objects_v2.return_value = {
        "Contents": [
            {
                "Key": manifest_key,
                "LastModified": datetime(2026, 2, 1, tzinfo=timezone.utc),
            }
        ]
    }
    body = MagicMock()
    body.read.return_value = b'{"reportKeys": []}'
    mock_s3.get_object.return_value = {"Body": body}

    with (
        patch(
            "app.modules.governance.domain.jobs.cur_ingestion.resolve_aws_region_hint",
            return_value="us-east-1",
        ),
        patch("boto3.client", return_value=mock_s3),
        patch("app.modules.governance.domain.jobs.cur_ingestion.logger") as logger_mock,
    ):
        key = await job._find_latest_cur_key(conn, "cur-bucket")

    assert key is None
    logger_mock.warning.assert_called_once_with(
        "cur_manifest_empty_files", manifest=manifest_key
    )


@pytest.mark.asyncio
async def test_find_latest_cur_key_returns_first_report_key_from_latest_manifest() -> None:
    job = CURIngestionJob()
    conn = _conn(cur_prefix="", cur_report_name="cost-report")
    mock_s3 = MagicMock()
    older = "cost-report/2026-01-01/cost-report-Manifest.json"
    newer = "cost-report/2026-02-01/cost-report-Manifest.json"
    mock_s3.list_objects_v2.return_value = {
        "Contents": [
            {"Key": older, "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc)},
            {"Key": newer, "LastModified": datetime(2026, 2, 1, tzinfo=timezone.utc)},
        ]
    }
    body = MagicMock()
    body.read.return_value = (
        b'{"reportKeys": ["cost-report/2026-02-01/part-000.parquet", "other.parquet"]}'
    )
    mock_s3.get_object.return_value = {"Body": body}

    with (
        patch(
            "app.modules.governance.domain.jobs.cur_ingestion.resolve_aws_region_hint",
            return_value="us-west-2",
        ),
        patch("boto3.client", return_value=mock_s3) as client_mock,
    ):
        key = await job._find_latest_cur_key(conn, "cur-bucket")

    assert key == "cost-report/2026-02-01/part-000.parquet"
    client_mock.assert_called_once()
    mock_s3.get_object.assert_called_once_with(Bucket="cur-bucket", Key=newer)


@pytest.mark.asyncio
async def test_find_latest_cur_key_logs_and_reraises_unexpected_error() -> None:
    job = CURIngestionJob()
    conn = _conn()
    mock_s3 = MagicMock()
    mock_s3.list_objects_v2.side_effect = RuntimeError("s3 unavailable")

    with (
        patch(
            "app.modules.governance.domain.jobs.cur_ingestion.resolve_aws_region_hint",
            return_value="us-east-1",
        ),
        patch("boto3.client", return_value=mock_s3),
        patch("app.modules.governance.domain.jobs.cur_ingestion.logger") as logger_mock,
    ):
        with pytest.raises(RuntimeError, match="s3 unavailable"):
            await job._find_latest_cur_key(conn, "cur-bucket")

    logger_mock.error.assert_called_once()
