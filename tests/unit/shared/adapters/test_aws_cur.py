from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from botocore.exceptions import ClientError

from app.schemas.costs import CloudUsageSummary, CostRecord
from app.shared.adapters.aws_cur import AWSCURAdapter
from app.shared.core.credentials import AWSCredentials
from app.shared.core.exceptions import ConfigurationError


def _async_cm(value: object) -> MagicMock:
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=value)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


class _AsyncBody:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    async def __aenter__(self) -> "_AsyncBody":
        return self

    async def __aexit__(self, _exc_type, _exc, _tb) -> None:
        return None

    async def read(self, _size: int) -> bytes:
        return self._chunks.pop(0) if self._chunks else b""


class _ReadBody:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def read(self) -> bytes:
        return self._payload


class _Paginator:
    def __init__(self, pages_by_prefix: dict[str, list[dict[str, object]]]) -> None:
        self._pages_by_prefix = pages_by_prefix

    def paginate(self, *, Bucket: str, Prefix: str):  # noqa: N803
        _ = Bucket
        pages = self._pages_by_prefix.get(Prefix, [])

        async def _aiter():
            for page in pages:
                yield page

        return _aiter()


@pytest.fixture
def mock_creds() -> AWSCredentials:
    return AWSCredentials(
        account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/ValdrixRole",
        external_id="ext-id",
        region="us-east-1",
    )


def _summary_with_records(records: list[CostRecord], total: Decimal) -> CloudUsageSummary:
    return CloudUsageSummary(
        tenant_id="tenant",
        provider="aws",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 2),
        total_cost=total,
        records=records,
        by_service={"svc": total},
        by_region={"us-east-1": total},
        by_tag={"team": {"core": total}},
    )


