"""Tests for frugalbot/tool_caller.py"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from any_llm.types.completion import ChatCompletionMessageFunctionToolCall, Function
from jsonschema import ValidationError as JsonSchemaValidationError
from pydantic import BaseModel

from frugalbot.config import ToolOutputFormat
from frugalbot.conversation import Conversation
from frugalbot.events import (
    MessageEvent,
    MessageMarkup,
    MessageType,
)
from frugalbot.hooks.base import ApprovalState, Hooks, PostToolCallHook, PreToolCallHook
from frugalbot.tool_caller import ToolCaller
from frugalbot.tools.base import Tools


class FakeToolResult(BaseModel):
    """A fake tool result for testing."""

    output: str


# --- Helpers -------------------------------------------------------------------


def _make_tool_call(
    *,
    tool_call_id: str = "tc_001",
    tool_name: str = "test_tool",
    arguments: str = '{"param": "value"}',
    extra_content: dict[str, Any] | None = None,
) -> ChatCompletionMessageFunctionToolCall:
    """Create a ChatCompletionMessageFunctionToolCall for testing."""
    tc = ChatCompletionMessageFunctionToolCall(
        id=tool_call_id,
        type="function",
        function=Function(name=tool_name, arguments=arguments),
    )
    if extra_content is not None:
        object.__setattr__(tc, "extra_content", extra_content)
    return tc


def _make_hooks() -> Hooks:
    """Create an empty Hooks instance."""
    return Hooks()


def _make_tools(mock_tool: AsyncMock | None = None) -> Tools:
    """Create a Tools instance with a mock test_tool registered."""
    tools = Tools()
    if mock_tool is None:
        tool = AsyncMock()
        tool.run.return_value = FakeToolResult(output="success")
        tool.validate_args = MagicMock()
        mock_tool = tool
    tools._tools_registry["test_tool"] = mock_tool
    return tools


def _make_caller(
    *,
    conversation: Conversation | None = None,
    tool_call: ChatCompletionMessageFunctionToolCall | None = None,
    hooks: Hooks | None = None,
    tools: Tools | None = None,
    tool_output_format: ToolOutputFormat = "yaml",
) -> ToolCaller:
    """Create a ToolCaller with sensible defaults."""
    if hooks is None:
        hooks = _make_hooks()
    if conversation is None:
        conversation = Conversation(hooks=hooks)
    if tool_call is None:
        tool_call = _make_tool_call()
    if tools is None:
        tools = _make_tools()
    return ToolCaller(
        conversation=conversation,
        hooks=hooks,
        tools=tools,
        tool_call=tool_call,
        tool_output_format=tool_output_format,
    )


# --- Fixtures ------------------------------------------------------------------


@pytest.fixture
def hooks() -> Hooks:
    return _make_hooks()


@pytest.fixture
def conversation(hooks: Hooks) -> Conversation:
    return Conversation(hooks=hooks)


@pytest.fixture
def tool_call() -> ChatCompletionMessageFunctionToolCall:
    return _make_tool_call()


@pytest.fixture
def mock_tool() -> AsyncMock:
    tool = AsyncMock()
    tool.run.return_value = FakeToolResult(output="success")
    tool.validate_args = MagicMock()
    return tool


@pytest.fixture
def tools(mock_tool: AsyncMock) -> Tools:
    return _make_tools(mock_tool)


@pytest.fixture
def mock_bus():
    with patch("frugalbot.tool_caller.bus", new_callable=AsyncMock) as mock:
        yield mock


# --- Tests for __init__ --------------------------------------------------------


def test_init_with_valid_arguments_stores_values() -> None:
    # Given
    hooks = _make_hooks()
    conversation = Conversation(hooks=hooks)
    tc = _make_tool_call()
    tools = _make_tools()

    # When
    caller = _make_caller(conversation=conversation, tool_call=tc, hooks=hooks, tools=tools, tool_output_format="yaml")

    # Then
    assert caller.conversation is conversation
    assert caller.hooks is hooks
    assert caller.tools is tools
    assert caller.tool_call is tc
    assert caller.tool_output_format == "yaml"
    assert caller.raw_args_str == '{"param": "value"}'


# --- Tests for call() - Approved state -----------------------------------------


async def test_call_with_approved_state_returns_none(
    conversation: Conversation,
    tool_call: ChatCompletionMessageFunctionToolCall,
    hooks: Hooks,
    tools: Tools,
    mock_bus: MagicMock,
) -> None:
    # Given
    caller = _make_caller(conversation=conversation, tool_call=tool_call, hooks=hooks, tools=tools)

    with patch.object(
        hooks,
        "run",
        new_callable=AsyncMock,
        side_effect=lambda hook_data: setattr(hook_data, "state", ApprovalState.APPROVED) if isinstance(hook_data, PreToolCallHook) else None,
    ):
        # When
        result = await caller.call()

    # Then
    assert result is None


async def test_call_with_approved_state_and_yaml_format_appends_yaml_content_to_conversation(
    conversation: Conversation,
    tool_call: ChatCompletionMessageFunctionToolCall,
    hooks: Hooks,
    tools: Tools,
    mock_bus: MagicMock,
) -> None:
    # Given
    caller = _make_caller(conversation=conversation, tool_call=tool_call, hooks=hooks, tools=tools, tool_output_format="yaml")

    async def approve_hook(hook_data: Any) -> None:
        if isinstance(hook_data, PreToolCallHook):
            hook_data.state = ApprovalState.APPROVED

    with patch.object(hooks, "run", new_callable=AsyncMock, side_effect=approve_hook):
        # When
        await caller.call()

    # Then
    assert len(conversation.messages) == 1
    msg = conversation.messages[0]
    assert isinstance(msg, dict)
    assert msg["role"] == "tool"
    assert msg["tool_call_id"] == "tc_001"
    assert msg["name"] == "test_tool"
    assert msg["content"] == "output: success"


async def test_call_with_approved_state_and_json_format_appends_json_content_to_conversation(
    conversation: Conversation,
    tool_call: ChatCompletionMessageFunctionToolCall,
    hooks: Hooks,
    tools: Tools,
    mock_bus: MagicMock,
) -> None:
    # Given
    caller = _make_caller(conversation=conversation, tool_call=tool_call, hooks=hooks, tools=tools, tool_output_format="json")

    async def approve_hook(hook_data: Any) -> None:
        if isinstance(hook_data, PreToolCallHook):
            hook_data.state = ApprovalState.APPROVED

    with patch.object(hooks, "run", new_callable=AsyncMock, side_effect=approve_hook):
        # When
        await caller.call()

    # Then
    assert len(conversation.messages) == 1
    msg = conversation.messages[0]
    assert isinstance(msg, dict)
    assert msg["role"] == "tool"
    assert msg["content"] == '{"output":"success"}'


async def test_call_with_approved_state_executes_tool_with_parsed_arguments(
    conversation: Conversation,
    tool_call: ChatCompletionMessageFunctionToolCall,
    hooks: Hooks,
    mock_tool: AsyncMock,
    mock_bus: MagicMock,
) -> None:
    # Given
    tools = _make_tools(mock_tool)
    caller = _make_caller(conversation=conversation, tool_call=tool_call, hooks=hooks, tools=tools)

    async def approve_hook(hook_data: Any) -> None:
        if isinstance(hook_data, PreToolCallHook):
            hook_data.state = ApprovalState.APPROVED

    with patch.object(hooks, "run", new_callable=AsyncMock, side_effect=approve_hook):
        # When
        await caller.call()

    # Then
    mock_tool.run.assert_called_once_with(param="value")


async def test_call_with_approved_state_runs_pre_tool_call_hook_with_correct_data(
    conversation: Conversation,
    tool_call: ChatCompletionMessageFunctionToolCall,
    hooks: Hooks,
    tools: Tools,
    mock_bus: MagicMock,
) -> None:
    # Given
    caller = _make_caller(conversation=conversation, tool_call=tool_call, hooks=hooks, tools=tools)

    async def approve_hook(hook_data: Any) -> None:
        if isinstance(hook_data, PreToolCallHook):
            hook_data.state = ApprovalState.APPROVED

    with patch.object(hooks, "run", new_callable=AsyncMock, side_effect=approve_hook) as mock_run:
        # When
        await caller.call()

    # Then
    pre_calls = [call for call in mock_run.call_args_list if isinstance(call.args[0], PreToolCallHook)]
    assert len(pre_calls) == 1
    pre_hook: PreToolCallHook = pre_calls[0].args[0]
    assert pre_hook.tool_name == "test_tool"
    assert pre_hook.arguments == {"param": "value"}


async def test_call_with_approved_state_runs_post_tool_call_hook_with_correct_data(
    conversation: Conversation,
    tool_call: ChatCompletionMessageFunctionToolCall,
    hooks: Hooks,
    tools: Tools,
    mock_bus: MagicMock,
) -> None:
    # Given
    caller = _make_caller(conversation=conversation, tool_call=tool_call, hooks=hooks, tools=tools)

    async def approve_hook(hook_data: Any) -> None:
        if isinstance(hook_data, PreToolCallHook):
            hook_data.state = ApprovalState.APPROVED

    with patch.object(hooks, "run", new_callable=AsyncMock, side_effect=approve_hook) as mock_run:
        # When
        await caller.call()

    # Then
    post_calls = [call for call in mock_run.call_args_list if isinstance(call.args[0], PostToolCallHook)]
    assert len(post_calls) == 1
    post_hook: PostToolCallHook = post_calls[0].args[0]
    assert post_hook.tool_name == "test_tool"
    assert post_hook.result_json == '{"output":"success"}'


# --- Tests for call() - Denied state -------------------------------------------


async def test_call_with_denied_state_and_reason_appends_refusal_with_reason_to_conversation(
    conversation: Conversation,
    tool_call: ChatCompletionMessageFunctionToolCall,
    hooks: Hooks,
    tools: Tools,
    mock_bus: MagicMock,
) -> None:
    # Given
    caller = _make_caller(conversation=conversation, tool_call=tool_call, hooks=hooks, tools=tools)

    async def deny_with_reason_hook(hook_data: Any) -> None:
        if isinstance(hook_data, PreToolCallHook):
            hook_data.state = ApprovalState.DENIED
            hook_data.denied_reason = "Too risky"

    with patch.object(hooks, "run", new_callable=AsyncMock, side_effect=deny_with_reason_hook):
        # When
        await caller.call()

    # Then
    assert len(conversation.messages) == 1
    msg = conversation.messages[0]
    assert isinstance(msg, dict)
    assert msg["role"] == "tool"
    assert msg["content"] == "The user refused to execute the tool call for the following reason: Too risky"


async def test_call_with_denied_state_without_reason_appends_generic_refusal_to_conversation(
    conversation: Conversation,
    tool_call: ChatCompletionMessageFunctionToolCall,
    hooks: Hooks,
    tools: Tools,
    mock_bus: MagicMock,
) -> None:
    # Given
    caller = _make_caller(conversation=conversation, tool_call=tool_call, hooks=hooks, tools=tools)

    async def deny_hook(hook_data: Any) -> None:
        if isinstance(hook_data, PreToolCallHook):
            hook_data.state = ApprovalState.DENIED

    with patch.object(hooks, "run", new_callable=AsyncMock, side_effect=deny_hook):
        # When
        await caller.call()

    # Then
    assert len(conversation.messages) == 1
    msg = conversation.messages[0]
    assert isinstance(msg, dict)
    assert msg["content"] == "The user refused to execute the tool call without providing a reason"


# --- Tests for call() - Not set state ------------------------------------------


async def test_call_with_not_set_state_appends_safety_message_to_conversation(
    conversation: Conversation,
    tool_call: ChatCompletionMessageFunctionToolCall,
    hooks: Hooks,
    tools: Tools,
    mock_bus: MagicMock,
) -> None:
    # Given
    # Default PreToolCallHook state is NOT_SET; no side effect needed.
    caller = _make_caller(conversation=conversation, tool_call=tool_call, hooks=hooks, tools=tools)

    # When
    await caller.call()

    # Then
    assert len(conversation.messages) == 1
    msg = conversation.messages[0]
    assert isinstance(msg, dict)
    assert msg["content"] == "The user didn't explicitly approve or deny the tool call. The tool call wasn't executed as a safety measure."


# --- Tests for call() - Error handling -----------------------------------------


async def test_call_with_invalid_json_args_appends_error_message_to_conversation(
    conversation: Conversation,
    hooks: Hooks,
    tools: Tools,
    mock_bus: MagicMock,
) -> None:
    # Given
    tc = _make_tool_call(arguments="not valid json")
    caller = _make_caller(conversation=conversation, tool_call=tc, hooks=hooks, tools=tools)

    # When
    await caller.call()

    # Then
    assert len(conversation.messages) == 1
    msg = conversation.messages[0]
    assert isinstance(msg, dict)
    assert "JSONDecodeError" in msg["content"]


async def test_call_with_invalid_json_args_emits_error_message_event_on_bus(
    conversation: Conversation,
    hooks: Hooks,
    tools: Tools,
    mock_bus: MagicMock,
) -> None:
    # Given
    tc = _make_tool_call(arguments="not valid json")
    caller = _make_caller(conversation=conversation, tool_call=tc, hooks=hooks, tools=tools)

    # When
    await caller.call()

    # Then
    error_calls = [call for call in mock_bus.emit_and_handle.call_args_list if isinstance(call.args[0], MessageEvent)]
    assert len(error_calls) == 1
    error_event: MessageEvent = error_calls[0].args[0]
    assert error_event.message_type == MessageType.TOOL_OUTPUT
    assert error_event.message_markup == MessageMarkup.NONE


async def test_call_with_validation_error_appends_error_message_to_conversation(
    conversation: Conversation,
    tool_call: ChatCompletionMessageFunctionToolCall,
    hooks: Hooks,
    mock_bus: MagicMock,
) -> None:
    # Given
    failing_tool = AsyncMock()
    failing_tool.validate_args = MagicMock(side_effect=JsonSchemaValidationError("Invalid args"))
    tools = _make_tools(failing_tool)
    caller = _make_caller(conversation=conversation, tool_call=tool_call, hooks=hooks, tools=tools)

    # When
    await caller.call()

    # Then
    assert len(conversation.messages) == 1
    msg = conversation.messages[0]
    assert isinstance(msg, dict)
    assert "ValidationError" in msg["content"]


async def test_call_with_tool_execution_error_appends_error_message_to_conversation(
    conversation: Conversation,
    tool_call: ChatCompletionMessageFunctionToolCall,
    hooks: Hooks,
    mock_bus: MagicMock,
) -> None:
    # Given
    failing_tool = AsyncMock()
    failing_tool.validate_args = MagicMock()
    failing_tool.run.side_effect = RuntimeError("Tool failed")
    tools = _make_tools(failing_tool)
    caller = _make_caller(conversation=conversation, tool_call=tool_call, hooks=hooks, tools=tools)

    async def approve_hook(hook_data: Any) -> None:
        if isinstance(hook_data, PreToolCallHook):
            hook_data.state = ApprovalState.APPROVED

    with patch.object(hooks, "run", new_callable=AsyncMock, side_effect=approve_hook):
        # When
        await caller.call()

    # Then
    assert len(conversation.messages) == 1
    msg = conversation.messages[0]
    assert isinstance(msg, dict)
    assert "RuntimeError: Tool failed" == msg["content"]


async def test_call_with_tool_execution_error_returns_none(
    conversation: Conversation,
    tool_call: ChatCompletionMessageFunctionToolCall,
    hooks: Hooks,
    mock_bus: MagicMock,
) -> None:
    # Given
    failing_tool = AsyncMock()
    failing_tool.validate_args = MagicMock()
    failing_tool.run.side_effect = RuntimeError("Tool failed")
    tools = _make_tools(failing_tool)
    caller = _make_caller(conversation=conversation, tool_call=tool_call, hooks=hooks, tools=tools)

    async def approve_hook(hook_data: Any) -> None:
        if isinstance(hook_data, PreToolCallHook):
            hook_data.state = ApprovalState.APPROVED

    with patch.object(hooks, "run", new_callable=AsyncMock, side_effect=approve_hook):
        # When
        result = await caller.call()

    # Then
    assert result is None


async def test_call_with_unknown_tool_name_appends_error_message_to_conversation(
    conversation: Conversation,
    hooks: Hooks,
    tools: Tools,
    mock_bus: MagicMock,
) -> None:
    # Given
    tc = _make_tool_call(tool_name="unknown_tool")
    caller = _make_caller(conversation=conversation, tool_call=tc, hooks=hooks, tools=tools)

    # When
    await caller.call()

    # Then
    assert len(conversation.messages) == 1
    msg = conversation.messages[0]
    assert isinstance(msg, dict)
    assert "KeyError" in msg["content"]


# --- Tests for call() - Extra content handling ---------------------------------


async def test_call_with_approved_state_and_extra_content_passes_it_to_conversation(
    conversation: Conversation,
    hooks: Hooks,
    tools: Tools,
    mock_bus: MagicMock,
) -> None:
    # Given
    extra = {"path": "/some/file.py"}
    tc = _make_tool_call(extra_content=extra)
    caller = _make_caller(conversation=conversation, tool_call=tc, hooks=hooks, tools=tools)

    async def approve_hook(hook_data: Any) -> None:
        if isinstance(hook_data, PreToolCallHook):
            hook_data.state = ApprovalState.APPROVED

    with patch.object(hooks, "run", new_callable=AsyncMock, side_effect=approve_hook):
        # When
        await caller.call()

    # Then
    msg = conversation.messages[0]
    assert isinstance(msg, dict)
    assert msg["extra_content"] == extra


async def test_call_with_denied_state_and_extra_content_passes_it_to_conversation(
    conversation: Conversation,
    hooks: Hooks,
    tools: Tools,
    mock_bus: MagicMock,
) -> None:
    # Given
    extra = {"path": "/some/file.py"}
    tc = _make_tool_call(extra_content=extra)
    caller = _make_caller(conversation=conversation, tool_call=tc, hooks=hooks, tools=tools)

    async def deny_hook(hook_data: Any) -> None:
        if isinstance(hook_data, PreToolCallHook):
            hook_data.state = ApprovalState.DENIED

    with patch.object(hooks, "run", new_callable=AsyncMock, side_effect=deny_hook):
        # When
        await caller.call()

    # Then
    msg = conversation.messages[0]
    assert isinstance(msg, dict)
    assert msg["extra_content"] == extra


async def test_call_without_extra_content_omits_extra_content_in_conversation(
    conversation: Conversation,
    tool_call: ChatCompletionMessageFunctionToolCall,
    hooks: Hooks,
    tools: Tools,
    mock_bus: MagicMock,
) -> None:
    # Given
    caller = _make_caller(conversation=conversation, tool_call=tool_call, hooks=hooks, tools=tools)

    async def approve_hook(hook_data: Any) -> None:
        if isinstance(hook_data, PreToolCallHook):
            hook_data.state = ApprovalState.APPROVED

    with patch.object(hooks, "run", new_callable=AsyncMock, side_effect=approve_hook):
        # When
        await caller.call()

    # Then
    msg = conversation.messages[0]
    assert isinstance(msg, dict)
    assert "extra_content" not in msg


async def test_call_with_error_and_extra_content_passes_it_to_conversation(
    conversation: Conversation,
    hooks: Hooks,
    tools: Tools,
    mock_bus: MagicMock,
) -> None:
    # Given
    extra = {"path": "/some/file.py"}
    tc = _make_tool_call(arguments="not valid json", extra_content=extra)
    caller = _make_caller(conversation=conversation, tool_call=tc, hooks=hooks, tools=tools)

    # When
    await caller.call()

    # Then
    msg = conversation.messages[0]
    assert isinstance(msg, dict)
    assert msg["extra_content"] == extra
