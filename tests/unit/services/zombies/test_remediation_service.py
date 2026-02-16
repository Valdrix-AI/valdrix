import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.optimization.domain.remediation_service import RemediationService
from app.models.remediation import (
    RemediationRequest,
    RemediationStatus,
    RemediationAction,
)
from app.models.aws_connection import AWSConnection
from app.shared.core.exceptions import ResourceNotFoundError
# Import all models to prevent mapper errors during Mock usage


@pytest.fixture
def db_session():
    """Mock database session."""
    session = MagicMock(spec=AsyncSession)
    session.bind = MagicMock()
    session.bind.url = "sqlite://"
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.info = {}
    session.connection = AsyncMock(return_value=MagicMock())
    return session


@pytest.fixture
def remediation_service(db_session):
    return RemediationService(db_session)


@pytest.mark.asyncio
async def test_create_request_success(remediation_service, db_session):
    tenant_id = uuid4()
    user_id = uuid4()
    connection_id = uuid4()

    mock_conn = MagicMock(spec=AWSConnection)
    mock_conn.id = connection_id
    mock_conn.tenant_id = tenant_id

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_conn
    db_session.execute.return_value = mock_res

    request = await remediation_service.create_request(
        tenant_id=tenant_id,
        user_id=user_id,
        resource_id="vol-123",
        resource_type="ebs_volume",
        provider="aws",
        connection_id=connection_id,
        action=RemediationAction.DELETE_VOLUME,
        estimated_savings=50.0,
        create_backup=True,
    )

    assert request.resource_id == "vol-123"
    assert request.status == RemediationStatus.PENDING
    db_session.add.assert_called_once()


@pytest.mark.asyncio
async def test_create_request_unauthorized_connection(remediation_service, db_session):
    tenant_id = uuid4()
    connection_id = uuid4()

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db_session.execute.return_value = mock_res

    with pytest.raises(
        ValueError, match="Unauthorized: Connection does not belong to tenant"
    ):
        await remediation_service.create_request(
            tenant_id=tenant_id,
            user_id=uuid4(),
            resource_id="v-1",
            resource_type="type",
            action=RemediationAction.DELETE_VOLUME,
            estimated_savings=10.0,
            connection_id=connection_id,
        )


@pytest.mark.asyncio
async def test_list_pending_success(remediation_service, db_session):
    tenant_id = uuid4()
    req = RemediationRequest(
        id=uuid4(), tenant_id=tenant_id, status=RemediationStatus.PENDING
    )

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [req]
    db_session.execute.return_value = mock_res

    res = await remediation_service.list_pending(tenant_id)
    assert len(res) == 1
    assert res[0].id == req.id


@pytest.mark.asyncio
async def test_approve_flow(remediation_service, db_session):
    request_id = uuid4()
    tenant_id = uuid4()
    reviewer_id = uuid4()

    # 1. Not found
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db_session.execute.return_value = mock_res
    with pytest.raises(ResourceNotFoundError, match="not found"):
        await remediation_service.approve(request_id, tenant_id, reviewer_id)

    # 2. Not pending
    # Important: Use MagicMock(spec=RemediationRequest) AND ensure .action is mocked if needed later
    req = MagicMock(spec=RemediationRequest)
    req.id = request_id
    req.tenant_id = tenant_id
    # Use a real enum value so .value works
    req.status = RemediationStatus.COMPLETED
    mock_res.scalar_one_or_none.return_value = req
    with pytest.raises(ValueError, match="not pending"):
        await remediation_service.approve(request_id, tenant_id, reviewer_id)

    # 3. Success
    req.status = RemediationStatus.PENDING
    res = await remediation_service.approve(
        request_id, tenant_id, reviewer_id, notes="OK"
    )
    assert res.status == RemediationStatus.APPROVED
    assert res.reviewed_by_user_id == reviewer_id
    assert res.review_notes == "OK"


@pytest.mark.asyncio
async def test_reject_flow(remediation_service, db_session):
    request_id = uuid4()
    tenant_id = uuid4()
    reviewer_id = uuid4()

    # 1. Not found
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db_session.execute.return_value = mock_res
    with pytest.raises(ResourceNotFoundError, match="not found"):
        await remediation_service.reject(request_id, tenant_id, reviewer_id)

    # 2. Success
    req = MagicMock(spec=RemediationRequest)
    req.id = request_id
    req.tenant_id = tenant_id
    req.status = RemediationStatus.PENDING
    mock_res.scalar_one_or_none.return_value = req
    res = await remediation_service.reject(
        request_id, tenant_id, reviewer_id, notes="NO"
    )
    assert res.status == RemediationStatus.REJECTED
    assert res.reviewed_by_user_id == reviewer_id


