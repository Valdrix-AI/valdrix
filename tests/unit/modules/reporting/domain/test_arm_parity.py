import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from app.modules.reporting.domain.azure_ampere import AzureAmpereAnalyzer
from app.modules.reporting.domain.gcp_tau import GCPTauAnalyzer
from app.modules.reporting.domain.graviton_analyzer import GravitonAnalyzer
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.models.aws_connection import AWSConnection


def _azure_connection():
    return AzureConnection(
        id=uuid4(),
        tenant_id=uuid4(),
        name="Azure Test",
        azure_tenant_id="tenant",
        client_id="client",
        subscription_id="sub",
        client_secret="secret",
        auth_method="secret",
    )

def _gcp_connection():
    return GCPConnection(
        id=uuid4(),
        tenant_id=uuid4(),
        name="GCP Test",
        project_id="test-project",
        auth_method="secret",
    )

def _aws_connection():
    return AWSConnection(
        id=uuid4(),
        tenant_id=uuid4(),
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/test",
        external_id="vx-test",
        region="us-east-1",
    )

@pytest.mark.asyncio
async def test_azure_ampere_analyzer_finds_candidates():
    connection = _azure_connection()
    analyzer = AzureAmpereAnalyzer(connection)
    
    mock_instances = [
        {
            "id": "vm1",
            "name": "vm1",
            "provider": "azure",
            "metadata": {"size": "Standard_D2s_v5"}
        },
        {
            "id": "vm2",
            "name": "vm2",
            "provider": "azure",
            "metadata": {"size": "Standard_D2ps_v5"} # Already ARM
        }
    ]
    
    with patch.object(analyzer.adapter, "discover_resources", AsyncMock(return_value=mock_instances)):
        result = await analyzer.analyze()
        
    assert result["total_instances"] == 2
    assert result["arm_instances"] == 1
    assert result["migration_candidates"] == 1
    assert result["candidates"][0]["recommended_type"] == "Standard_D2ps_v5"

@pytest.mark.asyncio
async def test_gcp_tau_analyzer_finds_candidates():
    connection = _gcp_connection()
    analyzer = GCPTauAnalyzer(connection)
    
    mock_instances = [
        {
            "id": "inst1",
            "name": "inst1",
            "provider": "gcp",
            "metadata": {"machine_type": "n1-standard-1"}
        },
        {
            "id": "inst2",
            "name": "inst2",
            "provider": "gcp",
            "metadata": {"machine_type": "t2a-standard-1"} # Already ARM
        }
    ]
    
    with patch.object(analyzer.adapter, "discover_resources", AsyncMock(return_value=mock_instances)):
        result = await analyzer.analyze()
        
    assert result["total_instances"] == 2
    assert result["arm_instances"] == 1
    assert result["migration_candidates"] == 1
    assert result["candidates"][0]["recommended_type"] == "t2a-standard-1"

@pytest.mark.asyncio
async def test_graviton_analyzer_finds_candidates():
    connection = _aws_connection()
    
    # Mock AdapterFactory to prevent ConfigurationError during __init__
    with patch("app.modules.reporting.domain.arm_analyzer.AdapterFactory.get_adapter") as mock_factory:
        mock_adapter = MagicMock()
        mock_factory.return_value = mock_adapter
        
        analyzer = GravitonAnalyzer(connection) 
        
        mock_instances = [
            {
                "id": "i-1",
                "name": "vm1",
                "type": "m5.large",
                "provider": "aws",
            },
            {
                "id": "i-2",
                "name": "vm2",
                "type": "m7g.large", # Already Graviton
                "provider": "aws",
            }
        ]
        
        mock_adapter.discover_resources = AsyncMock(return_value=mock_instances)
        
        result = await analyzer.analyze()
        
    assert result["total_instances"] == 2
    assert result["arm_instances"] == 1
    assert result["migration_candidates"] == 1
    assert result["candidates"][0]["recommended_type"] == "m7g.large"
    assert "compatible_workloads" in result
