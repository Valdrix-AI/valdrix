from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.aws.analytics import (
    AWSDeleteRedshiftClusterAction,
    AWSDeleteSageMakerEndpointAction,
)
from app.modules.optimization.domain.actions.aws.base import BaseAWSAction
from app.modules.optimization.domain.actions.aws.ec2 import (
    AWSDeleteNatGatewayAction,
    AWSDeleteSnapshotAction,
    AWSReleaseElasticIpAction,
    AWSResizeInstanceAction,
    AWSStopInstanceAction,
    AWSTerminateInstanceAction,
)
from app.modules.optimization.domain.actions.azure.base import BaseAzureAction
from app.modules.optimization.domain.actions.azure.vm import (
    AzureDeallocateVmAction,
    AzureResizeVmAction,
)
from app.modules.optimization.domain.actions.base import (
    ExecutionResult,
    ExecutionStatus,
    RemediationContext,
)
from app.modules.optimization.domain.actions.gcp.base import BaseGCPAction
from app.modules.optimization.domain.actions.gcp.compute import (
    GCPResizeInstanceAction,
    GCPStopInstanceAction,
)


class _AsyncClientContext:
    def __init__(self, client: object) -> None:
        self._client = client

    async def __aenter__(self) -> object:
        return self._client

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class _TestAWSBaseAction(BaseAWSAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        del context
        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            resource_id=resource_id,
            action_taken="noop",
        )


class _TestAzureBaseAction(BaseAzureAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        del context
        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            resource_id=resource_id,
            action_taken="noop",
        )


class _TestGCPBaseAction(BaseGCPAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        del context
        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            resource_id=resource_id,
            action_taken="noop",
        )


@pytest.fixture
def aws_context() -> RemediationContext:
    return RemediationContext(
        tenant_id=uuid4(),
        region="us-east-1",
        tier="growth",
        credentials={"aws_access_key_id": "ak", "aws_secret_access_key": "sk"},
    )


@pytest.fixture
def azure_context() -> RemediationContext:
    return RemediationContext(
        tenant_id=uuid4(),
        region="eastus",
        tier="pro",
        credentials={
            "tenant_id": "tenant",
            "client_id": "client",
            "client_secret": "secret",
            "subscription_id": "sub-123",
        },
    )


@pytest.fixture
def gcp_context() -> RemediationContext:
    return RemediationContext(
        tenant_id=uuid4(),
        region="us-central1",
        tier="pro",
        credentials={"type": "service_account", "project_id": "proj"},
    )


@pytest.mark.asyncio
async def test_base_aws_action_get_client_maps_endpoint_and_credentials(
    aws_context: RemediationContext,
) -> None:
    action = _TestAWSBaseAction()
    fake_client = MagicMock()

    with (
        patch("app.modules.optimization.domain.actions.aws.base.get_settings") as get_settings,
        patch("app.modules.optimization.domain.actions.aws.base.map_aws_credentials") as map_creds,
    ):
        get_settings.return_value = SimpleNamespace(AWS_ENDPOINT_URL="http://localstack:4566")
        map_creds.return_value = {"aws_access_key_id": "mapped-ak"}
        action.session.client = MagicMock(return_value=fake_client)

        client = await action._get_client("ec2", aws_context)

        assert client is fake_client
        map_creds.assert_called_once_with(aws_context.credentials)
        action.session.client.assert_called_once_with(
            "ec2",
            region_name="us-east-1",
            endpoint_url="http://localstack:4566",
            aws_access_key_id="mapped-ak",
        )