@pytest.mark.asyncio
async def test_reject_requires_pending_status(remediation_service, db_session):
    request_id = uuid4()
    tenant_id = uuid4()
    reviewer_id = uuid4()

    req = MagicMock(spec=RemediationRequest)
    req.id = request_id
    req.tenant_id = tenant_id
    req.status = RemediationStatus.COMPLETED

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = req
    db_session.execute.return_value = mock_res

    with pytest.raises(ValueError, match="not pending"):
        await remediation_service.reject(request_id, tenant_id, reviewer_id)


@pytest.mark.asyncio
async def test_reject_requires_pending_status(remediation_service, db_session):
    request_id = uuid4()
    tenant_id = uuid4()
    reviewer_id = uuid4()

    req = MagicMock(spec=RemediationRequest)
    req.id = request_id
    req.tenant_id = tenant_id
    req.status = RemediationStatus.COMPLETED

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = req
    db_session.execute.return_value = mock_res

    with pytest.raises(ValueError, match="not pending"):
        await remediation_service.reject(request_id, tenant_id, reviewer_id)

@pytest.mark.asyncio
async def test_execute_errors(remediation_service, db_session):
    request_id = uuid4()
    tenant_id = uuid4()

    # 1. Not found
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db_session.execute.return_value = mock_res

    with pytest.raises(ResourceNotFoundError, match="not found"):
        await remediation_service.execute(request_id, tenant_id)

    # 2. Invalid status
    req = MagicMock(spec=RemediationRequest)
    req.id = request_id
    req.tenant_id = tenant_id
    req.estimated_monthly_savings = Decimal("50.0")
    req.provider = "aws"
    req.status = RemediationStatus.PENDING
    mock_res.scalar_one_or_none.return_value = req

    with patch(
        "app.modules.optimization.domain.remediation.SafetyGuardrailService"
    ) as mock_safety:
        mock_safety.return_value.check_all_guards = AsyncMock()
        res = await remediation_service.execute(request_id, tenant_id)
        assert res.status == RemediationStatus.FAILED
        assert "must be approved or scheduled" in (res.execution_error or "")


@pytest.mark.asyncio
async def test_execute_scheduled_successfully(remediation_service, db_session):
    request_id = uuid4()
    tenant_id = uuid4()
    reviewer_id = uuid4()
    req = MagicMock(spec=RemediationRequest)
    req.id = request_id
    req.tenant_id = tenant_id
    req.status = RemediationStatus.APPROVED
    req.resource_id = "v-1"
    req.action = RemediationAction.DELETE_VOLUME
    req.resource_type = "vol"
    req.estimated_monthly_savings = Decimal("50.0")
    req.provider = "aws"
    req.reviewed_by_user_id = reviewer_id
    req.create_backup = False

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = req
    db_session.execute.return_value = mock_res

    with (
        patch(
            "app.modules.optimization.domain.remediation.AuditLogger.log",
            return_value=AsyncMock(),
        ) as mock_audit,
        patch(
            "app.modules.governance.domain.jobs.processor.enqueue_job",
            return_value=AsyncMock(),
        ) as mock_job,
        patch(
            "app.modules.optimization.domain.remediation.SafetyGuardrailService"
        ) as mock_safety,
    ):
        mock_safety.return_value.check_all_guards = AsyncMock()

        res = await remediation_service.execute(
            request_id, tenant_id, bypass_grace_period=False
        )
        assert res.status == RemediationStatus.SCHEDULED
        mock_job.assert_called_once()
        assert mock_audit.called


@pytest.mark.asyncio
async def test_execute_grace_period_logic(remediation_service, db_session):
    request_id = uuid4()
    tenant_id = uuid4()

    # 1. Deferred
    future_time = datetime.now(timezone.utc) + timedelta(hours=10)
    req = MagicMock(spec=RemediationRequest)
    req.id = request_id
    req.tenant_id = tenant_id
    req.status = RemediationStatus.SCHEDULED
    req.scheduled_execution_at = future_time
    req.estimated_monthly_savings = Decimal("50.0")
    req.provider = "aws"  # Needed for service lookup

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = req
    db_session.execute.return_value = mock_res

    with patch(
        "app.modules.optimization.domain.remediation.SafetyGuardrailService"
    ) as mock_safety:
        mock_safety.return_value.check_all_guards = AsyncMock()
        res = await remediation_service.execute(request_id, tenant_id)
        assert res.status == RemediationStatus.SCHEDULED

    # 2. Passed
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)
    # Reset status to APPROVED/SCHEDULED so it proceeds
    req.status = RemediationStatus.SCHEDULED
    req.scheduled_execution_at = past_time
    req.action = RemediationAction.DELETE_VOLUME
    req.create_backup = False
    req.resource_id = "v-1"
    req.resource_type = "vol"
    req.reviewed_by_user_id = uuid4()

    with (
        patch.object(remediation_service, "_execute_action", return_value=AsyncMock()),
        patch(
            "app.modules.optimization.domain.remediation.AuditLogger.log",
            return_value=AsyncMock(),
        ),
        patch(
            "app.modules.optimization.domain.remediation.SafetyGuardrailService"
        ) as mock_safety,
    ):
        mock_safety.return_value.check_all_guards = AsyncMock()
        res = await remediation_service.execute(request_id, tenant_id)
        assert res.status == RemediationStatus.COMPLETED


