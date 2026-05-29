from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
import typer

from frugalbot.agent import Agent
from frugalbot.agents import Agents
from frugalbot.config import ThinkingLevel
from frugalbot.ui.commands.thinking import _cmd_thinking_impl, cmd_thinking
from frugalbot.ui.tui import Tui


@pytest.fixture
def mock_agent() -> AsyncMock:
    agent = AsyncMock(spec=Agent)
    agent.name = "one"
    return agent


@pytest.fixture
def mock_agent2() -> AsyncMock:
    agent = AsyncMock(spec=Agent)
    agent.name = "two"
    return agent


@pytest.fixture
def mock_app(mock_agent, mock_agent2) -> Mock:
    """Creates a mock Tui app."""
    app = Mock(spec=Tui)
    app.agent = mock_agent
    app.agents = Mock(spec=Agents)
    app.agents.get_all.return_value = [mock_agent, mock_agent2]
    return app


@pytest.fixture
def mock_ctx(mock_app: Mock) -> Mock:
    """Creates a mock typer.Context with app set in obj."""
    ctx = Mock(spec=typer.Context)
    ctx.obj = {"app": mock_app}
    return ctx


async def test_cmd_thinking_calls_app_run_worker(mock_ctx: Mock, mock_app: Mock) -> None:
    # When
    cmd_thinking(mock_ctx, "MEDIUM")

    # Then
    mock_app.run_worker.assert_called_once()
    await mock_app.run_worker.call_args[0][0]


@pytest.mark.parametrize("level", ["NONE", "LOW", "MEDIUM", "HIGH"])
async def test_cmd_thinking_calls_set_thinking_on_all_agents_and_calls_notify(
    mock_agent: AsyncMock,
    mock_agent2: AsyncMock,
    mock_app: Mock,
    level: str,
) -> None:
    # When
    await _cmd_thinking_impl(mock_app, cast(ThinkingLevel, level))

    # Then
    mock_agent.set_thinking_level.assert_called_once_with(level, emit_status_update=True)
    mock_agent2.set_thinking_level.assert_called_once_with(level, emit_status_update=False)
    mock_app.notify.assert_called_once_with(f"Thinking level set to {level}")
