from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
import typer
from pytest_mock import MockerFixture
from textual.worker import WorkerState

from frugalbot.ui.commands.reload import _cmd_reload_impl, cmd_reload


@pytest.fixture
def mock_app() -> Mock:
    """Creates a mock Tui app with agent configured."""
    app = Mock()
    app.agent = Mock()
    app.agent.conversation = Mock()
    app.agent.conversation.messages = MagicMock()
    app.agent.conversation_file_path = Mock()
    app.agent.new_conversation = AsyncMock()
    app.agent.load_conversation_from_file = AsyncMock()
    app.agents = Mock()
    app.agents.reload = AsyncMock()
    return app


@pytest.fixture
def mock_ctx(mock_app: Mock) -> MagicMock:
    """Creates a mock typer.Context with app set in obj."""
    ctx = MagicMock(spec=typer.Context)
    ctx.obj = {"app": mock_app}
    return ctx


# --- Tests for early exit when agent is running (RUNNING state) ---


def test_cmd_reload_with_agent_running_notifies_cannot_reload(
    mock_ctx: MagicMock,
    mock_app: Mock,
) -> None:
    # Given
    mock_app.agent_worker = Mock()
    mock_app.agent_worker.state = WorkerState.RUNNING

    # When
    cmd_reload(mock_ctx)

    # Then
    mock_app.notify.assert_called_once_with("Cannot reload while agent is running. Wait for it to finish or ctrl+a to stop agent.")


def test_cmd_reload_with_agent_running_does_not_run_worker(
    mock_ctx: MagicMock,
    mock_app: Mock,
) -> None:
    # Given
    mock_app.agent_worker = Mock()
    mock_app.agent_worker.state = WorkerState.RUNNING

    # When
    cmd_reload(mock_ctx)

    # Then
    mock_app.run_worker.assert_not_called()


# --- Tests for early exit when agent is pending (PENDING state) ---


def test_cmd_reload_with_agent_pending_notifies_cannot_reload(
    mock_ctx: MagicMock,
    mock_app: Mock,
) -> None:
    # Given
    mock_app.agent_worker = Mock()
    mock_app.agent_worker.state = WorkerState.PENDING

    # When
    cmd_reload(mock_ctx)

    # Then
    mock_app.notify.assert_called_once_with("Cannot reload while agent is running. Wait for it to finish or ctrl+a to stop agent.")


def test_cmd_reload_with_agent_pending_does_not_run_worker(
    mock_ctx: MagicMock,
    mock_app: Mock,
) -> None:
    # Given
    mock_app.agent_worker = Mock()
    mock_app.agent_worker.state = WorkerState.PENDING

    # When
    cmd_reload(mock_ctx)

    # Then
    mock_app.run_worker.assert_not_called()


# --- Tests for successful reload when agent is not running ---


def test_cmd_reload_with_agent_not_running_runs_worker(
    mock_ctx: MagicMock,
    mock_app: Mock,
) -> None:
    # Given
    mock_app.agent_worker = None

    # When
    cmd_reload(mock_ctx)

    # Then
    mock_app.run_worker.assert_called_once()
    mock_app.run_worker.call_args[0][0].close()


# --- Tests for agent worker in non-running states (e.g. SUCCESS, CANCELLED, ERROR) ---


def test_cmd_reload_with_agent_success_proceeds_with_reload(
    mock_ctx: MagicMock,
    mock_app: Mock,
) -> None:
    # Given
    mock_app.agent_worker = Mock()
    mock_app.agent_worker.state = WorkerState.SUCCESS

    # When
    cmd_reload(mock_ctx)

    # Then
    mock_app.run_worker.assert_called_once()
    mock_app.run_worker.call_args[0][0].close()


