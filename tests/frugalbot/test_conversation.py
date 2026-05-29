from pathlib import Path
from typing import Any, cast

import orjson as json
import pytest
from any_llm.types.completion import (
    ChatCompletion,
    ChatCompletionMessage,
    ChatCompletionMessageFunctionToolCall,
    Choice,
    CompletionUsage,
    Function,
    PromptTokensDetails,
)

from frugalbot.conversation import Conversation
from frugalbot.hooks.base import Hooks

# --- Fixtures --------------------------------------------------------------------


@pytest.fixture
def hooks() -> Hooks:
    return Hooks()


@pytest.fixture
def conv(hooks: Hooks) -> Conversation:
    return Conversation(hooks=hooks)


# --- Helpers -------------------------------------------------------------------


def _make_completion(
    *,
    content: str = "Assistant response",
    id: str = "comp_1",
    model: str = "gpt-4",
    created: int = 123456789,
    usage: CompletionUsage | None = None,
    tool_calls: list[ChatCompletionMessageFunctionToolCall] | None = None,
) -> ChatCompletion:
    """Create a ChatCompletion with sensible defaults for tests."""
    message = ChatCompletionMessage(role="assistant", content=content)
    if tool_calls:
        message.tool_calls = tool_calls  # pyright: ignore[reportAttributeAccessIssue]
    choice = Choice(index=0, message=message, finish_reason="stop")
    return ChatCompletion(id=id, choices=[choice], model=model, created=created, object="chat.completion", usage=usage)


def _make_usage(
    *,
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
    total_tokens: int = 15,
    cached_tokens: int = 0,
) -> CompletionUsage:
    """Create a CompletionUsage with sensible defaults for tests."""
    return CompletionUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        prompt_tokens_details=PromptTokensDetails(cached_tokens=cached_tokens),
    )


# --- __init__ ------------------------------------------------------------------


def test_init_new_conversation_creates_empty_messages(hooks: Hooks) -> None:
    # Given
    # No preconditions needed

    # When
    conv = Conversation(hooks=hooks)

    # Then
    assert conv.messages == []


def test_init_new_conversation_creates_empty_entries(hooks: Hooks) -> None:
    # Given
    # No preconditions needed

    # When
    conv = Conversation(hooks=hooks)

    # Then
    assert conv.entries == []


# --- append_system_message -----------------------------------------------------


async def test_append_system_message_as_first_message_appends_system_dict(conv: Conversation) -> None:
    # Given
    # No preconditions needed

    # When
    await conv.append_system_message("You are a helpful assistant.")

    # Then
    assert conv.messages == [{"role": "system", "content": "You are a helpful assistant."}]


async def test_append_system_message_after_existing_message_raises_value_error(conv: Conversation) -> None:
    # Given
    await conv.append_user_message("Hello")

    # When / Then
    with pytest.raises(ValueError, match="System message must be the first message in the conversation"):
        await conv.append_system_message("Too late")


async def test_append_system_message_as_first_message_stores_dict_in_entries(conv: Conversation) -> None:
    # Given
    # No preconditions needed

    # When
    await conv.append_system_message("System prompt")

    # Then
    assert len(conv.entries) == 1
    entry = conv.entries[0]
    assert isinstance(entry, dict)
    assert entry["role"] == "system"


# --- append_user_message -------------------------------------------------------


async def test_append_user_message_with_text_appends_user_dict(conv: Conversation) -> None:
    # Given
    # No preconditions needed

    # When
    await conv.append_user_message("Hello, bot!")

    # Then
    assert conv.messages == [{"role": "user", "content": "Hello, bot!"}]


async def test_append_user_message_after_system_appends_in_order(conv: Conversation) -> None:
    # Given
    await conv.append_system_message("System")

    # When
    await conv.append_user_message("User")

    # Then
    assert conv.messages == [{"role": "system", "content": "System"}, {"role": "user", "content": "User"}]


