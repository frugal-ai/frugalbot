from unittest.mock import AsyncMock, patch

import orjson as json
import pytest
from any_llm.types.completion import ChatCompletionMessageFunctionToolCall

from frugalbot.clients.manual import ManualClient, ManualClientConfig, parse_assistant_message
from frugalbot.conversation import Conversation
from frugalbot.events import QuestionResponse
from frugalbot.hooks.base import Hooks
from frugalbot.tools.base import Tools


@pytest.fixture
def client() -> ManualClient:
    return ManualClient(ManualClientConfig(name="test"))


@pytest.fixture
async def conversation() -> Conversation:
    hooks = Hooks()
    conv = Conversation(hooks)
    await conv.append_system_message("System Prompt")
    await conv.append_user_message("User Prompt")
    return conv


@pytest.fixture
def tools() -> Tools:
    return Tools()


def test_parse_assistant_message_with_json_returns_structured_message() -> None:
    # Given
    response = """powershell
    {
        "command": "Get-Process"\n
    }"""

    # When
    message = parse_assistant_message(response)

    # Then
    assert message.tool_calls is not None
    tool_call = message.tool_calls[0]
    assert isinstance(tool_call, ChatCompletionMessageFunctionToolCall)
    assert json.loads(tool_call.function.arguments)["command"] == "Get-Process"


def test_parse_assistant_message_with_plain_text_returns_plain_message() -> None:
    # Given
    response = "Hello there!"

    # When
    message = parse_assistant_message(response)

    # Then
    assert message.content == response


def test_parse_assistant_message_with_invalid_json_returns_plain_message() -> None:
    # Given
    response = '{"command": "incomplete'

    # When
    message = parse_assistant_message(response)

    # Then
    assert message.content == response


async def test_initialize_conversation_without_system_prompt_support_copies_combined_prompt(client, conversation, tools) -> None:
    # Given
    responses = [QuestionResponse.NO, QuestionResponse.NO, QuestionResponse.OK]

    async def mock_emit_fn(event):
        event.future.set_result(responses.pop(0))

    # When
    with (
        patch("frugalbot.clients.manual.bus.emit_and_handle", side_effect=mock_emit_fn),
        patch("frugalbot.clients.manual.pyperclip.copy") as mock_copy,
    ):
        await client._initialize_conversation(conversation, tools)

        # Then
        mock_copy.assert_called_once_with("System Prompt\n\nUser Prompt")


async def test_initialize_conversation_with_system_prompt_support_copies_separate_prompts(client, conversation, tools) -> None:
    # Given
    # 1. Tools schema? YES -> Copy tools -> OK
    # 2. System prompt? YES -> Copy system -> OK
    # 3. Initial prompt? Copy initial -> OK
    responses = [QuestionResponse.YES, QuestionResponse.OK, QuestionResponse.YES, QuestionResponse.OK, QuestionResponse.OK]

    async def mock_emit_fn(event):
        event.future.set_result(responses.pop(0))

    # When
    with (
        patch("frugalbot.clients.manual.bus.emit_and_handle", side_effect=mock_emit_fn),
        patch("frugalbot.clients.manual.pyperclip.copy") as mock_copy,
    ):
        await client._initialize_conversation(conversation, tools)

        # Then
        assert mock_copy.call_count == 3


async def test_initialize_conversation_with_too_few_messages_raises_value_error(client, tools) -> None:
    # Given
    hooks = Hooks()
    conversation = Conversation(hooks)
    await conversation.append_system_message("S")

    # When & Then
    with pytest.raises(ValueError, match="Conversation must have at least 2 messages to initialize"):
        await client._initialize_conversation(conversation, tools)


async def test_call_when_uninitialized_initializes_and_returns_response(client, conversation, tools) -> None:
    # Given
    responses = ["User response"]

    async def mock_emit_fn(event):
        event.future.set_result(responses.pop(0))

    # When
    with (
        patch.object(ManualClient, "_initialize_conversation", new_callable=AsyncMock) as mock_init,
        patch("frugalbot.clients.manual.bus.emit_and_handle", side_effect=mock_emit_fn),
    ):
        result = await client.call(conversation, tools)

        # Then
        assert result.choices[0].message.content == "User response"
        mock_init.assert_called_once_with(conversation, tools)


async def test_call_when_initialized_returns_response_without_initialization(client, conversation, tools) -> None:
    # Given
    client._initialized = True
    # 1. OK for tool response copy
    # 2. Assistant response
    responses = [QuestionResponse.OK, "User response"]

    async def mock_emit_fn(event):
        event.future.set_result(responses.pop(0))

    # When
    with (
        patch.object(ManualClient, "_initialize_conversation", new_callable=AsyncMock) as mock_init,
        patch("frugalbot.clients.manual.bus.emit_and_handle", side_effect=mock_emit_fn),
    ):
        result = await client.call(conversation, tools)

        # Then
        assert result.choices[0].message.content == "User response"
        mock_init.assert_not_called()
