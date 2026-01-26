import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.modules.reporting.domain.graviton_analyzer import GravitonAnalyzer

class AsyncIterator:
    def __init__(self, items):
        self.items = items
    def __aiter__(self):
        return self
    async def __anext__(self):
        if not self.items:
            raise StopAsyncIteration
        return self.items.pop(0)

@pytest.mark.asyncio
async def test_analyze_instances_finds_candidates():
    """Verify that analyze_instances identifies Graviton candidates."""
    
    # Mock EC2 responses
    mock_reservations = [
        {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-123",
                            "InstanceType": "m5.large", # Candidate
                            "Tags": [{"Key": "Name", "Value": "legacy-app"}]
                        },
                        {
                            "InstanceId": "i-456",
                            "InstanceType": "m7g.large", # Already Graviton
                            "Tags": [{"Key": "Name", "Value": "modern-app"}]
                        }
                    ]
                }
            ]
        }
    ]
    
    # Mock Paginator
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = AsyncIterator(mock_reservations)
    
    # Mock Client
    mock_ec2 = AsyncMock()
    mock_ec2.get_paginator = MagicMock(return_value=mock_paginator)
    
    # Mock Context Manager
    mock_cm = MagicMock()
    mock_cm.__aenter__.return_value = mock_ec2
    mock_cm.__aexit__.return_value = None
    
    with patch("aioboto3.Session") as mock_session_cls:
        mock_session = mock_session_cls.return_value
        mock_session.client.return_value = mock_cm
        
        analyzer = GravitonAnalyzer()
        report = await analyzer.analyze_instances()
        
        assert report["total_instances"] == 2
        assert report["already_graviton"] == 1
        assert report["migration_candidates"] == 1
        
        candidate = report["candidates"][0]
        assert candidate["instance_id"] == "i-123"
        assert candidate["recommended_type"] == "m7g.large"
        assert candidate["energy_savings_percent"] == 40