# --- append_tool_message -------------------------------------------------------


async def test_append_tool_message_with_all_fields_appends_tool_dict(conv: Conversation) -> None:
    # Given
    # No preconditions needed

    # When
    await conv.append_tool_message("read_file", "file contents here", "text", "tc_001", {"path": "/foo.py"})

    # Then
    assert conv.messages == [
        {
            "name": "read_file",
            "role": "tool",
            "content": "file contents here",
            "tool_call_id": "tc_001",
            "extra_content": {"path": "/foo.py"},
        }
    ]


async def test_append_tool_message_with_none_extra_content_omits_extra_content_key(conv: Conversation) -> None:
    # Given
    # No preconditions needed

    # When
    await conv.append_tool_message("tool", "result", "text", "tc_002", None)

    # Then
    entry = conv.entries[0]
    assert isinstance(entry, dict)
    msg = cast(dict[str, Any], entry)
    assert msg["role"] == "tool"
    assert msg["name"] == "tool"
    assert msg["content"] == "result"
    assert msg["tool_call_id"] == "tc_002"
    assert "extra_content" not in msg


# --- append_assistant_message --------------------------------------------------


def test_append_assistant_message_with_completion_stores_tuple_in_entries(conv: Conversation) -> None:
    # Given
    completion = _make_completion(content="Hi there")

    # When
    conv.append_assistant_message("openai", completion)

    # Then
    assert len(conv.entries) == 1
    entry = conv.entries[0]
    assert isinstance(entry, tuple)
    assert entry[0] == "openai"
    assert entry[1] is completion


def test_append_assistant_message_with_completion_exposes_message_via_messages_property(conv: Conversation) -> None:
    # Given
    completion = _make_completion(content="Hi there")

    # When
    conv.append_assistant_message("openai", completion)

    # Then
    assert len(conv.messages) == 1
    assert conv.messages[0] == completion.choices[0].message


# --- latest_assistant_message --------------------------------------------------


def test_latest_assistant_message_on_empty_conversation_raises_value_error(conv: Conversation) -> None:
    # Given
    # No preconditions needed

    # When / Then
    with pytest.raises(ValueError, match="No assistant message found in conversation"):
        conv.latest_assistant_message()


async def test_latest_assistant_message_with_only_user_message_raises_value_error(conv: Conversation) -> None:
    # Given
    await conv.append_user_message("Hello")

    # When / Then
    with pytest.raises(ValueError, match="No assistant message found in conversation"):
        conv.latest_assistant_message()


def test_latest_assistant_message_with_single_assistant_returns_message(conv: Conversation) -> None:
    # Given
    completion = _make_completion(content="Response 1")
    conv.append_assistant_message("openai", completion)

    # When
    result = conv.latest_assistant_message()

    # Then
    assert result == completion.choices[0].message


async def test_latest_assistant_message_with_multiple_assistant_messages_returns_last(conv: Conversation) -> None:
    # Given
    comp1 = _make_completion(content="First", id="comp_1")
    comp2 = _make_completion(content="Second", id="comp_2")
    conv.append_assistant_message("openai", comp1)
    await conv.append_user_message("Still here?")
    conv.append_assistant_message("openai", comp2)

    # When
    result = conv.latest_assistant_message()

    # Then
    assert result.content == "Second"


# --- serialize_to_dict / serialize_to_string -----------------------------------


def test_serialize_to_dict_with_no_messages_returns_empty_messages_list(conv: Conversation) -> None:
    # Given
    # No preconditions needed

    # When
    result = conv.serialize_to_dict()

    # Then
    assert result == {"messages": []}


