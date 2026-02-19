import asyncio
import time
from botocore.exceptions import ClientError
from typing import Any, Dict, Optional
from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.aws.base import BaseAWSAction
from app.modules.optimization.domain.actions.base import ExecutionResult, ExecutionStatus, RemediationContext
from app.modules.optimization.domain.actions.factory import RemediationActionFactory


@RemediationActionFactory.register("aws", RemediationAction.DELETE_VOLUME)
class AWSDeleteVolumeAction(BaseAWSAction):
    async def create_backup(self, resource_id: str, context: RemediationContext) -> Optional[str]:
        """Create a snapshot backup before deleting a volume."""
        async with await self._get_client("ec2", context) as ec2:
            response = await ec2.create_snapshot(
                VolumeId=resource_id,
                Description=f"Valdrix backup before deletion of {resource_id}",
                TagSpecifications=[
                    {
                        "ResourceType": "snapshot",
                        "Tags": [
                            {"Key": "Valdrix", "Value": "remediation-backup"},
                            {"Key": "OriginalVolume", "Value": resource_id},
                        ],
                    }
                ],
            )
            return str(response["SnapshotId"])

    async def _perform_action(self, resource_id: str, context: RemediationContext) -> ExecutionResult:
        async with await self._get_client("ec2", context) as ec2:
            # 1. Check for attachments and detach if necessary
            volume_info = await ec2.describe_volumes(VolumeIds=[resource_id])
            volumes = volume_info.get("Volumes", [])
            if volumes:
                attachments = volumes[0].get("Attachments", [])
                for attachment in attachments:
                    if attachment.get("State") in {"attached", "attaching", "busy"}:
                        await ec2.detach_volume(
                            VolumeId=resource_id,
                            InstanceId=attachment.get("InstanceId"),
                            Force=True
                        )
                        
                # Wait for detachment (max 3 mins)
                if attachments:
                    deadline = time.monotonic() + 180
                    while time.monotonic() < deadline:
                        v_info = await ec2.describe_volumes(VolumeIds=[resource_id])
                        if not v_info.get("Volumes", [])[0].get("Attachments", []):
                            break
                        await asyncio.sleep(5)

            # 2. Delete the volume
            await ec2.delete_volume(VolumeId=resource_id)
            
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id=resource_id,
                action_taken=RemediationAction.DELETE_VOLUME.value
            )
