import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.optimization.adapters.saas.plugins.api import GitHubUnusedSeatPlugin


@pytest.mark.asyncio
async def test_github_unused_seat_plugin():
    """
    Verify detecting inactive GitHub seats via canonical SaaS connector config.
    """
    plugin = GitHubUnusedSeatPlugin()
    assert plugin.category_key == "unused_license_seats"

    now = datetime.now(timezone.utc)
    mock_members = [
        {
            "login": "active-user",
            "last_activity": (now - timedelta(days=5)).isoformat(),
        },
        {
            "login": "inactive-user",
            "last_activity": (now - timedelta(days=45)).isoformat(),
        },
    ]

    mock_client_ctx = AsyncMock()
    mock_client = AsyncMock()
    mock_client_ctx.__aenter__.return_value = mock_client
    mock_client.get.return_value = MagicMock(
        status_code=200,
        json=lambda: mock_members,
    )

    with patch("httpx.AsyncClient", return_value=mock_client_ctx):
        zombies = await plugin.scan(
            session=None,
            region="global",
            credentials={"api_key": "ghp_fake_token"},
            config={"github_org": "my-org", "unused_threshold_days": 30},
        )

    assert len(zombies) == 1
    assert zombies[0]["resource_id"] == "inactive-user"
    assert zombies[0]["action"] == "revoke_github_seat"
