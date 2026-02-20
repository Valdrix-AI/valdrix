from typing import List, Dict, Any
from botocore.exceptions import ClientError
import structlog
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry

logger = structlog.get_logger()


@registry.register("aws")
class CustomerManagedKeysPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "customer_managed_kms_keys"

    async def scan(


    

    self,


    

    session: Any,


    

    region: str,


    

    credentials: Dict[str, Any] | None = None,


    

    config: Any = None,


    

    inventory: Any = None,


    

    **kwargs: Any,


    ) -> List[Dict[str, Any]]:
        zombies = []
        try:
            async with self._get_client(
                session, "kms", region, credentials, config=config
            ) as kms:
                paginator = kms.get_paginator("list_keys")
                async for page in paginator.paginate():
                    for key in page["Keys"]:
                        try:
                            key_id = key["KeyId"]
                            # We need DescribeKey to know if it's Customer Managed
                            meta = await kms.describe_key(KeyId=key_id)
                            metadata = meta["KeyMetadata"]

                            if (
                                metadata["KeyManager"] == "CUSTOMER"
                                and metadata["KeyState"] != "PendingDeletion"
                            ):
                                # It's a customer key and active (costing money)

                                # Get aliases for better reporting
                                try:
                                    aliases_resp = await kms.list_aliases(KeyId=key_id)
                                    alias_names = [
                                        a["AliasName"]
                                        for a in aliases_resp.get("Aliases", [])
                                    ]
                                    alias_str = (
                                        ", ".join(alias_names)
                                        if alias_names
                                        else "No Alias"
                                    )
                                except ClientError:
                                    alias_str = "Unknown Alias"

                                zombies.append(
                                    {
                                        "resource_id": key_id,
                                        "resource_name": alias_str,
                                        "resource_type": "KMS Key",
                                        "monthly_cost": 1.00,  # Approx $1/month
                                        "recommendation": "Schedule deletion if unused",
                                        "action": "schedule_key_deletion",
                                        "confidence_score": 1.0,
                                        "explainability_notes": f"Customer Managed Key '{alias_str}' incurs a monthly fee regardless of usage.",
                                    }
                                )
                        except ClientError as e:
                            logger.warning(
                                "kms_key_describe_failed",
                                key_id=key.get("KeyId"),
                                error=str(e),
                            )

        except ClientError as e:
            logger.warning("kms_scan_error", error=str(e))

        return zombies