async def test_serialize_to_dict_with_mixed_messages_returns_correct_structure(conv: Conversation) -> None:
    # Given
    await conv.append_system_message("Sys")
    await conv.append_user_message("Usr")
    completion = _make_completion(content="Asst")
    conv.append_assistant_message("openai", completion)

    # When
    result = conv.serialize_to_dict()

    # Then
    msgs = result["messages"]
    assert len(msgs) == 3
    assert msgs[0]["type"] == "message"
    assert msgs[0]["data"]["role"] == "system"
    assert msgs[1]["type"] == "message"
    assert msgs[1]["data"]["role"] == "user"
    assert msgs[2]["type"] == "completion"
    assert msgs[2]["provider"] == "openai"


def test_serialize_to_string_returns_valid_json_string(conv: Conversation) -> None:
    # Given
    # No preconditions needed

    # When
    result = conv.serialize_to_string()

    # Then
    parsed = json.loads(result)
    assert parsed == {"messages": []}


async def test_serialize_to_string_with_content_contains_roles(conv: Conversation) -> None:
    # Given
    await conv.append_system_message("Be nice")
    await conv.append_user_message("Hi")

    # When
    result = conv.serialize_to_string()

    # Then
    assert '"role": "system"' in result
    assert '"role": "user"' in result


# --- serialize_to_file / load_from_file ----------------------------------------


async def test_serialize_to_file_and_load_from_file_round_trips_messages(conv: Conversation, fs) -> None:
    # Given
    await conv.append_system_message("System")
    await conv.append_user_message("User")
    completion = _make_completion(content="Assistant")
    conv.append_assistant_message("test_provider", completion)
    file_path = Path("/conversation.json")

    # When
    await conv.serialize_to_file(file_path)
    hooks2 = Hooks()
    conv2 = Conversation(hooks=hooks2)
    await conv2.load_from_file(file_path)

    # Then
    assert conv2.messages == conv.messages


async def test_serialize_to_file_creates_file_at_nested_path(conv: Conversation, fs) -> None:
    # Given
    await conv.append_system_message("System")
    file_path = Path("/nested/dir/conversation.json")

    # When
    await conv.serialize_to_file(file_path)

    # Then
    assert file_path.exists()


async def test_serialize_to_file_and_load_restores_correct_entry_types(conv: Conversation, fs) -> None:
    # Given
    await conv.append_system_message("System")
    await conv.append_user_message("User")
    completion = _make_completion(content="Assistant")
    conv.append_assistant_message("test_provider", completion)
    file_path = Path("/conversation.json")

    # When
    await conv.serialize_to_file(file_path)
    hooks2 = Hooks()
    conv2 = Conversation(hooks=hooks2)
    await conv2.load_from_file(file_path)

    # Then
    assert len(conv2.entries) == 3
    assert isinstance(conv2.entries[0], dict)
    assert isinstance(conv2.entries[1], dict)
    assert isinstance(conv2.entries[2], tuple)
    assert isinstance(conv2.entries[2][1], ChatCompletion)


async def test_load_from_file_with_unknown_message_type_raises_value_error(fs) -> None:
    # Given
    file_path = Path("/invalid.json")
    fs.create_file(file_path, contents=json.dumps({"messages": [{"type": "unknown", "data": {}}]}).decode("utf-8"))
    hooks = Hooks()
    conv = Conversation(hooks=hooks)

    # When / Then
    with pytest.raises(ValueError, match="Unknown message type 'unknown'"):
        await conv.load_from_file(file_path)


# --- get_usage -----------------------------------------------------------------


def test_get_usage_with_no_completions_returns_zeroed_usage(conv: Conversation) -> None:
    # Given
    # No preconditions needed

    # When
    result = conv.get_usage()

    # Then
    assert result.total_prompt_tokens == 0
    assert result.total_cached_tokens == 0
    assert result.total_tokens == 0


def test_get_usage_with_single_completion_returns_usage_from_completion(conv: Conversation) -> None:
    # Given
    usage = _make_usage(prompt_tokens=100, total_tokens=120, cached_tokens=5)
    completion = _make_completion(content="Hello", usage=usage)
    conv.append_assistant_message("openai", completion)

    # When
    result = conv.get_usage()

    # Then
    assert result.total_prompt_tokens == 100
    assert result.total_cached_tokens == 5
    assert result.total_tokens == 120