@pytest.mark.asyncio
async def test_aws_ec2_actions_execute_success_paths(
    aws_context: RemediationContext,
) -> None:
    ec2 = MagicMock()
    ec2.stop_instances = AsyncMock()
    ec2.terminate_instances = AsyncMock()
    ec2.delete_snapshot = AsyncMock()
    ec2.release_address = AsyncMock()
    ec2.delete_nat_gateway = AsyncMock()

    stop_action = AWSStopInstanceAction()
    term_action = AWSTerminateInstanceAction()
    snap_action = AWSDeleteSnapshotAction()
    eip_action = AWSReleaseElasticIpAction()
    nat_action = AWSDeleteNatGatewayAction()

    for action in (stop_action, term_action, snap_action, eip_action, nat_action):
        action._get_client = AsyncMock(return_value=_AsyncClientContext(ec2))

    stop_result = await stop_action.execute("i-123", aws_context)
    term_result = await term_action.execute("i-456", aws_context)
    snap_result = await snap_action.execute("snap-1", aws_context)
    eip_result = await eip_action.execute("eipalloc-1", aws_context)
    nat_result = await nat_action.execute("nat-1", aws_context)

    assert stop_result.status == ExecutionStatus.SUCCESS
    assert stop_result.action_taken == RemediationAction.STOP_INSTANCE.value
    assert term_result.status == ExecutionStatus.SUCCESS
    assert term_result.action_taken == RemediationAction.TERMINATE_INSTANCE.value
    assert snap_result.status == ExecutionStatus.SUCCESS
    assert snap_result.action_taken == RemediationAction.DELETE_SNAPSHOT.value
    assert eip_result.status == ExecutionStatus.SUCCESS
    assert eip_result.action_taken == RemediationAction.RELEASE_ELASTIC_IP.value
    assert nat_result.status == ExecutionStatus.SUCCESS
    assert nat_result.action_taken == RemediationAction.DELETE_NAT_GATEWAY.value

    ec2.stop_instances.assert_any_await(InstanceIds=["i-123"])
    ec2.terminate_instances.assert_awaited_once_with(InstanceIds=["i-456"])
    ec2.delete_snapshot.assert_awaited_once_with(SnapshotId="snap-1")
    ec2.release_address.assert_awaited_once_with(AllocationId="eipalloc-1")
    ec2.delete_nat_gateway.assert_awaited_once_with(NatGatewayId="nat-1")


@pytest.mark.asyncio
async def test_aws_resize_instance_validation_and_execute(
    aws_context: RemediationContext,
) -> None:
    action = AWSResizeInstanceAction()

    invalid_context = RemediationContext(
        tenant_id=aws_context.tenant_id,
        region=aws_context.region,
        tier=aws_context.tier,
        parameters={},
    )
    skipped = await action.execute("i-123", invalid_context)
    assert skipped.status == ExecutionStatus.SKIPPED

    valid_context = RemediationContext(
        tenant_id=aws_context.tenant_id,
        region=aws_context.region,
        tier=aws_context.tier,
        parameters={"target_instance_type": "t3.micro"},
    )

    ec2 = MagicMock()
    ec2.stop_instances = AsyncMock()
    ec2.start_instances = AsyncMock()
    ec2.modify_instance_attribute = AsyncMock()
    waiter = MagicMock()
    waiter.wait = AsyncMock()
    ec2.get_waiter = MagicMock(return_value=waiter)

    action._get_client = AsyncMock(return_value=_AsyncClientContext(ec2))
    result = await action.execute("i-123", valid_context)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.metadata == {"target_type": "t3.micro"}
    ec2.stop_instances.assert_awaited_once_with(InstanceIds=["i-123"])
    ec2.get_waiter.assert_called_once_with("instance_stopped")
    waiter.wait.assert_awaited_once_with(InstanceIds=["i-123"])
    ec2.modify_instance_attribute.assert_awaited_once_with(
        InstanceId="i-123",
        InstanceType={"Value": "t3.micro"},
    )
    ec2.start_instances.assert_awaited_once_with(InstanceIds=["i-123"])


@pytest.mark.asyncio
async def test_aws_analytics_actions_execute(
    aws_context: RemediationContext,
) -> None:
    redshift_action = AWSDeleteRedshiftClusterAction()
    sagemaker_action = AWSDeleteSageMakerEndpointAction()

    redshift = MagicMock()
    redshift.delete_cluster = AsyncMock()
    sagemaker = MagicMock()
    sagemaker.delete_endpoint = AsyncMock()
    sagemaker.delete_endpoint_config = AsyncMock()

    redshift_action._get_client = AsyncMock(return_value=_AsyncClientContext(redshift))
    sagemaker_action._get_client = AsyncMock(return_value=_AsyncClientContext(sagemaker))

    redshift_result = await redshift_action.execute("cluster-1", aws_context)
    sagemaker_result = await sagemaker_action.execute("endpoint-1", aws_context)

    assert redshift_result.status == ExecutionStatus.SUCCESS
    assert redshift_result.action_taken == RemediationAction.DELETE_REDSHIFT_CLUSTER.value
    assert sagemaker_result.status == ExecutionStatus.SUCCESS
    assert (
        sagemaker_result.action_taken
        == RemediationAction.DELETE_SAGEMAKER_ENDPOINT.value
    )
    redshift.delete_cluster.assert_awaited_once_with(
        ClusterIdentifier="cluster-1",
        SkipFinalClusterSnapshot=True,
    )
    sagemaker.delete_endpoint.assert_awaited_once_with(EndpointName="endpoint-1")
    sagemaker.delete_endpoint_config.assert_awaited_once_with(
        EndpointConfigName="endpoint-1"
    )