@pytest.mark.asyncio
async def test_execute_backup_routing(remediation_service, db_session):
    request_id = uuid4()
    tenant_id = uuid4()
    req = MagicMock(spec=RemediationRequest)
    req.id = request_id
    req.tenant_id = tenant_id
    # Reset status for each check
    req.status = RemediationStatus.APPROVED
    req.create_backup = True
    req.backup_retention_days = 7
    req.reviewed_by_user_id = uuid4()
    req.estimated_monthly_savings = Decimal("50.0")
    req.provider = "aws"
    req.resource_id = "r-1"
    req.resource_type = "type"

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = req
    db_session.execute.return_value = mock_res

    with (
        patch.object(remediation_service, "_execute_action", return_value=AsyncMock()),
        patch(
            "app.modules.optimization.domain.remediation.AuditLogger.log",
            return_value=AsyncMock(),
        ),
        patch(
            "app.modules.optimization.domain.remediation.SafetyGuardrailService"
        ) as mock_safety,
    ):
        mock_safety.return_value.check_all_guards = AsyncMock()

        # 1. RDS Backup
        req.status = RemediationStatus.APPROVED
        req.action = RemediationAction.DELETE_RDS_INSTANCE
        with patch.object(
            remediation_service, "_create_rds_backup", return_value="rds-snap"
        ) as mock_rds_b:
            await remediation_service.execute(
                request_id, tenant_id, bypass_grace_period=True
            )
            mock_rds_b.assert_called()

        # 2. Redshift Backup
        req.status = (
            RemediationStatus.APPROVED
        )  # Crucial: reset status because it targets the SAME mock object
        req.action = RemediationAction.DELETE_REDSHIFT_CLUSTER
        with patch.object(
            remediation_service, "_create_redshift_backup", return_value="rs-snap"
        ) as mock_rs_b:
            await remediation_service.execute(
                request_id, tenant_id, bypass_grace_period=True
            )
            mock_rs_b.assert_called()


@pytest.mark.asyncio
async def test_execute_backup_failure_aborts(remediation_service, db_session):
    request_id = uuid4()
    tenant_id = uuid4()
    req = MagicMock(spec=RemediationRequest)
    req.id = request_id
    req.tenant_id = tenant_id
    req.status = RemediationStatus.APPROVED
    req.resource_id = "v-1"
    req.resource_type = "vol"
    req.action = RemediationAction.DELETE_VOLUME
    req.create_backup = True
    req.reviewed_by_user_id = uuid4()

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = req
    db_session.execute.return_value = mock_res

    with (
        patch.object(
            remediation_service,
            "_create_volume_backup",
            side_effect=Exception("AWS Error"),
        ),
        patch(
            "app.modules.optimization.domain.remediation.AuditLogger.log",
            return_value=AsyncMock(),
        ),
        patch(
            "app.modules.optimization.domain.remediation.SafetyGuardrailService"
        ) as mock_safety,
    ):  # Patch Safety Service
        mock_safety.return_value.check_all_guards = AsyncMock()

        res = await remediation_service.execute(
            request_id, tenant_id, bypass_grace_period=True
        )
        assert res.status == RemediationStatus.FAILED
        assert "BACKUP_FAILED" in res.execution_error


@pytest.mark.asyncio
async def test_get_client_credential_mapping(remediation_service):
    # Test with CamelCase credentials
    remediation_service.credentials = {
        "AccessKeyId": "AK",
        "SecretAccessKey": "SK",
        "SessionToken": "ST",
    }
    mock_session = MagicMock()
    remediation_service.session = mock_session
    with patch(
        "app.modules.optimization.domain.remediation.get_settings"
    ) as mock_settings:
        mock_settings.return_value.AWS_ENDPOINT_URL = "http://localhost"
        await remediation_service._get_client("ec2")
        args, kwargs = mock_session.client.call_args
        assert kwargs["aws_access_key_id"] == "AK"
        assert kwargs["endpoint_url"] == "http://localhost"