def test_get_usage_with_multiple_completions_takes_last_prompt(conv: Conversation) -> None:
    # Given
    u1 = _make_usage(prompt_tokens=10, total_tokens=15, cached_tokens=2)
    c1 = _make_completion(content="First", id="comp_1", usage=u1)
    conv.append_assistant_message("openai", c1)

    u2 = _make_usage(prompt_tokens=25, total_tokens=35, cached_tokens=5)
    c2 = _make_completion(content="Second", id="comp_2", usage=u2)
    conv.append_assistant_message("openai", c2)

    # When
    result = conv.get_usage()

    # Then
    assert result.total_prompt_tokens == 25
    assert result.total_cached_tokens == 5


def test_get_usage_with_completion_lacking_usage_returns_zeroed_usage(conv: Conversation) -> None:
    # Given
    completion = _make_completion(content="No usage", usage=None)
    conv.append_assistant_message("openai", completion)

    # When
    result = conv.get_usage()

    # Then
    assert result.total_prompt_tokens == 0


# --- convert_into_web_chat_prompt ----------------------------------------------


async def test_convert_into_web_chat_prompt_with_system_and_user_returns_formatted_string(conv: Conversation) -> None:
    # Given
    await conv.append_system_message("Be concise.")
    await conv.append_user_message("What is Python?")

    # When
    result = conv.convert_into_web_chat_prompt()

    # Then
    assert result == "System: Be concise.\n\nUser: What is Python?"


async def test_convert_into_web_chat_prompt_with_assistant_message_includes_content(conv: Conversation) -> None:
    # Given
    await conv.append_user_message("Hi")
    completion = _make_completion(content="Hello!")
    conv.append_assistant_message("openai", completion)

    # When
    result = conv.convert_into_web_chat_prompt()

    # Then
    assert "User: Hi" in result
    assert "Assistant:" in result
    assert "Hello!" in result


async def test_convert_into_web_chat_prompt_with_tool_message_includes_tool_name_and_result(conv: Conversation) -> None:
    # Given
    await conv.append_tool_message("read_file", "line 1\nline 2", "text", "tc_001", None)

    # When
    result = conv.convert_into_web_chat_prompt()

    # Then
    assert "Tool [read_file]:" in result
    assert "line 1" in result
    assert "line 2" in result


async def test_convert_into_web_chat_prompt_with_full_conversation_returns_complete_prompt(conv: Conversation) -> None:
    # Given
    await conv.append_system_message("You are a coder.")
    await conv.append_user_message("Read a file")
    completion = _make_completion(content="Here you go:")
    conv.append_assistant_message("openai", completion)
    await conv.append_tool_message("read_file", "contents", "text", "tc_001", None)

    # When
    result = conv.convert_into_web_chat_prompt()

    # Then
    assert result.startswith("System: You are a coder.")
    assert "User: Read a file" in result
    assert "Assistant:\nHere you go:" in result
    assert "Tool [read_file]:" in result


async def test_convert_into_web_chat_prompt_with_empty_conversation_returns_empty_string(conv: Conversation) -> None:
    # Given
    # No preconditions needed

    # When
    result = conv.convert_into_web_chat_prompt()

    # Then
    assert result == ""


async def test_convert_into_web_chat_prompt_with_assistant_tool_calls_includes_tool_call_block(conv: Conversation) -> None:
    # Given
    await conv.append_user_message("List files")
    tool_call = ChatCompletionMessageFunctionToolCall(
        id="tc_001",
        type="function",
        function=Function(name="list_files", arguments='{"path": "."}'),
    )
    completion = _make_completion(content="Let me do that.", tool_calls=[tool_call])
    conv.append_assistant_message("openai", completion)

    # When
    result = conv.convert_into_web_chat_prompt()

    # Then
    assert "<tool_calls>" in result
    assert "list_files" in result