@pytest.mark.asyncio
async def test_base_azure_action_credentials_and_client_cache(
    azure_context: RemediationContext,
) -> None:
    action = _TestAzureBaseAction()

    with (
        patch(
            "app.modules.optimization.domain.actions.azure.base.ClientSecretCredential"
        ) as credential_cls,
        patch(
            "app.modules.optimization.domain.actions.azure.base.ComputeManagementClient"
        ) as compute_cls,
    ):
        credential_instance = MagicMock()
        credential_cls.return_value = credential_instance
        compute_instance = MagicMock()
        compute_cls.return_value = compute_instance

        first_creds = await action._get_credentials(azure_context)
        second_creds = await action._get_credentials(azure_context)
        assert first_creds is second_creds

        first_client = await action._get_compute_client(azure_context)
        second_client = await action._get_compute_client(azure_context)
        assert first_client is second_client

        credential_cls.assert_called_once_with(
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
        )
        compute_cls.assert_called_once_with(
            credential=credential_instance,
            subscription_id="sub-123",
        )

    assert await action.validate("rid", azure_context) is True
    assert await action.create_backup("rid", azure_context) is None


@pytest.mark.asyncio
async def test_azure_actions_execute_paths(azure_context: RemediationContext) -> None:
    resource_id = "/subscriptions/sub-123/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/vm-a"

    deallocate_action = AzureDeallocateVmAction()
    resize_action = AzureResizeVmAction()

    vm_ops = MagicMock()
    deallocate_poller = MagicMock()
    deallocate_poller.result = AsyncMock()
    vm_ops.begin_deallocate = AsyncMock(return_value=deallocate_poller)

    vm_obj = SimpleNamespace(hardware_profile=None)
    vm_ops.get = AsyncMock(return_value=vm_obj)
    resize_poller = MagicMock()
    resize_poller.result = AsyncMock()
    vm_ops.begin_create_or_update = AsyncMock(return_value=resize_poller)

    compute_client = MagicMock(virtual_machines=vm_ops)
    deallocate_action._get_compute_client = AsyncMock(return_value=compute_client)
    resize_action._get_compute_client = AsyncMock(return_value=compute_client)

    deallocate_result = await deallocate_action.execute(resource_id, azure_context)

    invalid_resize_context = RemediationContext(
        tenant_id=azure_context.tenant_id,
        region=azure_context.region,
        tier=azure_context.tier,
        credentials=azure_context.credentials,
        parameters={},
    )
    skipped = await resize_action.execute(resource_id, invalid_resize_context)

    valid_resize_context = RemediationContext(
        tenant_id=azure_context.tenant_id,
        region=azure_context.region,
        tier=azure_context.tier,
        credentials=azure_context.credentials,
        parameters={"target_size": "Standard_B2s"},
    )

    with patch("azure.mgmt.compute.models.HardwareProfile") as hardware_profile_cls:
        hardware_profile_cls.return_value = SimpleNamespace(vm_size=None)
        resize_result = await resize_action.execute(resource_id, valid_resize_context)

    assert deallocate_result.status == ExecutionStatus.SUCCESS
    assert deallocate_result.action_taken == RemediationAction.DEALLOCATE_AZURE_VM.value
    vm_ops.begin_deallocate.assert_awaited_once_with("rg-a", "vm-a")
    deallocate_poller.result.assert_awaited_once()

    assert skipped.status == ExecutionStatus.SKIPPED

    assert resize_result.status == ExecutionStatus.SUCCESS
    assert resize_result.action_taken == RemediationAction.RESIZE_AZURE_VM.value
    assert resize_result.metadata == {"target_size": "Standard_B2s"}
    vm_ops.get.assert_awaited_once_with("rg-a", "vm-a")
    vm_ops.begin_create_or_update.assert_awaited_once_with("rg-a", "vm-a", vm_obj)
    resize_poller.result.assert_awaited_once()
    assert vm_obj.hardware_profile is not None
    assert vm_obj.hardware_profile.vm_size == "Standard_B2s"