def test_cmd_reload_with_agent_cancelled_proceeds_with_reload(
    mock_ctx: MagicMock,
    mock_app: Mock,
) -> None:
    # Given
    mock_app.agent_worker = Mock()
    mock_app.agent_worker.state = WorkerState.CANCELLED

    # When
    cmd_reload(mock_ctx)

    # Then
    mock_app.run_worker.assert_called_once()
    mock_app.run_worker.call_args[0][0].close()


def test_cmd_reload_with_agent_failed_proceeds_with_reload(
    mock_ctx: MagicMock,
    mock_app: Mock,
) -> None:
    # Given
    mock_app.agent_worker = Mock()
    mock_app.agent_worker.state = WorkerState.ERROR

    # When
    cmd_reload(mock_ctx)

    # Then
    mock_app.run_worker.assert_called_once()
    mock_app.run_worker.call_args[0][0].close()


# --- Tests for _cmd_reload_impl behavior ---


@pytest.mark.asyncio
async def test_impl_clears_subscribers(
    mock_app: Mock,
    mocker: MockerFixture,
) -> None:
    # Given
    mock_bus = mocker.patch("frugalbot.ui.commands.reload.bus")

    # When
    await _cmd_reload_impl(mock_app)

    # Then
    mock_bus.clear_subscribers.assert_called_once()


@pytest.mark.asyncio
async def test_impl_calls_unload_commands(
    mock_app: Mock,
    mocker: MockerFixture,
) -> None:
    # Given
    mocker.patch("frugalbot.ui.commands.reload.bus")
    mock_unload_commands = mocker.patch("frugalbot.ui.commands.reload.unload_commands")

    # When
    await _cmd_reload_impl(mock_app)

    # Then
    mock_unload_commands.assert_called_once()


@pytest.mark.asyncio
async def test_impl_calls_agents_reload(
    mock_app: Mock,
    mocker: MockerFixture,
) -> None:
    # Given
    mocker.patch("frugalbot.ui.commands.reload.bus")
    mocker.patch("frugalbot.ui.commands.reload.unload_commands")
    mock_agents_reload = mocker.patch.object(mock_app.agents, "reload")

    # When
    await _cmd_reload_impl(mock_app)

    # Then
    mock_agents_reload.assert_called_once()


@pytest.mark.asyncio
async def test_impl_sets_initialized_false(
    mock_app: Mock,
    mocker: MockerFixture,
) -> None:
    # Given
    mocker.patch("frugalbot.ui.commands.reload.bus")
    mocker.patch("frugalbot.ui.commands.reload.unload_commands")

    # When
    await _cmd_reload_impl(mock_app)

    # Then
    assert mock_app.initialized is False


@pytest.mark.asyncio
async def test_impl_calls_init_with_agents(
    mock_app: Mock,
    mocker: MockerFixture,
) -> None:
    # Given
    mocker.patch("frugalbot.ui.commands.reload.bus")
    mocker.patch("frugalbot.ui.commands.reload.unload_commands")

    # When
    await _cmd_reload_impl(mock_app)

    # Then
    mock_app.init.assert_called_once_with(mock_app.agents)


@pytest.mark.asyncio
async def test_impl_calls_agent_new_conversation(
    mock_app: Mock,
    mocker: MockerFixture,
) -> None:
    # Given
    mocker.patch("frugalbot.ui.commands.reload.bus")
    mocker.patch("frugalbot.ui.commands.reload.unload_commands")
    mock_new_conversation = mocker.patch.object(mock_app.agent, "new_conversation")

    # When
    await _cmd_reload_impl(mock_app)

    # Then
    mock_new_conversation.assert_called_once()


@pytest.mark.asyncio
async def test_impl_notifies_successful(
    mock_app: Mock,
    mocker: MockerFixture,
) -> None:
    # Given
    mocker.patch("frugalbot.ui.commands.reload.bus")
    mocker.patch("frugalbot.ui.commands.reload.unload_commands")

    # When
    await _cmd_reload_impl(mock_app)

    # Then
    mock_app.notify.assert_called_once_with("Reload successful.")
