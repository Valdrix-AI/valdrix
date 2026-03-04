from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from scripts import db_diagnostics


@pytest.mark.asyncio
async def test_run_command_dispatches_ping_and_disposes_engine() -> None:
    engine = SimpleNamespace(dispose=AsyncMock())
    expected = db_diagnostics.CommandResult(name="ping", payload={"ok": True})

    with (
        patch("scripts.db_diagnostics._build_engine", return_value=engine),
        patch("scripts.db_diagnostics._run_ping", new=AsyncMock(return_value=expected)) as run_ping,
    ):
        result = await db_diagnostics.run_command("ping")

    assert result == expected
    run_ping.assert_awaited_once_with(engine)
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_command_rejects_unknown_command_and_disposes_engine() -> None:
    engine = SimpleNamespace(dispose=AsyncMock())
    with patch("scripts.db_diagnostics._build_engine", return_value=engine):
        with pytest.raises(ValueError, match="Unsupported command: unknown"):
            await db_diagnostics.run_command("unknown")
    engine.dispose.assert_awaited_once()


def test_main_executes_selected_command_and_prints_payload(capsys: pytest.CaptureFixture[str]) -> None:
    expected = db_diagnostics.CommandResult(name="tables", payload={"count": 2})
    with patch(
        "scripts.db_diagnostics.run_command",
        new=AsyncMock(return_value=expected),
    ) as run_command:
        exit_code = db_diagnostics.main(["tables"])

    assert exit_code == 0
    run_command.assert_awaited_once_with("tables")
    assert capsys.readouterr().out.strip() == "{'count': 2}"
