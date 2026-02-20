from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.gcp.base import BaseGCPAction
from app.modules.optimization.domain.actions.base import ExecutionResult, ExecutionStatus, RemediationContext
from app.modules.optimization.domain.actions.factory import RemediationActionFactory


@RemediationActionFactory.register("gcp", RemediationAction.STOP_GCP_INSTANCE)
class GCPStopInstanceAction(BaseGCPAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        # resource_id for GCP is often "project/zone/instance"
        parts = resource_id.split("/")
        project = parts[0]
        zone = parts[1]
        instance = parts[2]

        client = await self._get_instances_client(context)
        operation = client.stop(project=project, zone=zone, instance=instance)
        # Wait for operation
        operation.result()  # type: ignore[no-untyped-call]

        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            resource_id=resource_id,
            action_taken=RemediationAction.STOP_GCP_INSTANCE.value
        )


@RemediationActionFactory.register("gcp", RemediationAction.RESIZE_GCP_INSTANCE)
class GCPResizeInstanceAction(BaseGCPAction):
    async def validate(self, resource_id: str, context: RemediationContext) -> bool:
        if not context.parameters or "target_machine_type" not in context.parameters:
            return False
        return True

    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        if not context.parameters:
            raise ValueError("Missing parameters for resizing")
        target_machine_type = context.parameters["target_machine_type"]
        parts = resource_id.split("/")
        project = parts[0]
        zone = parts[1]
        instance = parts[2]

        client = await self._get_instances_client(context)
        
        # 1. GCP Resize requires instance to be TERMINATED (stopped)
        stop_op = client.stop(project=project, zone=zone, instance=instance)
        stop_op.result()  # type: ignore[no-untyped-call]
        
        # 2. Set machine type
        # machine_type should be the full URI or just the name depending on the SDK version
        # Typically "zones/{zone}/machineTypes/{target_machine_type}"
        machine_type_uri = f"zones/{zone}/machineTypes/{target_machine_type}"
        
        from google.cloud.compute_v1.types import InstancesSetMachineTypeRequest
        request = InstancesSetMachineTypeRequest(machine_type=machine_type_uri)
        
        set_op = client.set_machine_type(
            project=project, 
            zone=zone, 
            instance=instance, 
            instances_set_machine_type_request_resource=request
        )
        set_op.result()  # type: ignore[no-untyped-call]
        
        # 3. Start instance
        start_op = client.start(project=project, zone=zone, instance=instance)
        start_op.result()  # type: ignore[no-untyped-call]

        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            resource_id=resource_id,
            action_taken=RemediationAction.RESIZE_GCP_INSTANCE.value,
            metadata={"target_machine_type": target_machine_type}
        )
