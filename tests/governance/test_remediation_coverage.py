
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from app.modules.optimization.domain.remediation_service import RemediationService
from app.models.remediation import RemediationAction
from botocore.exceptions import ClientError

@pytest_asyncio.fixture
async def remediation_service(db):
    return RemediationService(db)

@pytest.mark.asyncio
async def test_execute_action_ec2_variations(remediation_service):
    """Test various EC2 remediation actions."""
    resource_id = "i-12345678"
    
    with patch.object(remediation_service, "_get_client", new_callable=AsyncMock) as mock_get_client:
        mock_ec2 = AsyncMock()
        mock_get_client.return_value.__aenter__.return_value = mock_ec2
        
        # Test STOP_INSTANCE
        await remediation_service._execute_action(resource_id, RemediationAction.STOP_INSTANCE)
        mock_ec2.stop_instances.assert_called_with(InstanceIds=[resource_id])
        
        # Test TERMINATE_INSTANCE
        await remediation_service._execute_action(resource_id, RemediationAction.TERMINATE_INSTANCE)
        mock_ec2.terminate_instances.assert_called_with(InstanceIds=[resource_id])
        
        # Test DELETE_SNAPSHOT
        await remediation_service._execute_action("snap-123", RemediationAction.DELETE_SNAPSHOT)
        mock_ec2.delete_snapshot.assert_called_with(SnapshotId="snap-123")
        
        # Test RELEASE_ELASTIC_IP
        await remediation_service._execute_action("eipalloc-123", RemediationAction.RELEASE_ELASTIC_IP)
        mock_ec2.release_address.assert_called_with(AllocationId="eipalloc-123")
        
        # Test DELETE_NAT_GATEWAY
        await remediation_service._execute_action("nat-123", RemediationAction.DELETE_NAT_GATEWAY)
        mock_ec2.delete_nat_gateway.assert_called_with(NatGatewayId="nat-123")

@pytest.mark.asyncio
async def test_execute_action_rds_variations(remediation_service):
    """Test various RDS remediation actions."""
    resource_id = "db-instance-123"
    
    with patch.object(remediation_service, "_get_client", new_callable=AsyncMock) as mock_get_client:
        mock_rds = AsyncMock()
        mock_get_client.return_value.__aenter__.return_value = mock_rds
        
        # Test STOP_RDS_INSTANCE
        await remediation_service._execute_action(resource_id, RemediationAction.STOP_RDS_INSTANCE)
        mock_rds.stop_db_instance.assert_called_with(DBInstanceIdentifier=resource_id)
        
        # Test DELETE_RDS_INSTANCE
        await remediation_service._execute_action(resource_id, RemediationAction.DELETE_RDS_INSTANCE)
        mock_rds.delete_db_instance.assert_called_with(
            DBInstanceIdentifier=resource_id,
            SkipFinalSnapshot=True
        )

@pytest.mark.asyncio
async def test_execute_action_s3_and_ecr(remediation_service):
    """Test S3 and ECR remediation actions."""
    with patch.object(remediation_service, "_get_client", new_callable=AsyncMock) as mock_get_client:
        mock_s3 = AsyncMock()
        mock_ecr = AsyncMock()
        
        # Mock S3
        mock_get_client.return_value.__aenter__.return_value = mock_s3
        await remediation_service._execute_action("my-bucket", RemediationAction.DELETE_S3_BUCKET)
        mock_s3.delete_bucket.assert_called_with(Bucket="my-bucket")
        
        # Mock ECR
        mock_get_client.return_value.__aenter__.return_value = mock_ecr
        await remediation_service._execute_action("repo@sha256:123", RemediationAction.DELETE_ECR_IMAGE)
        mock_ecr.batch_delete_image.assert_called_once()
        args, kwargs = mock_ecr.batch_delete_image.call_args
        assert kwargs["repositoryName"] == "repo"
        assert kwargs["imageIds"][0]["imageDigest"] == "sha256:123"

@pytest.mark.asyncio
async def test_execute_action_redshift_and_elb(remediation_service):
    """Test Redshift and ELB remediation actions."""
    with patch.object(remediation_service, "_get_client", new_callable=AsyncMock) as mock_get_client:
        mock_redshift = AsyncMock()
        mock_elb = AsyncMock()
        
        # Mock Redshift
        mock_get_client.return_value.__aenter__.return_value = mock_redshift
        await remediation_service._execute_action("cluster-123", RemediationAction.DELETE_REDSHIFT_CLUSTER)
        mock_redshift.delete_cluster.assert_called_with(
            ClusterIdentifier="cluster-123",
            SkipFinalClusterSnapshot=True
        )
        
        # Mock ELB
        mock_get_client.return_value.__aenter__.return_value = mock_elb
        await remediation_service._execute_action("arn:elb", RemediationAction.DELETE_LOAD_BALANCER)
        mock_elb.delete_load_balancer.assert_called_with(LoadBalancerArn="arn:elb")

@pytest.mark.asyncio
async def test_execute_action_sagemaker(remediation_service):
    """Test SageMaker remediation actions."""
    with patch.object(remediation_service, "_get_client", new_callable=AsyncMock) as mock_get_client:
        mock_sagemaker = AsyncMock()
        mock_get_client.return_value.__aenter__.return_value = mock_sagemaker
        
        await remediation_service._execute_action("endpoint-123", RemediationAction.DELETE_SAGEMAKER_ENDPOINT)
        mock_sagemaker.delete_endpoint.assert_called_with(EndpointName="endpoint-123")
        mock_sagemaker.delete_endpoint_config.assert_called_with(EndpointConfigName="endpoint-123")

@pytest.mark.asyncio
async def test_create_backups(remediation_service):
    """Test backup creation logic for different services."""
    with patch.object(remediation_service, "_get_client", new_callable=AsyncMock) as mock_get_client:
        # RDS Backup
        mock_rds = AsyncMock()
        mock_get_client.return_value.__aenter__.return_value = mock_rds
        snapshot_id = await remediation_service._create_rds_backup("instance-123", 7)
        assert snapshot_id.startswith("valdrix-backup-instance-123-")
        mock_rds.create_db_snapshot.assert_called_once()
        
        # Redshift Backup
        mock_redshift = AsyncMock()
        mock_get_client.return_value.__aenter__.return_value = mock_redshift
        snapshot_id = await remediation_service._create_redshift_backup("cluster-123", 14)
        assert snapshot_id.startswith("valdrix-backup-cluster-123-")
        mock_redshift.create_cluster_snapshot.assert_called_once()

@pytest.mark.asyncio
async def test_execute_action_invalid(remediation_service):
    """Test that invalid actions raise ValueError."""
    with pytest.raises(ValueError, match="Unknown action"):
        await remediation_service._execute_action("res-123", "invalid_action")

@pytest.mark.asyncio
async def test_aws_action_error_handling(remediation_service):
    """Test error handling when AWS call fails."""
    with patch.object(remediation_service, "_get_client", new_callable=AsyncMock) as mock_get_client:
        mock_ec2 = AsyncMock()
        mock_ec2.delete_volume.side_effect = ClientError(
            {"Error": {"Code": "VolumeInUse", "Message": "Still attached"}},
            "DeleteVolume"
        )
        mock_get_client.return_value.__aenter__.return_value = mock_ec2
        
        with pytest.raises(ClientError):
            await remediation_service._execute_action("vol-123", RemediationAction.DELETE_VOLUME)
