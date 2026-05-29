from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
import typer
from pyfakefs.fake_filesystem import FakeFilesystem

from frugalbot.ui.commands.load import cmd_load


@pytest.fixture
def mock_app() -> Mock:
    """Creates a mock Tui app with agent and output configured."""
    app = Mock()
    app.agent = Mock()
    app.output = Mock()
    return app


@pytest.fixture
def mock_ctx(mock_app: Mock) -> MagicMock:
    """Creates a mock typer.Context with app set in obj."""
    ctx = MagicMock(spec=typer.Context)
    ctx.obj = {"app": mock_app}
    return ctx


@pytest.fixture
def session_file(fs: FakeFilesystem) -> Path:
    """Creates a fake JSON session file and returns its path."""
    file_path = Path("/fake/sessions/test_session.json")
    fs.create_file(str(file_path), contents="[]")
    return file_path


# --- Tests for app.output.remove_children exit point (third-party interaction) ---


def test_cmd_load_with_valid_file_removes_output_children(
    mock_ctx: MagicMock,
    mock_app: Mock,
    session_file: Path,
) -> None:
    # Given

    # When
    cmd_load(mock_ctx, session_file)

    # Then
    mock_app.output.remove_children.assert_called_once()


# --- Tests for app.run_worker exit point (third-party interaction) ---


def test_cmd_load_with_valid_file_calls_run_worker_once(
    mock_ctx: MagicMock,
    mock_app: Mock,
    session_file: Path,
) -> None:
    # Given

    # When
    cmd_load(mock_ctx, session_file)

    # Then
    mock_app.run_worker.assert_called_once()


def test_cmd_load_with_valid_file_passes_load_conversation_result_to_run_worker(
    mock_ctx: MagicMock,
    mock_app: Mock,
    session_file: Path,
) -> None:
    # Given
    expected_coro = mock_app.agent.load_conversation_from_file.return_value

    # When
    cmd_load(mock_ctx, session_file)

    # Then
    call_args = mock_app.run_worker.call_args
    assert call_args[0][0] == expected_coro


def test_cmd_load_with_valid_file_passes_load_conversation_name_to_run_worker(
    mock_ctx: MagicMock,
    mock_app: Mock,
    session_file: Path,
) -> None:
    # Given

    # When
    cmd_load(mock_ctx, session_file)

    # Then
    call_args = mock_app.run_worker.call_args
    assert call_args[1]["name"] == "load_conversation"


def test_cmd_load_with_valid_file_calls_load_conversation_from_file_with_path(
    mock_ctx: MagicMock,
    mock_app: Mock,
    session_file: Path,
) -> None:
    # Given

    # When
    cmd_load(mock_ctx, session_file)

    # Then
    mock_app.agent.load_conversation_from_file.assert_called_once_with(session_file)


def test_cmd_load_with_different_file_path_passes_correct_path_to_agent(
    mock_ctx: MagicMock,
    mock_app: Mock,
    fs: FakeFilesystem,
) -> None:
    # Given
    file_path = Path("/fake/other/deep/session.json")
    fs.create_file(str(file_path), contents="[]")

    # When
    cmd_load(mock_ctx, file_path)

    # Then
    mock_app.agent.load_conversation_from_file.assert_called_once_with(file_path)


# --- Tests for call ordering ---


def test_cmd_load_with_valid_file_removes_children_before_running_worker(
    mock_ctx: MagicMock,
    mock_app: Mock,
    session_file: Path,
) -> None:
    # Given

    # When
    cmd_load(mock_ctx, session_file)

    # Then
    assert mock_app.mock_calls[0][0] == "output.remove_children"
    assert mock_app.mock_calls[1][0] == "agent.load_conversation_from_file"
    assert mock_app.mock_calls[2][0] == "run_worker"
