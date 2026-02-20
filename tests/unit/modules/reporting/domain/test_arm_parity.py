import pytest
from unittest.mock import MagicMock, AsyncMock

from app.modules.reporting.domain.azure_ampere import AzureAmpereAnalyzer
from app.modules.reporting.domain.gcp_tau import GCPTauAnalyzer
from app.modules.reporting.domain.graviton_analyzer import GravitonAnalyzer


@pytest.mark.asyncio
async def test_azure_ampere_analyzer_finds_candidates():
    adapter = MagicMock()
    analyzer = AzureAmpereAnalyzer(adapter)
    
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
    
    analyzer.adapter.discover_resources = AsyncMock(return_value=mock_instances)
    result = await analyzer.analyze()
        
    assert result["total_instances"] == 2
    assert result["arm_instances"] == 1
    assert result["migration_candidates"] == 1
    assert result["candidates"][0]["recommended_type"] == "Standard_D2ps_v5"

@pytest.mark.asyncio
async def test_gcp_tau_analyzer_finds_candidates():
    adapter = MagicMock()
    analyzer = GCPTauAnalyzer(adapter)
    
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
    
    analyzer.adapter.discover_resources = AsyncMock(return_value=mock_instances)
    result = await analyzer.analyze()
        
    assert result["total_instances"] == 2
    assert result["arm_instances"] == 1
    assert result["migration_candidates"] == 1
    assert result["candidates"][0]["recommended_type"] == "t2a-standard-1"

@pytest.mark.asyncio
async def test_graviton_analyzer_finds_candidates():
    adapter = MagicMock()
    analyzer = GravitonAnalyzer(adapter)

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

    adapter.discover_resources = AsyncMock(return_value=mock_instances)

    result = await analyzer.analyze()
        
    assert result["total_instances"] == 2
    assert result["arm_instances"] == 1
    assert result["migration_candidates"] == 1
    assert result["candidates"][0]["recommended_type"] == "m7g.large"
    assert "compatible_workloads" in result