@pytest.mark.asyncio
class TestAWSCURAdapter:
    async def test_constructor_resolves_global_region_hint(self) -> None:
        creds = AWSCredentials(
            account_id="123456789012",
            role_arn="arn:aws:iam::123456789012:role/ValdrixRole",
            external_id="ext-id",
            region="global",
        )

        with patch(
            "app.shared.adapters.aws_utils.get_settings",
            return_value=SimpleNamespace(
                AWS_SUPPORTED_REGIONS=["eu-west-1"],
                AWS_DEFAULT_REGION="eu-west-1",
            ),
        ):
            adapter = AWSCURAdapter(creds)

        assert adapter._resolved_region == "eu-west-1"
        assert adapter.bucket_name == "valdrix-cur-123456789012-eu-west-1"

    async def test_verify_connection_success(self, mock_creds: AWSCredentials) -> None:
        mock_s3 = AsyncMock()
        mock_session = MagicMock()
        mock_session.client.return_value = _async_cm(mock_s3)

        with patch.object(
            AWSCURAdapter,
            "_get_credentials",
            new=AsyncMock(
                return_value={
                    "AccessKeyId": "test",
                    "SecretAccessKey": "test",
                    "SessionToken": "test",
                }
            ),
        ):
            adapter = AWSCURAdapter(mock_creds)
            adapter.session = mock_session

            success = await adapter.verify_connection()
            assert success is True
            mock_s3.head_bucket.assert_awaited_with(Bucket=adapter.bucket_name)

    async def test_verify_connection_failure_returns_false(
        self, mock_creds: AWSCredentials
    ) -> None:
        mock_s3 = AsyncMock()
        mock_s3.head_bucket.side_effect = RuntimeError("access denied")
        mock_session = MagicMock()
        mock_session.client.return_value = _async_cm(mock_s3)

        with patch.object(
            AWSCURAdapter,
            "_get_credentials",
            new=AsyncMock(
                return_value={
                    "AccessKeyId": "test",
                    "SecretAccessKey": "test",
                    "SessionToken": "test",
                }
            ),
        ), patch("app.shared.adapters.aws_cur.logger.error") as mock_error:
            adapter = AWSCURAdapter(mock_creds)
            adapter.session = mock_session
            success = await adapter.verify_connection()

        assert success is False
        mock_error.assert_called_once()

    async def test_setup_cur_automation_creates_bucket_and_report(
        self, mock_creds: AWSCredentials
    ) -> None:
        mock_s3 = AsyncMock()
        mock_cur = AsyncMock()
        mock_s3.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadBucket",
        )

        mock_session = MagicMock()
        mock_session.client.side_effect = [_async_cm(mock_s3), _async_cm(mock_cur)]

        with patch.object(
            AWSCURAdapter,
            "_get_credentials",
            new=AsyncMock(
                return_value={
                    "AccessKeyId": "AKIA...",
                    "SecretAccessKey": "SECRET",
                    "SessionToken": "TOKEN",
                }
            ),
        ):
            adapter = AWSCURAdapter(mock_creds)
            adapter.session = mock_session

            result = await adapter.setup_cur_automation()

        assert result["status"] == "success"
        assert result["bucket_name"] == adapter.bucket_name
        mock_s3.create_bucket.assert_awaited_once_with(Bucket=adapter.bucket_name)
        mock_s3.put_bucket_policy.assert_awaited_once()
        mock_cur.put_report_definition.assert_awaited_once()
        call_args = mock_cur.put_report_definition.call_args[1]
        assert (
            call_args["ReportDefinition"]["ReportName"]
            == f"valdrix-cur-{mock_creds.account_id}"
        )

    async def test_setup_cur_automation_non_us_east_adds_location_constraint(
        self,
    ) -> None:
        creds = AWSCredentials(
            account_id="123456789012",
            role_arn="arn:aws:iam::123456789012:role/ValdrixRole",
            external_id="ext-id",
            region="eu-west-1",
        )
        mock_s3 = AsyncMock()
        mock_cur = AsyncMock()
        mock_s3.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadBucket",
        )
        mock_session = MagicMock()
        mock_session.client.side_effect = [_async_cm(mock_s3), _async_cm(mock_cur)]

        with patch.object(
            AWSCURAdapter,
            "_get_credentials",
            new=AsyncMock(
                return_value={
                    "AccessKeyId": "AKIA...",
                    "SecretAccessKey": "SECRET",
                    "SessionToken": "TOKEN",
                }
            ),
        ):
            adapter = AWSCURAdapter(creds)
            adapter.session = mock_session
            result = await adapter.setup_cur_automation()

        assert result["status"] == "success"
        mock_s3.create_bucket.assert_awaited_once_with(
            Bucket=adapter.bucket_name,
            CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
        )

    async def test_setup_cur_automation_returns_error_when_s3_step_fails(
        self, mock_creds: AWSCredentials
    ) -> None:
        mock_s3 = AsyncMock()
        mock_s3.put_bucket_policy.side_effect = RuntimeError("policy failed")
        mock_session = MagicMock()
        mock_session.client.return_value = _async_cm(mock_s3)

        with patch.object(
            AWSCURAdapter,
            "_get_credentials",
            new=AsyncMock(
                return_value={
                    "AccessKeyId": "AKIA...",
                    "SecretAccessKey": "SECRET",
                    "SessionToken": "TOKEN",
                }
            ),
        ):
            adapter = AWSCURAdapter(mock_creds)
            adapter.session = mock_session
            result = await adapter.setup_cur_automation()

        assert result["status"] == "error"
        assert "S3 setup failed" in result["message"]

    async def test_setup_cur_automation_returns_error_when_cur_step_fails(
        self, mock_creds: AWSCredentials
    ) -> None:
        mock_s3 = AsyncMock()
        mock_cur = AsyncMock()
        mock_cur.put_report_definition.side_effect = RuntimeError("cur failed")
        mock_session = MagicMock()
        mock_session.client.side_effect = [_async_cm(mock_s3), _async_cm(mock_cur)]

        with patch.object(
            AWSCURAdapter,
            "_get_credentials",
            new=AsyncMock(
                return_value={
                    "AccessKeyId": "AKIA...",
                    "SecretAccessKey": "SECRET",
                    "SessionToken": "TOKEN",
                }
            ),
        ):
            adapter = AWSCURAdapter(mock_creds)
            adapter.session = mock_session
            result = await adapter.setup_cur_automation()

        assert result["status"] == "error"
        assert "CUR setup failed" in result["message"]

    async def test_get_cost_and_usage_converts_dates(self, mock_creds: AWSCredentials) -> None:
        adapter = AWSCURAdapter(mock_creds)
        record = CostRecord(
            date=datetime(2026, 2, 1, tzinfo=timezone.utc),
            amount=Decimal("4.5"),
            amount_raw=Decimal("4.5"),
            currency="USD",
            service="AmazonEC2",
            region="us-east-1",
            usage_type="BoxUsage",
            tags={},
        )
        summary = _summary_with_records([record], Decimal("4.5"))

        with patch.object(
            adapter,
            "get_daily_costs",
            new=AsyncMock(return_value=summary),
        ) as get_daily_costs:
            rows = await adapter.get_cost_and_usage(
                datetime(2026, 2, 1, tzinfo=timezone.utc),
                datetime(2026, 2, 2, tzinfo=timezone.utc),
            )

        get_daily_costs.assert_awaited_once_with(date(2026, 2, 1), date(2026, 2, 2))
        assert rows[0]["service"] == "AmazonEC2"
        assert rows[0]["amount"] == Decimal("4.5")

    async def test_get_daily_costs_empty_and_error_paths(
        self, mock_creds: AWSCredentials
    ) -> None:
        adapter = AWSCURAdapter(mock_creds)
        with patch.object(
            adapter,
            "_list_cur_files_in_range",
            new=AsyncMock(return_value=[]),
        ):
            summary = await adapter.get_daily_costs(date(2026, 2, 1), date(2026, 2, 2))
        assert summary.total_cost == 0
        assert summary.records == []

        with patch.object(
            adapter,
            "_list_cur_files_in_range",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ), pytest.raises(RuntimeError):
            await adapter.get_daily_costs(date(2026, 2, 1), date(2026, 2, 2))

    async def test_stream_cost_and_usage_yields_flat_records(
        self, mock_creds: AWSCredentials
    ) -> None:
        adapter = AWSCURAdapter(mock_creds)
        record = CostRecord(
            date=datetime(2026, 2, 1, tzinfo=timezone.utc),
            amount=Decimal("1.25"),
            amount_raw=Decimal("1.25"),
            currency="USD",
            service="AmazonS3",
            region="us-east-1",
            usage_type="Storage",
            tags={"team": "platform"},
        )
        summary = _summary_with_records([record], Decimal("1.25"))

        with patch.object(
            adapter,
            "_list_cur_files_in_range",
            new=AsyncMock(return_value=["a.parquet", "b.parquet"]),
        ), patch.object(
            adapter,
            "_ingest_single_file",
            new=AsyncMock(return_value=summary),
        ):
            results = [
                item
                async for item in adapter.stream_cost_and_usage(
                    datetime(2026, 2, 1, tzinfo=timezone.utc),
                    datetime(2026, 2, 2, tzinfo=timezone.utc),
                )
            ]

        assert len(results) == 2
        assert results[0]["source_adapter"] == "cur_data_export"
        assert results[0]["cost_usd"] == Decimal("1.25")

    async def test_list_cur_files_prefers_latest_manifest_and_deduplicates(
        self, mock_creds: AWSCredentials
    ) -> None:
        jan_prefix = "cur/2026/01/"
        feb_prefix = "cur/2026/02/"
        paginator = _Paginator(
            {
                jan_prefix: [
                    {
                        "Contents": [
                            {
                                "Key": f"{jan_prefix}older-manifest.json",
                                "LastModified": datetime(
                                    2026, 1, 10, tzinfo=timezone.utc
                                ),
                            },
                            {
                                "Key": f"{jan_prefix}latest-manifest.json",
                                "LastModified": datetime(
                                    2026, 1, 20, tzinfo=timezone.utc
                                ),
                            },
                            {"Key": f"{jan_prefix}direct.parquet"},
                        ]
                    }
                ],
                feb_prefix: [{"Contents": [{"Key": f"{feb_prefix}feb.parquet"}]}],
            }
        )
        manifest_payload = {
            "reportKeys": [
                "cur/2026/01/a.parquet",
                "cur/2026/01/a.parquet",
                "cur/2026/01/b.parquet",
            ]
        }
        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = paginator
        mock_s3.get_object = AsyncMock(
            return_value={"Body": _ReadBody(json.dumps(manifest_payload).encode())}
        )
        mock_session = MagicMock()
        mock_session.client.return_value = _async_cm(mock_s3)

        with patch.object(
            AWSCURAdapter,
            "_get_credentials",
            new=AsyncMock(
                return_value={
                    "AccessKeyId": "AKIA...",
                    "SecretAccessKey": "SECRET",
                    "SessionToken": "TOKEN",
                }
            ),
        ):
            adapter = AWSCURAdapter(mock_creds)
            adapter.session = mock_session
            keys = await adapter._list_cur_files_in_range(
                date(2026, 1, 1), date(2026, 2, 5)
            )

        assert keys == [
            "cur/2026/01/a.parquet",
            "cur/2026/01/b.parquet",
            "cur/2026/02/feb.parquet",
        ]
        mock_s3.get_object.assert_awaited_once_with(
            Bucket=adapter.bucket_name,
            Key=f"{jan_prefix}latest-manifest.json",
        )

    async def test_list_cur_files_manifest_parse_failure_falls_back_to_listing(
        self, mock_creds: AWSCredentials
    ) -> None:
        month_prefix = "cur/2026/03/"
        paginator = _Paginator(
            {
                month_prefix: [
                    {
                        "Contents": [
                            {
                                "Key": f"{month_prefix}manifest.json",
                                "LastModified": datetime(
                                    2026, 3, 10, tzinfo=timezone.utc
                                ),
                            },
                            {"Key": f"{month_prefix}part-1.parquet"},
                            {"Key": f"{month_prefix}part-2.parquet"},
                        ]
                    }
                ]
            }
        )
        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = paginator
        mock_s3.get_object = AsyncMock(side_effect=RuntimeError("manifest read failed"))
        mock_session = MagicMock()
        mock_session.client.return_value = _async_cm(mock_s3)

        with patch.object(
            AWSCURAdapter,
            "_get_credentials",
            new=AsyncMock(
                return_value={
                    "AccessKeyId": "AKIA...",
                    "SecretAccessKey": "SECRET",
                    "SessionToken": "TOKEN",
                }
            ),
        ):
            adapter = AWSCURAdapter(mock_creds)
            adapter.session = mock_session
            keys = await adapter._list_cur_files_in_range(
                date(2026, 3, 1), date(2026, 3, 1)
            )

        assert keys == [f"{month_prefix}part-1.parquet", f"{month_prefix}part-2.parquet"]

    async def test_process_files_in_range_merges_and_truncates(
        self, mock_creds: AWSCredentials
    ) -> None:
        adapter = AWSCURAdapter(mock_creds)
        record = CostRecord(
            date=datetime(2026, 2, 1, tzinfo=timezone.utc),
            amount=Decimal("1"),
            amount_raw=Decimal("1"),
            currency="USD",
            service="svc",
            region="us-east-1",
            usage_type="x",
            tags={"team": "core"},
        )
        large_records = [record] * 10001
        small_record = CostRecord(
            date=datetime(2026, 2, 2, tzinfo=timezone.utc),
            amount=Decimal("2"),
            amount_raw=Decimal("2"),
            currency="USD",
            service="svc",
            region="us-west-2",
            usage_type="y",
            tags={"team": "edge"},
        )
        file_a = CloudUsageSummary(
            tenant_id="t",
            provider="aws",
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 1),
            total_cost=Decimal("10001"),
            records=large_records,
            by_service={"svc": Decimal("10001")},
            by_region={"us-east-1": Decimal("10001")},
            by_tag={"team": {"core": Decimal("10001")}},
        )
        file_b = CloudUsageSummary(
            tenant_id="t",
            provider="aws",
            start_date=date(2026, 2, 2),
            end_date=date(2026, 2, 2),
            total_cost=Decimal("2"),
            records=[small_record],
            by_service={"svc": Decimal("2")},
            by_region={"us-west-2": Decimal("2")},
            by_tag={"team": {"edge": Decimal("2")}},
        )

        with patch.object(
            adapter,
            "_ingest_single_file",
            new=AsyncMock(side_effect=[file_a, file_b]),
        ), patch("app.shared.adapters.aws_cur.logger.warning") as mock_warning:
            summary = await adapter._process_files_in_range(
                ["a.parquet", "b.parquet"],
                date(2026, 2, 1),
                date(2026, 2, 2),
            )

        assert summary.total_cost == Decimal("10003")
        assert len(summary.records) == 10001
        assert summary.by_region["us-east-1"] == Decimal("10001")
        assert summary.by_region["us-west-2"] == Decimal("2")
        assert summary.by_tag["team"]["core"] == Decimal("10001")
        assert summary.by_tag["team"]["edge"] == Decimal("2")
        mock_warning.assert_any_call(
            "cur_file_summary_records_truncated",
            file_key="a.parquet",
            cap=10000,
            truncated_records=1,
        )
        mock_warning.assert_any_call(
            "cur_master_summary_records_truncated",
            cap_per_file=10000,
            truncated_records_total=1,
            files_processed=2,
        )

    async def test_ingest_single_file_downloads_and_cleans_up(
        self, mock_creds: AWSCredentials
    ) -> None:
        adapter = AWSCURAdapter(mock_creds)
        mock_s3 = AsyncMock()
        mock_s3.get_object = AsyncMock(
            return_value={"Body": _AsyncBody([b"abc", b"def", b""])}
        )
        adapter.session = MagicMock()
        adapter.session.client.return_value = _async_cm(mock_s3)
        expected = adapter._empty_summary()

        with patch.object(
            adapter,
            "_get_credentials",
            new=AsyncMock(
                return_value={
                    "AccessKeyId": "AKIA...",
                    "SecretAccessKey": "SECRET",
                    "SessionToken": "TOKEN",
                }
            ),
        ), patch.object(
            adapter,
            "_process_parquet_streamingly",
            return_value=expected,
        ) as process_mock, patch(
            "app.shared.adapters.aws_cur.os.path.exists",
            return_value=True,
        ), patch(
            "app.shared.adapters.aws_cur.os.remove"
        ) as remove_mock:
            summary = await adapter._ingest_single_file(
                "cur/file.parquet",
                date(2026, 2, 1),
                date(2026, 2, 2),
            )

        assert summary is expected
        process_mock.assert_called_once()
        remove_mock.assert_called_once()

    async def test_process_parquet_streamingly_logs_when_record_cap_exceeded(
        self, mock_creds: AWSCredentials
    ) -> None:
        adapter = AWSCURAdapter(mock_creds)
        adapter._SUMMARY_RECORD_CAP = 2

        df = pd.DataFrame(
            {
                "lineItem/UsageStartDate": [
                    "2026-02-01T00:00:00Z",
                    "2026-02-01T01:00:00Z",
                    "2026-02-01T02:00:00Z",
                ],
                "lineItem/UnblendedCost": ["1.0", "2.0", "3.0"],
                "lineItem/CurrencyCode": ["USD", "USD", "USD"],
                "lineItem/ProductCode": ["AmazonEC2", "AmazonEC2", "AmazonEC2"],
                "product/region": ["us-east-1", "us-east-1", "us-east-1"],
                "lineItem/UsageType": ["BoxUsage", "BoxUsage", "BoxUsage"],
            }
        )

        class _FakeTable:
            def to_pandas(self):
                return df

        class _FakeParquetFile:
            num_row_groups = 1

            def read_row_group(self, idx: int):
                assert idx == 0
                return _FakeTable()

        with patch(
            "app.shared.adapters.aws_cur.pq.ParquetFile",
            return_value=_FakeParquetFile(),
        ), patch("app.shared.adapters.aws_cur.logger.warning") as mock_warning:
            summary = adapter._process_parquet_streamingly("/tmp/cur.parquet")

        assert len(summary.records) == 2
        assert summary.total_cost == 6
        mock_warning.assert_any_call(
            "cur_summary_record_cap_reached",
            cap=2,
            dropped_records=1,
            retained_records=2,
            start=None,
            end=None,
        )

    async def test_process_parquet_streamingly_handles_read_and_row_parse_errors(
        self, mock_creds: AWSCredentials
    ) -> None:
        adapter = AWSCURAdapter(mock_creds)
        good_record = CostRecord(
            date=datetime(2026, 2, 1, tzinfo=timezone.utc),
            amount=Decimal("5"),
            amount_raw=Decimal("5"),
            currency="USD",
            service="AmazonS3",
            region="us-east-1",
            usage_type="Storage",
            tags={"team": "core"},
        )
        df = pd.DataFrame(
            {
                "lineItem/UsageStartDate": [
                    "2026-02-01T00:00:00Z",
                    "2026-02-01T01:00:00Z",
                ],
                "lineItem/UnblendedCost": ["5.0", "oops"],
            }
        )

        class _FakeTable:
            def __init__(self, frame: pd.DataFrame) -> None:
                self._frame = frame

            def to_pandas(self) -> pd.DataFrame:
                return self._frame

        class _FakeParquetFile:
            num_row_groups = 2

            def read_row_group(self, idx: int):
                if idx == 0:
                    raise RuntimeError("broken row-group")
                return _FakeTable(df)

        with patch(
            "app.shared.adapters.aws_cur.pq.ParquetFile",
            return_value=_FakeParquetFile(),
        ), patch.object(
            adapter,
            "_parse_row",
            side_effect=[good_record, ValueError("bad row")],
        ), patch("app.shared.adapters.aws_cur.logger.warning") as mock_warning:
            summary = adapter._process_parquet_streamingly("/tmp/cur.parquet")

        assert summary.total_cost == Decimal("5")
        assert len(summary.records) == 1
        assert summary.by_service["AmazonS3"] == Decimal("5")
        assert summary.by_tag["team"]["core"] == Decimal("5")
        mock_warning.assert_any_call(
            "cur_row_group_read_failed",
            error="broken row-group",
            row_group=0,
        )

    async def test_process_parquet_streamingly_skips_chunks_without_required_columns(
        self, mock_creds: AWSCredentials
    ) -> None:
        adapter = AWSCURAdapter(mock_creds)
        df = pd.DataFrame({"lineItem/UsageStartDate": ["2026-02-01T00:00:00Z"]})

        class _FakeTable:
            def to_pandas(self):
                return df

        class _FakeParquetFile:
            num_row_groups = 1

            def read_row_group(self, _idx: int):
                return _FakeTable()

        with patch(
            "app.shared.adapters.aws_cur.pq.ParquetFile",
            return_value=_FakeParquetFile(),
        ):
            summary = adapter._process_parquet_streamingly(
                "/tmp/cur.parquet",
                start_date=date(2026, 2, 1),
                end_date=date(2026, 2, 2),
            )

        assert summary.total_cost == 0
        assert summary.records == []

    async def test_parse_row_handles_invalid_values(self, mock_creds: AWSCredentials) -> None:
        adapter = AWSCURAdapter(mock_creds)
        row = pd.Series(
            {
                "lineItem/UsageStartDate": "2026-02-01T12:00:00",
                "lineItem/UnblendedCost": "not-a-number",
                "lineItem/CurrencyCode": "",
                "lineItem/ProductCode": "",
                "product/region": "",
                "lineItem/UsageType": "",
            }
        )
        col_map = {
            "date": "lineItem/UsageStartDate",
            "cost": "lineItem/UnblendedCost",
            "currency": "lineItem/CurrencyCode",
            "service": "lineItem/ProductCode",
            "region": "product/region",
            "usage_type": "lineItem/UsageType",
        }

        parsed = adapter._parse_row(row, col_map)

        assert parsed.amount == Decimal("0")
        assert parsed.currency == "USD"
        assert parsed.service == "Unknown"
        assert parsed.region == "Global"
        assert parsed.usage_type == "Unknown"
        assert parsed.date.tzinfo == timezone.utc

    async def test_parse_row_raises_for_missing_or_invalid_date(
        self, mock_creds: AWSCredentials
    ) -> None:
        adapter = AWSCURAdapter(mock_creds)
        row_missing = pd.Series({"lineItem/UnblendedCost": "1.0"})
        with pytest.raises(ConfigurationError, match="Missing date column mapping"):
            adapter._parse_row(
                row_missing,
                {
                    "date": None,
                    "cost": "lineItem/UnblendedCost",
                },
            )

        row_invalid = pd.Series(
            {
                "lineItem/UsageStartDate": pd.NaT,
                "lineItem/UnblendedCost": "1.0",
            }
        )
        with pytest.raises(ConfigurationError, match="Invalid usage start date"):
            adapter._parse_row(
                row_invalid,
                {
                    "date": "lineItem/UsageStartDate",
                    "cost": "lineItem/UnblendedCost",
                },
            )

    async def test_extract_tags_supports_both_column_prefixes(
        self, mock_creds: AWSCredentials
    ) -> None:
        adapter = AWSCURAdapter(mock_creds)
        row = pd.Series(
            {
                "resourceTags/user:team": "core",
                "resource_tags_user_env": "prod",
                "resourceTags/user:empty": "",
                "other": "value",
            }
        )

        tags = adapter._extract_tags(row)

        assert tags == {"team": "core", "env": "prod"}

    async def test_get_credentials_uses_multitenant_adapter(
        self, mock_creds: AWSCredentials
    ) -> None:
        adapter = AWSCURAdapter(mock_creds)
        fake_mt = MagicMock()
        fake_mt.get_credentials = AsyncMock(
            return_value={
                "AccessKeyId": "AKIA...",
                "SecretAccessKey": "SECRET",
                "SessionToken": "TOKEN",
            }
        )
        with patch(
            "app.shared.adapters.aws_multitenant.MultiTenantAWSAdapter",
            return_value=fake_mt,
        ):
            creds = await adapter._get_credentials()

        assert creds["AccessKeyId"] == "AKIA..."

    async def test_empty_summary_and_noop_resource_methods(
        self, mock_creds: AWSCredentials
    ) -> None:
        adapter = AWSCURAdapter(mock_creds)
        summary = adapter._empty_summary()

        assert summary.provider == "aws"
        assert summary.total_cost == 0
        assert await adapter.discover_resources("ec2") == []
        assert await adapter.get_resource_usage("ec2") == []
