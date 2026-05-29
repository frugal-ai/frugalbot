from dataclasses import dataclass, field
from typing import Any, cast

from frugalbot.hooks.base import AgentStopHook, HookConfig
from frugalbot.hooks.validate_finished import _VERIFICATION_MESSAGE_PREFIX, ValidateFinished
from frugalbot.utils.prompts import USER_PROMPT_SUFFIX_FOR_ATTACHMENTS

# region Test helpers and fixtures


@dataclass
class FakeConversation:
    """In-memory fake for Conversation used by AgentStopHook."""

    messages: list[dict[str, Any] | Any] = field(default_factory=list)
    appended_messages: list[str] = field(default_factory=list)

    async def append_user_message(self, content: str) -> None:
        self.appended_messages.append(content)


def _make_hook_data(messages: list[dict[str, Any] | Any]) -> AgentStopHook:
    conversation = FakeConversation(messages=messages)
    return AgentStopHook(conversation=conversation)  # type: ignore[arg-type]


def _get_fake_conversation(hook_data: AgentStopHook) -> FakeConversation:
    return cast(FakeConversation, hook_data.conversation)


def _make_hook() -> ValidateFinished:
    config = HookConfig(enabled=True)
    return ValidateFinished(config)


def _make_user_message(content: str) -> dict[str, Any]:
    return {"role": "user", "content": content}


def _make_assistant_message(content: str) -> dict[str, Any]:
    return {"role": "assistant", "content": content}


def _make_fake_chat_completion_message(content: str) -> Any:
    """Create a non-dict object that mimics a ChatCompletionMessage with a .content attribute."""

    class FakeChatCompletionMessage:
        def __init__(self, text: str) -> None:
            self.content: str = text
            self.role: str = "assistant"

    return FakeChatCompletionMessage(text=content)


# endregion

# region: No user message found scenarios


async def test_run_with_empty_messages_does_nothing() -> None:
    # Given
    hook = _make_hook()
    hook_data = _make_hook_data(messages=[])

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is False


async def test_run_with_only_assistant_messages_does_nothing() -> None:
    # Given
    hook = _make_hook()
    messages = [_make_assistant_message("Hello"), _make_assistant_message("World")]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is False


async def test_run_with_only_system_messages_does_nothing() -> None:
    # Given
    hook = _make_hook()
    messages = [{"role": "system", "content": "You are a helpful assistant."}]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is False


# endregion

# region: Assistant replied "YES" (task confirmed done)
# Note: The YES detection in the hook only works for non-dict ChatCompletionMessage objects.
# Dict-based assistant messages are skipped by the role check.


