from unittest.mock import MagicMock, Mock

import pytest
import typer
from pytest_mock import MockerFixture

from frugalbot.ui.commands.copy import cmd_copy


@pytest.fixture
def mock_app() -> Mock:
    """Creates a mock Tui app with agent and conversation configured."""
    app = Mock()
    app.agent = Mock()
    app.agent.conversation = Mock()
    return app


@pytest.fixture
def mock_ctx(mock_app: Mock) -> MagicMock:
    """Creates a mock typer.Context with app set in obj."""
    ctx = MagicMock(spec=typer.Context)
    ctx.obj = {"app": mock_app}
    return ctx


def test_cmd_copy_with_valid_conversation_copies_text_to_clipboard(
    mock_ctx: MagicMock,
    mock_app: Mock,
    mocker: MockerFixture,
) -> None:
    # Given
    expected_text = "User: Hello\nAssistant: Hi there!"
    mock_app.agent.conversation.convert_into_web_chat_prompt.return_value = expected_text
    mock_pyperclip = mocker.patch("frugalbot.ui.commands.copy.pyperclip")

    # When
    cmd_copy(mock_ctx)

    # Then
    mock_pyperclip.copy.assert_called_once_with(expected_text)


def test_cmd_copy_with_valid_conversation_notifies_user(
    mock_ctx: MagicMock,
    mock_app: Mock,
    mocker: MockerFixture,
) -> None:
    # Given
    mock_app.agent.conversation.convert_into_web_chat_prompt.return_value = "Some text"
    mocker.patch("frugalbot.ui.commands.copy.pyperclip")

    # When
    cmd_copy(mock_ctx)

    # Then
    mock_app.notify.assert_called_once_with("Conversation copied to clipboard!")


def test_cmd_copy_with_empty_conversation_copies_empty_string_to_clipboard(
    mock_ctx: MagicMock,
    mock_app: Mock,
    mocker: MockerFixture,
) -> None:
    # Given
    mock_app.agent.conversation.convert_into_web_chat_prompt.return_value = ""
    mock_pyperclip = mocker.patch("frugalbot.ui.commands.copy.pyperclip")

    # When
    cmd_copy(mock_ctx)

    # Then
    mock_pyperclip.copy.assert_called_once_with("")


def test_cmd_copy_with_multiline_text_copies_full_text_to_clipboard(
    mock_ctx: MagicMock,
    mock_app: Mock,
    mocker: MockerFixture,
) -> None:
    # Given
    multiline_text = "User: Line 1\nLine 2\nLine 3\n\nAssistant: Response"
    mock_app.agent.conversation.convert_into_web_chat_prompt.return_value = multiline_text
    mock_pyperclip = mocker.patch("frugalbot.ui.commands.copy.pyperclip")

    # When
    cmd_copy(mock_ctx)

    # Then
    mock_pyperclip.copy.assert_called_once_with(multiline_text)


def test_cmd_copy_with_long_conversation_copies_full_text(
    mock_ctx: MagicMock,
    mock_app: Mock,
    mocker: MockerFixture,
) -> None:
    # Given
    long_text = "Message\n" * 1000
    mock_app.agent.conversation.convert_into_web_chat_prompt.return_value = long_text
    mock_pyperclip = mocker.patch("frugalbot.ui.commands.copy.pyperclip")

    # When
    cmd_copy(mock_ctx)

    # Then
    mock_pyperclip.copy.assert_called_once_with(long_text)
