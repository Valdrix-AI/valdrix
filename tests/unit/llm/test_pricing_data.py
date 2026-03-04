from unittest.mock import AsyncMock, patch

import pytest

from app.shared.llm.pricing_data import refresh_llm_pricing


@pytest.mark.asyncio
async def test_refresh_llm_pricing_handles_recoverable_db_errors() -> None:
    db = AsyncMock()
    db.execute.side_effect = RuntimeError("db unavailable")

    with patch("app.shared.llm.pricing_data.logger") as logger_mock:
        await refresh_llm_pricing(db)

    logger_mock.error.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_llm_pricing_does_not_swallow_fatal_errors() -> None:
    db = AsyncMock()
    db.execute.side_effect = KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        await refresh_llm_pricing(db)
