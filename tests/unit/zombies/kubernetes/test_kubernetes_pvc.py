
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.modules.optimization.domain.plugin import ZombiePlugin

@pytest.mark.asyncio
async def test_kubernetes_pvc_plugin_structure():
    """TDD Step 1: Ensure plugin exists and inherits correctly (Fails if module missing)."""
    from app.modules.optimization.adapters.kubernetes.plugins.kubernetes_pvc import OrphanedPVCPlugin
    plugin = OrphanedPVCPlugin()
    assert isinstance(plugin, ZombiePlugin)
    assert plugin.category_key == "orphaned_pvc"
    assert plugin.provider == "kubernetes"

@pytest.mark.asyncio
async def test_kubernetes_pvc_scan_logic():
    """TDD Step 2: Ensure it detects Bound PVCs with no Pods (Fails if logic missing)."""
    from app.modules.optimization.adapters.kubernetes.plugins.kubernetes_pvc import OrphanedPVCPlugin
    
    plugin = OrphanedPVCPlugin()
    
    # Mock K8s V1 Api
    mock_core_v1 = MagicMock()

    # Mock PVCs
    pvc1 = MagicMock()
    pvc1.metadata.name = "used-pvc"
    pvc1.metadata.namespace = "default"
    pvc1.metadata.uid = "uid-1"
    pvc1.status.phase = "Bound"
    pvc1.spec.resources.requests = {"storage": "10Gi"}
    pvc1.spec.storage_class_name = "gp2"

    pvc2 = MagicMock()
    pvc2.metadata.name = "orphaned-pvc"
    pvc2.metadata.namespace = "default"
    pvc2.metadata.uid = "uid-2"
    pvc2.status.phase = "Bound"
    pvc2.spec.resources.requests = {"storage": "50Gi"}
    pvc2.spec.storage_class_name = "gp3"

    # Mock Pods
    pod1 = MagicMock()
    pod1.metadata.namespace = "default"
    pod1.spec.volumes = [MagicMock(persistent_volume_claim=MagicMock(claim_name="used-pvc"))]
    
    # Setup Async Returns for V1 methods
    # Kubernetes methods return an object with .items, and the method itself is a coroutine
    mock_pvc_list = MagicMock()
    mock_pvc_list.items = [pvc1, pvc2]
    mock_core_v1.list_persistent_volume_claim_for_all_namespaces = AsyncMock(return_value=mock_pvc_list)

    mock_pod_list = MagicMock()
    mock_pod_list.items = [pod1]
    mock_core_v1.list_pod_for_all_namespaces = AsyncMock(return_value=mock_pod_list)
    
    # Mock ApiClient Context Manager
    mock_api_client_instance = MagicMock()
    mock_api_client_instance.__aenter__ = AsyncMock(return_value=mock_api_client_instance)
    mock_api_client_instance.__aexit__ = AsyncMock(return_value=None)
    
    # Mock Config/Creds
    session = MagicMock()
    
    
    with patch("app.modules.optimization.adapters.kubernetes.plugins.kubernetes_pvc.client.ApiClient", return_value=mock_api_client_instance):
        with patch("app.modules.optimization.adapters.kubernetes.plugins.kubernetes_pvc.client.CoreV1Api", return_value=mock_core_v1):
            with patch("app.modules.optimization.adapters.kubernetes.plugins.kubernetes_pvc.k8s_config.load_kube_config", new_callable=AsyncMock):
                 zombies = await plugin.scan(session=session, region="us-east-1", config={"kubeconfig": "fake"})
             
    assert len(zombies) == 1
    assert zombies[0]["resource_id"] == "uid-2"
    assert zombies[0]["resource_type"] == "Persistent Volume Claim"
    assert zombies[0]["action"] == "delete_pvc"
