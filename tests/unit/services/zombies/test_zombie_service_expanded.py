import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from app.modules.optimization.domain.service import ZombieService

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def zombie_service(mock_db):
    return ZombieService(mock_db)

class TestZombieServiceExpanded:
    @pytest.mark.asyncio
    async def test_scan_for_tenant_no_connections(self, zombie_service, mock_db):
        """Test that scan returns empty results when no cloud connections exist."""
        tenant_id = uuid4()
        user = MagicMock()
        user.tier = "starter"
        
        with patch("app.modules.optimization.domain.service.select") as _:
            mock_conn_res = MagicMock()
            mock_conn_res.scalars.return_value.all.return_value = []
            mock_db.execute.return_value = mock_conn_res
            
            result = await zombie_service.scan_for_tenant(tenant_id, user, analyze=False)
            # Should return empty results with no errors
            assert result is not None

    @pytest.mark.asyncio
    async def test_send_notifications_failure(self, zombie_service):
        """Test that notification failures don't crash the service."""
        zombies = {"total_monthly_waste": 100.0}
        with patch("app.modules.notifications.domain.get_slack_service") as mock_get_slack:
            mock_slack = AsyncMock()
            mock_slack.notify_zombies.side_effect = Exception("Slack Down")
            mock_get_slack.return_value = mock_slack
            
            # Should not raise exception
            await zombie_service._send_notifications(zombies)

