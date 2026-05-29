from unittest.mock import Mock

import pytest
import typer
from pytest_mock import MockerFixture

from frugalbot.ui.commands.help import _HELP_CONTENT, cmd_help
from frugalbot.ui.screens.help import HelpScreen


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


# --- Tests for app.call_after_refresh exit point (third-party interaction) ---


def test_cmd_help_with_valid_context_calls_call_after_refresh(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given

    # When
    cmd_help(mock_ctx)

    # Then
    mock_app.call_after_refresh.assert_called_once()


def test_cmd_help_with_valid_context_passes_push_screen_as_first_argument(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given

    # When
    cmd_help(mock_ctx)

    # Then
    call_args = mock_app.call_after_refresh.call_args
    assert call_args[0][0] == mock_app.push_screen


def test_cmd_help_with_valid_context_passes_help_screen_as_second_argument(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given

    # When
    cmd_help(mock_ctx)

    # Then
    call_args = mock_app.call_after_refresh.call_args
    assert isinstance(call_args[0][1], HelpScreen)


# --- Tests for HelpScreen content exit point (state change) ---


def test_cmd_help_with_valid_context_screen_content_starts_with_help_content(
    mock_ctx: Mock,
) -> None:
    # Given

    # When
    cmd_help(mock_ctx)

    # Then
    call_args = mock_ctx.obj["app"].call_after_refresh.call_args
    help_screen: HelpScreen = call_args[0][1]
    assert help_screen.content.startswith(_HELP_CONTENT)


@pytest.mark.parametrize(
    "expected_description",
    [
        "Submit",
        "Scroll Output Up",
        "Scroll Output Down",
        "Scroll Output Home",
        "Scroll Output End",
        "Enable / Disable Auto-Scrolling",
        "Search History",
        "Cancel Agent",
        "Cycle Between Configured Providers / Models",
    ],
)
def test_cmd_help_with_valid_context_screen_content_contains_binding_description(
    mock_ctx: Mock,
    expected_description: str,
) -> None:
    # Given

    # When
    cmd_help(mock_ctx)

    # Then
    call_args = mock_ctx.obj["app"].call_after_refresh.call_args
    help_screen: HelpScreen = call_args[0][1]
    assert expected_description in help_screen.content


@pytest.mark.parametrize(
    "expected_shortcut",
    [
        "`alt+enter`",
        "`alt+u or alt+up`",
        "`alt+d or alt+down`",
        "`alt+h or alt+home`",
        "`alt+e or alt+end`",
        "`alt+s`",
        "`ctrl+r`",
        "`ctrl+a`",
        "`alt+p or ctrl+p`",
    ],
)
def test_cmd_help_with_valid_context_screen_content_contains_binding_shortcut(
    mock_ctx: Mock,
    expected_shortcut: str,
) -> None:
    # Given

    # When
    cmd_help(mock_ctx)

    # Then
    call_args = mock_ctx.obj["app"].call_after_refresh.call_args
    help_screen: HelpScreen = call_args[0][1]
    assert expected_shortcut in help_screen.content


def test_cmd_help_with_valid_context_screen_content_contains_navigation_section(
    mock_ctx: Mock,
) -> None:
    # Given

    # When
    cmd_help(mock_ctx)

    # Then
    call_args = mock_ctx.obj["app"].call_after_refresh.call_args
    help_screen: HelpScreen = call_args[0][1]
    assert "## Navigation & Interaction" in help_screen.content


def test_cmd_help_with_valid_context_screen_content_contains_autocomplete_hint(
    mock_ctx: Mock,
) -> None:
    # Given

    # When
    cmd_help(mock_ctx)

    # Then
    call_args = mock_ctx.obj["app"].call_after_refresh.call_args
    help_screen: HelpScreen = call_args[0][1]
    assert "Type `/` to open the command autocomplete menu" in help_screen.content


def test_cmd_help_with_valid_context_screen_content_contains_keyboard_shortcuts_header(
    mock_ctx: Mock,
) -> None:
    # Given

    # When
    cmd_help(mock_ctx)

    # Then
    call_args = mock_ctx.obj["app"].call_after_refresh.call_args
    help_screen: HelpScreen = call_args[0][1]
    assert "## Keyboard Shortcuts" in help_screen.content


def test_cmd_help_with_valid_context_screen_content_contains_table_header(
    mock_ctx: Mock,
) -> None:
    # Given

    # When
    cmd_help(mock_ctx)

    # Then
    call_args = mock_ctx.obj["app"].call_after_refresh.call_args
    help_screen: HelpScreen = call_args[0][1]
    assert "| Shortcut | Description |" in help_screen.content


def test_cmd_help_with_valid_context_screen_content_formats_submit_as_table_row(
    mock_ctx: Mock,
) -> None:
    # Given

    # When
    cmd_help(mock_ctx)

    # Then
    call_args = mock_ctx.obj["app"].call_after_refresh.call_args
    help_screen: HelpScreen = call_args[0][1]
    assert "| `alt+enter` | Submit |" in help_screen.content


def test_cmd_help_with_valid_context_screen_content_formats_search_history_as_table_row(
    mock_ctx: Mock,
) -> None:
    # Given

    # When
    cmd_help(mock_ctx)

    # Then
    call_args = mock_ctx.obj["app"].call_after_refresh.call_args
    help_screen: HelpScreen = call_args[0][1]
    assert "| `ctrl+r` | Search History |" in help_screen.content