async def test_run_with_assistant_yes_does_nothing() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("Do the task"),
        _make_fake_chat_completion_message("I did it"),
        _make_user_message(f"{_VERIFICATION_MESSAGE_PREFIX}Do the task\n---\n\nIf you have completed all requested work, reply with 'YES' and nothing else."),
        _make_fake_chat_completion_message("YES"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is False


async def test_run_with_assistant_yes_lowercase_does_nothing() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("Do the task"),
        _make_fake_chat_completion_message("Done"),
        _make_user_message(f"{_VERIFICATION_MESSAGE_PREFIX}..."),
        _make_fake_chat_completion_message("yes"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is False


async def test_run_with_assistant_yes_mixed_case_does_nothing() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("Do the task"),
        _make_fake_chat_completion_message("Yes"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is False


async def test_run_with_assistant_yes_with_single_quotes_does_nothing() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("Do the task"),
        _make_fake_chat_completion_message("'YES'"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is False


async def test_run_with_assistant_yes_with_double_quotes_does_nothing() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("Do the task"),
        _make_fake_chat_completion_message('"YES"'),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is False


async def test_run_with_assistant_yes_no_continues_after_yes() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("First request"),
        _make_fake_chat_completion_message("Done first"),
        _make_user_message("Second request"),
        _make_fake_chat_completion_message("YES"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is False


# endregion

# region: Assistant replied something other than "YES" (should verify older user message)


async def test_run_with_assistant_non_yes_triggers_verification() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("Please create a file"),
        _make_assistant_message("I have created the file."),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is True


async def test_run_with_assistant_non_yes_appends_verification_message() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("Please create a file"),
        _make_assistant_message("I have created the file."),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    conversation = _get_fake_conversation(hook_data)
    assert len(conversation.appended_messages) == 1
    assert conversation.appended_messages[0].startswith(_VERIFICATION_MESSAGE_PREFIX)
    assert "Please create a file" in conversation.appended_messages[0]
    assert "reply with 'YES'" in conversation.appended_messages[0]


async def test_run_with_assistant_almost_yes_triggers_verification() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("Please create a file"),
        _make_assistant_message("YES!"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is True


# endregion

# region: Verification message prefix skipping


async def test_run_skips_user_message_with_verification_prefix() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("Please create a file"),
        _make_assistant_message("Done"),
        _make_user_message(f"{_VERIFICATION_MESSAGE_PREFIX}Please create a file\n---\n\nIf you have completed all requested work, reply with 'YES' and nothing else."),
        _make_assistant_message("Not yet, working on it"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    conversation = _get_fake_conversation(hook_data)
    assert hook_data.continue_conversation is True
    assert len(conversation.appended_messages) == 1
    # Should find the original user message, not the verification-prefixed one
    assert "Please create a file" in conversation.appended_messages[0]
    # Should not have double verification prefix
    assert conversation.appended_messages[0].count(_VERIFICATION_MESSAGE_PREFIX) == 1


# endregion

# region: Attachments suffix trimming


async def test_run_trims_attachments_suffix_from_user_message() -> None:
    # Given
    hook = _make_hook()
    original_content = "Please fix this file"
    attachments_suffix = f"{USER_PROMPT_SUFFIX_FOR_ATTACHMENTS}file content here"
    messages = [
        _make_user_message(f"{original_content}{attachments_suffix}"),
        _make_assistant_message("I fixed it"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    conversation = _get_fake_conversation(hook_data)
    assert hook_data.continue_conversation is True
    assert len(conversation.appended_messages) == 1
    assert USER_PROMPT_SUFFIX_FOR_ATTACHMENTS not in conversation.appended_messages[0]
    assert "Please fix this file" in conversation.appended_messages[0]


async def test_run_verification_message_contains_trimmed_content() -> None:
    # Given
    hook = _make_hook()
    user_content = "Refactor the module"
    attachment_content = "\n\nThe result of 'read' tool calls...\n\nfile content"
    messages = [
        _make_user_message(f"{user_content}{USER_PROMPT_SUFFIX_FOR_ATTACHMENTS}{attachment_content}"),
        _make_assistant_message("Refactored!"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    conversation = _get_fake_conversation(hook_data)
    verification_msg = conversation.appended_messages[0]
    expected_verification = f"{_VERIFICATION_MESSAGE_PREFIX}{user_content}\n---\n\nIf you have completed all requested work, reply with 'YES' and nothing else."
    assert verification_msg == expected_verification


# endregion

# region: ChatCompletionMessage (non-dict) handling


async def test_run_with_chat_completion_message_yes_does_nothing() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("Do the task"),
        _make_fake_chat_completion_message("YES"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is False


async def test_run_with_chat_completion_message_non_yes_continues_search() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("Please create a file"),
        _make_fake_chat_completion_message("I created the file"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is True


async def test_run_with_chat_completion_message_empty_content_skips() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("Please create a file"),
        _make_fake_chat_completion_message(""),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is True


async def test_run_with_mixed_dict_and_chat_completion_messages_finds_yes() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("Do the task"),
        _make_assistant_message("Working on it"),
        _make_fake_chat_completion_message("YES"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is False


async def test_run_with_mixed_dict_and_chat_completion_messages_triggers_verification() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("Do the task"),
        _make_fake_chat_completion_message("Done"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is True


# endregion

# region: Edge cases


async def test_run_with_user_message_missing_content_key_skips() -> None:
    # Given
    hook = _make_hook()
    messages = [
        {"role": "user"},
        _make_assistant_message("Hello"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is False


async def test_run_with_user_message_missing_role_key_skips() -> None:
    # Given
    hook = _make_hook()
    messages = [
        {"content": "Hello"},
        _make_assistant_message("Hi"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is False


async def test_run_with_assistant_role_not_user_skips() -> None:
    # Given
    hook = _make_hook()
    messages = [
        {"role": "assistant", "content": "Done"},
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is False


async def test_run_stops_at_first_matching_user_message() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("First task"),
        _make_assistant_message("Done first"),
        _make_user_message("Second task"),
        _make_assistant_message("Done second"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    conversation = _get_fake_conversation(hook_data)
    assert hook_data.continue_conversation is True
    # Should only append one verification message for the latest user message
    assert len(conversation.appended_messages) == 1
    assert "Second task" in conversation.appended_messages[0]
    assert "First task" not in conversation.appended_messages[0]


async def test_run_with_only_tool_messages_does_nothing() -> None:
    # Given
    hook = _make_hook()
    messages = [
        {"role": "tool", "content": "result", "name": "edit", "tool_call_id": "123"},
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is False


async def test_run_with_assistant_yes_with_parentheses_does_nothing() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("Do the task"),
        _make_fake_chat_completion_message("(YES)"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is False


async def test_run_with_assistant_yes_with_brackets_does_nothing() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("Do the task"),
        _make_fake_chat_completion_message("[YES]"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is False


async def test_run_with_assistant_yes_too_long_triggers_verification() -> None:
    # Given
    hook = _make_hook()
    messages = [
        _make_user_message("Do the task"),
        _make_assistant_message("!YES!!"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.continue_conversation is True


async def test_run_verification_message_format_matches_expected() -> None:
    # Given
    hook = _make_hook()
    user_text = "Build a web scraper"
    messages = [
        _make_user_message(user_text),
        _make_assistant_message("Done!"),
    ]
    hook_data = _make_hook_data(messages=messages)

    # When
    await hook.run(hook_data)

    # Then
    conversation = _get_fake_conversation(hook_data)
    expected = f"{_VERIFICATION_MESSAGE_PREFIX}{user_text}\n---\n\nIf you have completed all requested work, reply with 'YES' and nothing else."
    assert conversation.appended_messages[0] == expected


# endregion