@pytest.mark.asyncio
async def test_base_gcp_action_credentials_and_client_resolution(
    gcp_context: RemediationContext,
) -> None:
    action = _TestGCPBaseAction()

    with patch(
        "app.modules.optimization.domain.actions.gcp.base.service_account.Credentials.from_service_account_info"
    ) as from_info:
        creds_obj = MagicMock()
        from_info.return_value = creds_obj
        creds = await action._get_credentials(gcp_context)
        assert creds is creds_obj
        from_info.assert_called_once_with(gcp_context.credentials)

    empty_context = RemediationContext(
        tenant_id=gcp_context.tenant_id,
        region=gcp_context.region,
        tier=gcp_context.tier,
        credentials={},
    )
    assert await action._get_credentials(empty_context) is None

    with (
        patch(
            "app.modules.optimization.domain.actions.gcp.base.service_account.Credentials.from_service_account_info"
        ) as from_info,
        patch(
            "app.modules.optimization.domain.actions.gcp.base.compute_v1.InstancesClient"
        ) as instances_cls,
    ):
        from_info.return_value = MagicMock()
        instance_client = MagicMock()
        instances_cls.return_value = instance_client
        client = await action._get_instances_client(gcp_context)
        assert client is instance_client
        instances_cls.assert_called_once()

    assert await action.validate("rid", gcp_context) is True
    assert await action.create_backup("rid", gcp_context) is None


@pytest.mark.asyncio
async def test_gcp_actions_execute_paths(gcp_context: RemediationContext) -> None:
    resource_id = "proj-a/us-central1-a/inst-1"

    stop_action = GCPStopInstanceAction()
    resize_action = GCPResizeInstanceAction()

    stop_op = MagicMock()
    stop_op.result = MagicMock()
    set_op = MagicMock()
    set_op.result = MagicMock()
    start_op = MagicMock()
    start_op.result = MagicMock()

    client = MagicMock()
    client.stop = MagicMock(side_effect=[stop_op, stop_op])
    client.set_machine_type = MagicMock(return_value=set_op)
    client.start = MagicMock(return_value=start_op)

    stop_action._get_instances_client = AsyncMock(return_value=client)
    resize_action._get_instances_client = AsyncMock(return_value=client)

    stop_result = await stop_action.execute(resource_id, gcp_context)

    invalid_resize = RemediationContext(
        tenant_id=gcp_context.tenant_id,
        region=gcp_context.region,
        tier=gcp_context.tier,
        credentials=gcp_context.credentials,
        parameters={},
    )
    skipped = await resize_action.execute(resource_id, invalid_resize)

    valid_resize = RemediationContext(
        tenant_id=gcp_context.tenant_id,
        region=gcp_context.region,
        tier=gcp_context.tier,
        credentials=gcp_context.credentials,
        parameters={"target_machine_type": "e2-small"},
    )

    request_obj = MagicMock()
    with patch(
        "google.cloud.compute_v1.types.InstancesSetMachineTypeRequest",
        return_value=request_obj,
    ) as request_cls:
        resize_result = await resize_action.execute(resource_id, valid_resize)

    assert stop_result.status == ExecutionStatus.SUCCESS
    assert stop_result.action_taken == RemediationAction.STOP_GCP_INSTANCE.value
    client.stop.assert_any_call(project="proj-a", zone="us-central1-a", instance="inst-1")
    stop_op.result.assert_called()

    assert skipped.status == ExecutionStatus.SKIPPED

    assert resize_result.status == ExecutionStatus.SUCCESS
    assert resize_result.action_taken == RemediationAction.RESIZE_GCP_INSTANCE.value
    assert resize_result.metadata == {"target_machine_type": "e2-small"}
    request_cls.assert_called_once_with(
        machine_type="zones/us-central1-a/machineTypes/e2-small"
    )
    client.set_machine_type.assert_called_once_with(
        project="proj-a",
        zone="us-central1-a",
        instance="inst-1",
        instances_set_machine_type_request_resource=request_obj,
    )
    client.start.assert_called_once_with(
        project="proj-a",
        zone="us-central1-a",
        instance="inst-1",
    )


@pytest.mark.asyncio
async def test_gcp_resize_raises_when_parameters_missing(gcp_context: RemediationContext) -> None:
    action = GCPResizeInstanceAction()
    action._get_instances_client = AsyncMock()

    no_parameters_context = RemediationContext(
        tenant_id=gcp_context.tenant_id,
        region=gcp_context.region,
        tier=gcp_context.tier,
        credentials=gcp_context.credentials,
        parameters=None,
    )

    with pytest.raises(ValueError, match="Missing parameters"):
        await action._perform_action("p/z/i", no_parameters_context)