@pytest.mark.asyncio
async def test_backup_helpers_logic(remediation_service):
    mock_client = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_client

    with patch.object(remediation_service, "_get_client", return_value=mock_cm):
        # EBS
        mock_client.create_snapshot.return_value = {"SnapshotId": "snap-1"}
        await remediation_service._create_volume_backup("vol-1", 7)
        mock_client.create_snapshot.assert_called()

        # RDS (covers lines 484-485 log)
        await remediation_service._create_rds_backup("rds-1", 7)
        mock_client.create_db_snapshot.assert_called()

        # Redshift (covers lines 509-510 log)
        await remediation_service._create_redshift_backup("rs-1", 7)
        mock_client.create_cluster_snapshot.assert_called()


@pytest.mark.asyncio
async def test_aws_action_dispatcher_comprehensive(remediation_service):
    mock_client = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_client

    with patch.object(remediation_service, "_get_client", return_value=mock_cm):
        # Coverage for all branches
        actions = [
            (RemediationAction.DELETE_VOLUME, "delete_volume", {"VolumeId": "r-1"}),
            (
                RemediationAction.DELETE_SNAPSHOT,
                "delete_snapshot",
                {"SnapshotId": "r-1"},
            ),
            (
                RemediationAction.RELEASE_ELASTIC_IP,
                "release_address",
                {"AllocationId": "r-1"},
            ),
            (
                RemediationAction.STOP_INSTANCE,
                "stop_instances",
                {"InstanceIds": ["r-1"]},
            ),
            (
                RemediationAction.TERMINATE_INSTANCE,
                "terminate_instances",
                {"InstanceIds": ["r-1"]},
            ),
            (RemediationAction.DELETE_S3_BUCKET, "delete_bucket", {"Bucket": "r-1"}),
            (
                RemediationAction.DELETE_REDSHIFT_CLUSTER,
                "delete_cluster",
                {"ClusterIdentifier": "r-1", "SkipFinalClusterSnapshot": True},
            ),
            (
                RemediationAction.DELETE_LOAD_BALANCER,
                "delete_load_balancer",
                {"LoadBalancerArn": "r-1"},
            ),
            (
                RemediationAction.STOP_RDS_INSTANCE,
                "stop_db_instance",
                {"DBInstanceIdentifier": "r-1"},
            ),
            (
                RemediationAction.DELETE_RDS_INSTANCE,
                "delete_db_instance",
                {"DBInstanceIdentifier": "r-1", "SkipFinalSnapshot": True},
            ),
            (
                RemediationAction.DELETE_NAT_GATEWAY,
                "delete_nat_gateway",
                {"NatGatewayId": "r-1"},
            ),
        ]

        for action, method, expected_kwargs in actions:
            await remediation_service._execute_action("r-1", action)
            getattr(mock_client, method).assert_called()

        # SageMaker coverage
        await remediation_service._execute_action(
            "sm-1", RemediationAction.DELETE_SAGEMAKER_ENDPOINT
        )
        mock_client.delete_endpoint.assert_called_with(EndpointName="sm-1")

        # ECR coverage
        await remediation_service._execute_action(
            "repo@digest", RemediationAction.DELETE_ECR_IMAGE
        )
        mock_client.batch_delete_image.assert_called()


@pytest.mark.asyncio
async def test_enforce_hard_limit_success(remediation_service, db_session):
    tenant_id = uuid4()
    req = MagicMock(spec=RemediationRequest)
    req.id = uuid4()
    req.tenant_id = tenant_id
    req.action = RemediationAction.STOP_INSTANCE
    req.status = RemediationStatus.PENDING
    req.confidence_score = Decimal("0.99")
    req.estimated_monthly_savings = Decimal("10.0")

    with patch(
        "app.shared.llm.usage_tracker.UsageTracker.check_budget",
        return_value="hard_limit",
    ):
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [req]
        db_session.execute.return_value = mock_res

        with patch.object(
            remediation_service, "execute", return_value=AsyncMock()
        ) as mock_execute:
            ids = await remediation_service.enforce_hard_limit(tenant_id)
            assert len(ids) == 1
            assert req.status == RemediationStatus.APPROVED
            assert req.reviewed_by_user_id == UUID(
                "00000000-0000-0000-0000-000000000000"
            )
            mock_execute.assert_called_once_with(
                req.id, tenant_id, bypass_grace_period=False
            )
