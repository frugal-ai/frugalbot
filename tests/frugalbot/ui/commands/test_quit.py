from unittest.mock import Mock

import pytest
import typer
from pytest_mock import MockerFixture

from frugalbot.ui.commands.quit import cmd_quit


@pytest.fixture
def mock_app() -> Mock:
    """Creates a mock Tui app."""
    return Mock()


@pytest.fixture
def mock_ctx(mock_app: Mock, mocker: MockerFixture) -> Mock:
    """Creates a mock typer.Context with app set in obj."""
    ctx = mocker.MagicMock(spec=typer.Context)
    ctx.obj = {"app": mock_app}
    return ctx


# --- Tests for autocomplete_path_worker.cancel exit point (third-party interaction) ---


def test_cmd_quit_with_autocomplete_path_worker_calls_cancel(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given
    mock_app.autocomplete_path_worker = Mock()

    # When
    cmd_quit(mock_ctx)

    # Then
    mock_app.autocomplete_path_worker.cancel.assert_called_once()


def test_cmd_quit_without_autocomplete_path_worker_does_not_call_cancel(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given
    mock_app.autocomplete_path_worker = None

    # When
    cmd_quit(mock_ctx)

    # Then
    assert not hasattr(mock_app.autocomplete_path_worker, "cancel")


# --- Tests for autocomplete_path_query_event.set exit point (third-party interaction) ---


def test_cmd_quit_with_autocomplete_path_worker_calls_query_event_set(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given

    # When
    cmd_quit(mock_ctx)

    # Then
    mock_app.autocomplete_path_query_event.set.assert_called_once()


def test_cmd_quit_without_autocomplete_path_worker_calls_query_event_set(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given
    mock_app.autocomplete_path_worker = None

    # When
    cmd_quit(mock_ctx)

    # Then
    mock_app.autocomplete_path_query_event.set.assert_called_once()


# --- Tests for app.exit exit point (third-party interaction) ---


def test_cmd_quit_with_autocomplete_path_worker_calls_exit(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given

    # When
    cmd_quit(mock_ctx)

    # Then
    mock_app.exit.assert_called_once()


def test_cmd_quit_without_autocomplete_path_worker_calls_exit(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given
    mock_app.autocomplete_path_worker = None

    # When
    cmd_quit(mock_ctx)

    # Then
    mock_app.exit.assert_called_once()
