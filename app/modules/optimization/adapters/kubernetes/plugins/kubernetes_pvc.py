
from typing import List, Dict, Any, cast
import structlog
from kubernetes_asyncio import client, config as k8s_config
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
from app.modules.reporting.domain.pricing.service import PricingService

logger = structlog.get_logger()

@registry.register("kubernetes")
class OrphanedPVCPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "orphaned_pvc"
    
    @property
    def provider(self) -> str:
        return "kubernetes"

    async def scan(
        self,
        session: Any = None,
        region: str = "global",
        credentials: Dict[str, str] | None = None,
        config: Dict[str, Any] | None = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """
        Scans for Persistent Volume Claims (PVCs) that are 'Bound' but not mounted by any Pod.
        """
        zombies = []
        try:
            # Connect to K8s
            if config and "kubeconfig" in config:
                await k8s_config.load_kube_config(config_file=config["kubeconfig"])
            else:
                cast(Any, k8s_config.load_incluster_config)()

            async with client.ApiClient() as api_client:
                v1 = client.CoreV1Api(api_client)
                
                # 1. List all PVCs
                pvc_list = await v1.list_persistent_volume_claim_for_all_namespaces()
                all_pvcs = {
                    (p.metadata.namespace, p.metadata.name): p 
                    for p in pvc_list.items 
                    if p.status.phase == "Bound"
                }

                # 2. List all Pods to find mounted PVCs
                pod_list = await v1.list_pod_for_all_namespaces()
                mounted_pvcs = set()
                
                for pod in pod_list.items:
                    if not pod.spec.volumes:
                        continue
                    for vol in pod.spec.volumes:
                        if vol.persistent_volume_claim:
                             mounted_pvcs.add((pod.metadata.namespace, vol.persistent_volume_claim.claim_name))

                # 3. Identify Orphans
                for (ns, name), pvc in all_pvcs.items():
                    if (ns, name) not in mounted_pvcs:
                        size_str = pvc.spec.resources.requests.get("storage", "0")
                        storage_class = pvc.spec.storage_class_name or "standard"
                        
                        # Rough parsing of size (e.g., "10Gi")
                        size_gb = self._parse_size(size_str)
                        
                        # Estimate Cost
                        monthly_cost = PricingService.estimate_monthly_waste(
                            provider="kubernetes",
                            resource_type="pvc",
                            resource_size=f"{storage_class}:{size_gb}GB",
                            region=region
                        )

                        zombies.append({
                            "resource_id": pvc.metadata.uid,
                            "resource_type": "Persistent Volume Claim",
                            "name": name,
                            "namespace": ns,
                            "size": size_str,
                            "storage_class": storage_class,
                            "monthly_cost": monthly_cost,
                            "recommendation": "Delete PVC if data is not needed",
                            "action": "delete_pvc",
                            "supports_backup": True,
                            "explainability_notes": f"PVC {name} in namespace {ns} is Bound but not mounted by any active Pod.",
                            "confidence_score": 0.95
                        })
                        
        except Exception as e:
            logger.error("k8s_pvc_scan_failed", error=str(e))
            
        return zombies

    def _parse_size(self, size_str: str) -> float:
        """Helper to parse K8s quantity strings to GB float."""
        if not size_str:
            return 0.0
        
        units = {"Ki": 1/1024/1024, "Mi": 1/1024, "Gi": 1, "Ti": 1024}
        for unit, multiplier in units.items():
            if size_str.endswith(unit):
                try:
                    return float(size_str.replace(unit, "")) * multiplier
                except ValueError:
                    pass
        try:
            return float(size_str)
        except ValueError:
            return 0.0
