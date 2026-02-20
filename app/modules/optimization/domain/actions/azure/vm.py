from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.azure.base import BaseAzureAction
from app.modules.optimization.domain.actions.base import ExecutionResult, ExecutionStatus, RemediationContext
from app.modules.optimization.domain.actions.factory import RemediationActionFactory


@RemediationActionFactory.register("azure", RemediationAction.DEALLOCATE_AZURE_VM)
class AzureDeallocateVmAction(BaseAzureAction):
    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        # Azure resource_id is usually the full ARM ID
        parts = resource_id.split("/")
        rg_name = parts[parts.index("resourceGroups") + 1]
        vm_name = parts[parts.index("virtualMachines") + 1]

        client = await self._get_compute_client(context)
        # deallocate is the Azure equivalent of STOP (releases hardware)
        poller = await client.virtual_machines.begin_deallocate(rg_name, vm_name)
        await poller.result()

        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            resource_id=resource_id,
            action_taken=RemediationAction.DEALLOCATE_AZURE_VM.value
        )


@RemediationActionFactory.register("azure", RemediationAction.RESIZE_AZURE_VM)
class AzureResizeVmAction(BaseAzureAction):
    async def validate(self, resource_id: str, context: RemediationContext) -> bool:
        if not context.parameters or "target_size" not in context.parameters:
            return False
        return True

    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        if not context.parameters:
            raise ValueError("context.parameters missing")
        target_size = context.parameters["target_size"]
        parts = resource_id.split("/")
        rg_name = parts[parts.index("resourceGroups") + 1]
        vm_name = parts[parts.index("virtualMachines") + 1]

        client = await self._get_compute_client(context)
        
        # 1. Get current VM
        vm = await client.virtual_machines.get(rg_name, vm_name)
        
        # 2. Update hardware profile
        if not vm.hardware_profile:
            from azure.mgmt.compute.models import HardwareProfile
            vm.hardware_profile = HardwareProfile()
        vm.hardware_profile.vm_size = target_size
        
        # 3. Apply update (Azure will restart VM if needed)
        poller = await client.virtual_machines.begin_create_or_update(rg_name, vm_name, vm)
        await poller.result()

        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            resource_id=resource_id,
            action_taken=RemediationAction.RESIZE_AZURE_VM.value,
            metadata={"target_size": target_size}
        )
