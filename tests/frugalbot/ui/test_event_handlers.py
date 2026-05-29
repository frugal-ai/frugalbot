import inspect
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from frugalbot.events import (
    BulkMessageEvent,
    MessageEvent,
    MessageMarkup,
    MessageType,
    QuestionResponse,
    QuestionType,
    StatusUpdateEvent,
    UserChoiceInteractionEvent,
    UserCompositeInteractionEvent,
    UserTextInteractionEvent,
)
from frugalbot.ui import event_handlers as event_handlers_module

TUI_PATCH_PATH = "frugalbot.ui.event_handlers.tui"


async def _invoke_handler(handler: Any, event: Any) -> None:
    """Invoke a handler (sync or async) safely handling Awaitable[None] | None return."""
    result = handler(event)  # result is Any since handler is Any
    if inspect.iscoroutine(result):
        await result


@pytest.fixture(autouse=True)
def _isolate_bus() -> Generator[None]:
    """Clear all bus subscribers before and after each test to ensure isolation."""
    event_handlers_module.bus.clear_subscribers()
    yield
    event_handlers_module.bus.clear_subscribers()


@pytest.fixture(autouse=True)
def _register_handlers() -> None:
    """Re-import event_handlers to register handlers on the (cleared) global bus."""
    import importlib

    importlib.reload(event_handlers_module)


class TestHandleMessage:
    """Tests for the handle_message and _handle_message handlers."""

    @pytest.fixture
    def mock_tui(self) -> MagicMock:
        mock = MagicMock()
        mock.md_stream = None
        mock.stream_type = MessageType.INFO
        mock.output = MagicMock()
        return mock

    async def test_handle_message_with_no_tui_output_does_nothing(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        del mock_tui.output  # Simulate tui having no "output" attribute
        event = MessageEvent(message="Hello", message_type=MessageType.INFO)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_message, event)

        # Then
        mock_tui.append_block.assert_not_called()

    async def test_handle_message_with_info_type_uses_green_prefix(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        event = MessageEvent(message="Info message", message_type=MessageType.INFO)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_message, event)

        # Then
        call_args = mock_tui.append_block.call_args
        assert "[bold green]INFO[/]" in call_args[0][0]

    async def test_handle_message_with_warning_type_uses_yellow_prefix(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        event = MessageEvent(message="Warning message", message_type=MessageType.WARNING)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_message, event)

        # Then
        call_args = mock_tui.append_block.call_args
        assert "[bold yellow]WARNING[/]" in call_args[0][0]

    async def test_handle_message_with_error_type_uses_red_prefix(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        event = MessageEvent(message="Error occurred", message_type=MessageType.ERROR)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_message, event)

        # Then
        call_args = mock_tui.append_block.call_args
        assert "[bold red]ERROR[/]" in call_args[0][0]

    async def test_handle_message_with_user_type_uses_orange_prefix(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        event = MessageEvent(message="User said hello", message_type=MessageType.USER)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_message, event)

        # Then
        call_args = mock_tui.append_block.call_args
        assert "[bold rgb(215,95,0)]USER[/]" in call_args[0][0]

    async def test_handle_message_with_assistant_type_uses_cyan_prefix(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        event = MessageEvent(message="I can help with that", message_type=MessageType.ASSISTANT)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_message, event)

        # Then
        call_args = mock_tui.append_block.call_args
        assert "[bold cyan]ASSISTANT[/]" in call_args[0][0]

    async def test_handle_message_with_thinking_type_uses_magenta_prefix_and_dim_style(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        event = MessageEvent(message="Thinking...", message_type=MessageType.THINKING)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_message, event)

        # Then
        call_args = mock_tui.append_block.call_args
        assert "[bold magenta]ASSISTANT THINKING[/]" in call_args[0][0]
        assert call_args[0][1] == "dim"

    async def test_handle_message_with_tool_call_type_uses_blue_prefix(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        event = MessageEvent(message="call_tool()", message_type=MessageType.TOOL_CALL)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_message, event)

        # Then
        call_args = mock_tui.append_block.call_args
        assert "[bold rgb(135,175,255)]TOOL CALL[/]" in call_args[0][0]

    async def test_handle_message_with_tool_output_type_uses_magenta_prefix(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        event = MessageEvent(message="Tool result", message_type=MessageType.TOOL_OUTPUT)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_message, event)

        # Then
        call_args = mock_tui.append_block.call_args
        assert "[bold rgb(215,135,215)]TOOL[/]" in call_args[0][0]

    async def test_handle_message_with_system_type_uses_purple_prefix(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        event = MessageEvent(message="System starting", message_type=MessageType.SYSTEM)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_message, event)

        # Then
        call_args = mock_tui.append_block.call_args
        assert "[bold purple]SYSTEM[/]" in call_args[0][0]

    async def test_handle_message_with_non_stream_appends_block_and_rule(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        event = MessageEvent(
            message="Test message",
            message_type=MessageType.INFO,
            message_markup=MessageMarkup.MARKDOWN,
            is_stream=False,
        )

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_message, event)

        # Then
        mock_tui.append_block.assert_called_once()
        call_args = mock_tui.append_block.call_args
        assert call_args[0][2] == "Test message"
        assert call_args[0][3] == MessageMarkup.MARKDOWN
        assert call_args[1]["batch"] is True
        mock_tui.append_rule.assert_called_once_with(batch=False)

    async def test_handle_message_with_non_stream_stops_existing_md_stream(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        mock_md_stream = AsyncMock()
        mock_md_stream.stop = AsyncMock()
        mock_tui.md_stream = mock_md_stream
        event = MessageEvent(message="Non-stream message", message_type=MessageType.ASSISTANT)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_message, event)

        # Then
        mock_md_stream.stop.assert_awaited_once()

    async def test_handle_message_with_non_stream_appends_rule_with_batch_true_after_stop(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        mock_md_stream = AsyncMock()
        mock_md_stream.stop = AsyncMock()
        mock_tui.md_stream = mock_md_stream
        event = MessageEvent(message="Stopping stream", message_type=MessageType.INFO)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_message, event)

        # Then - first append_rule call uses batch=True (from stopping the stream)
        first_call = mock_tui.append_rule.call_args_list[0]
        assert first_call[1]["batch"] is True

    async def test_handle_message_with_user_type_and_non_batch_calls_scroll_end(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        event = MessageEvent(message="User message", message_type=MessageType.USER, is_stream=False)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_message, event)

        # Then
        mock_tui.call_after_refresh.assert_called_once()
        callback = mock_tui.call_after_refresh.call_args[0][0]
        # Execute the callback while mock_tui.output is still valid
        with patch(TUI_PATCH_PATH, mock_tui):
            callback()
        mock_tui.output.scroll_end.assert_called_once_with(animate=False)

    async def test_handle_message_with_stream_starts_new_streaming_block(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        event = MessageEvent(message="Stream start", message_type=MessageType.ASSISTANT, is_stream=True)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_message, event)

        # Then
        mock_tui.start_streaming_block.assert_called_once()
        call_args = mock_tui.start_streaming_block.call_args
        assert call_args[0][2] == "Stream start"
        assert mock_tui.stream_type == MessageType.ASSISTANT

    async def test_handle_message_with_stream_appends_to_existing_stream_when_type_matches(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        mock_tui.md_stream = MagicMock()
        mock_tui.append_to_streaming_block = AsyncMock()
        mock_tui.stream_type = MessageType.ASSISTANT
        event = MessageEvent(message=" Stream continuation", message_type=MessageType.ASSISTANT, is_stream=True)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_message, event)

        # Then
        mock_tui.append_to_streaming_block.assert_awaited_once_with(" Stream continuation")
        mock_tui.start_streaming_block.assert_not_called()

    async def test_handle_message_with_stream_switches_type_stops_old_stream_and_starts_new(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        mock_md_stream = AsyncMock()
        mock_md_stream.stop = AsyncMock()
        mock_tui.md_stream = mock_md_stream
        mock_tui.stream_type = MessageType.ASSISTANT
        event = MessageEvent(message="Tool output", message_type=MessageType.TOOL_OUTPUT, is_stream=True)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_message, event)

        # Then
        mock_md_stream.stop.assert_awaited_once()
        mock_tui.append_rule.assert_called_once()
        mock_tui.start_streaming_block.assert_called_once()
        assert mock_tui.stream_type == MessageType.TOOL_OUTPUT


class TestHandleBulkMessage:
    """Tests for handle_bulk_message."""

    @pytest.fixture
    def mock_tui(self) -> MagicMock:
        mock = MagicMock()
        mock.md_stream = None
        mock.stream_type = MessageType.INFO
        mock.output = MagicMock()
        return mock

    async def test_handle_bulk_message_with_empty_list_does_not_raise(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        event = BulkMessageEvent(messages=[])

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_bulk_message, event)

        # Then - no exception raised

    async def test_handle_bulk_message_with_single_message_calls_append_block_once(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        event = BulkMessageEvent(messages=[MessageEvent(message="Only message", message_type=MessageType.INFO)])

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_bulk_message, event)

        # Then
        assert mock_tui.append_block.call_count == 1
        # Last message gets batch=False for the rule
        mock_tui.append_rule.assert_called_with(batch=False)

    async def test_handle_bulk_message_with_multiple_messages_appends_all_blocks(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        event = BulkMessageEvent(
            messages=[
                MessageEvent(message="First", message_type=MessageType.USER),
                MessageEvent(message="Second", message_type=MessageType.ASSISTANT),
                MessageEvent(message="Third", message_type=MessageType.INFO),
            ]
        )

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_bulk_message, event)

        # Then
        assert mock_tui.append_block.call_count == 3

    async def test_handle_bulk_message_with_multiple_messages_batches_all_but_last(
        self,
        mock_tui: MagicMock,
    ) -> None:
        # Given
        event = BulkMessageEvent(
            messages=[
                MessageEvent(message="First", message_type=MessageType.USER),
                MessageEvent(message="Second", message_type=MessageType.ASSISTANT),
                MessageEvent(message="Third", message_type=MessageType.INFO),
            ]
        )

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_bulk_message, event)

        # Then - check that the first two calls used batch=True and the last used batch=False
        append_rule_calls = mock_tui.append_rule.call_args_list
        assert len(append_rule_calls) == 3
        assert append_rule_calls[0][1]["batch"] is True
        assert append_rule_calls[1][1]["batch"] is True
        assert append_rule_calls[2][1]["batch"] is False


class TestHandleUserChoiceInteraction:
    """Tests for handle_user_choice_interaction."""

    async def test_handle_user_choice_interaction_with_yes_no_pushes_question_screen(
        self,
    ) -> None:
        # Given
        mock_tui = MagicMock()
        mock_tui.push_screen_wait = AsyncMock(return_value=QuestionResponse.YES)
        event = UserChoiceInteractionEvent(prompt="Continue?", question_type=QuestionType.YES_NO)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_user_choice_interation, event)

        # Then
        mock_tui.push_screen_wait.assert_awaited_once()
        screen_arg = mock_tui.push_screen_wait.call_args[0][0]
        assert screen_arg.question == "Continue?"
        assert screen_arg.question_type == QuestionType.YES_NO

    async def test_handle_user_choice_interaction_with_yes_response_sets_future_result(
        self,
    ) -> None:
        # Given
        mock_tui = MagicMock()
        mock_tui.push_screen_wait = AsyncMock(return_value=QuestionResponse.YES)
        event = UserChoiceInteractionEvent(prompt="Approve?", question_type=QuestionType.YES_NO)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_user_choice_interation, event)

        # Then
        assert event.future.done() is True
        assert event.future.result() == QuestionResponse.YES

    async def test_handle_user_choice_interaction_with_no_response_sets_future_result(
        self,
    ) -> None:
        # Given
        mock_tui = MagicMock()
        mock_tui.push_screen_wait = AsyncMock(return_value=QuestionResponse.NO)
        event = UserChoiceInteractionEvent(prompt="Delete?", question_type=QuestionType.YES_NO)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_user_choice_interation, event)

        # Then
        assert event.future.result() == QuestionResponse.NO

    async def test_handle_user_choice_interaction_with_always_response_sets_future_result(
        self,
    ) -> None:
        # Given
        mock_tui = MagicMock()
        mock_tui.push_screen_wait = AsyncMock(return_value=QuestionResponse.ALWAYS)
        event = UserChoiceInteractionEvent(prompt="Always allow?", question_type=QuestionType.YES_NO_ALWAYS)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_user_choice_interation, event)

        # Then
        assert event.future.result() == QuestionResponse.ALWAYS

    async def test_handle_user_choice_interaction_with_ok_only_pushes_screen(
        self,
    ) -> None:
        # Given
        mock_tui = MagicMock()
        mock_tui.push_screen_wait = AsyncMock(return_value=QuestionResponse.OK)
        event = UserChoiceInteractionEvent(prompt="Press OK to continue", question_type=QuestionType.OK_ONLY)

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_user_choice_interation, event)

        # Then
        screen_arg = mock_tui.push_screen_wait.call_args[0][0]
        assert screen_arg.question_type == QuestionType.OK_ONLY
        assert event.future.result() == QuestionResponse.OK


class TestHandleUserTextInteraction:
    """Tests for handle_user_text_interaction."""

    async def test_handle_user_text_interaction_with_prompt_pushes_text_prompt_screen(
        self,
    ) -> None:
        # Given
        mock_tui = MagicMock()
        mock_tui.push_screen_wait = AsyncMock(return_value="user input here")
        event = UserTextInteractionEvent(prompt="Enter your name:")

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_user_text_interaction, event)

        # Then
        mock_tui.push_screen_wait.assert_awaited_once()
        screen_arg = mock_tui.push_screen_wait.call_args[0][0]
        assert screen_arg.prompt == "Enter your name:"

    async def test_handle_user_text_interaction_with_user_input_sets_future_result(
        self,
    ) -> None:
        # Given
        mock_tui = MagicMock()
        mock_tui.push_screen_wait = AsyncMock(return_value="Alice")
        event = UserTextInteractionEvent(prompt="Name?")

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_user_text_interaction, event)

        # Then
        assert event.future.done() is True
        assert event.future.result() == "Alice"

    async def test_handle_user_text_interaction_with_empty_input_sets_empty_future_result(
        self,
    ) -> None:
        # Given
        mock_tui = MagicMock()
        mock_tui.push_screen_wait = AsyncMock(return_value="")
        event = UserTextInteractionEvent(prompt="Enter comment:")

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_user_text_interaction, event)

        # Then
        assert event.future.result() == ""


class TestHandleUserCompositeInteraction:
    """Tests for handle_user_composite_interaction."""

    async def test_handle_user_composite_interaction_with_no_response_does_not_prompt_for_text(
        self,
    ) -> None:
        # Given
        mock_tui = MagicMock()
        mock_tui.push_screen_wait = AsyncMock(return_value=QuestionResponse.NO)
        event = UserCompositeInteractionEvent(
            prompt="Proceed?",
            question_type=QuestionType.YES_NO,
            follow_up_prompt="Enter reason:",
        )

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_user_composite_interaction, event)

        # Then
        assert mock_tui.push_screen_wait.await_count == 1
        assert event.future.result() == (QuestionResponse.NO, "")

    async def test_handle_user_composite_interaction_with_yes_response_prompts_for_text(
        self,
    ) -> None:
        # Given
        mock_tui = MagicMock()
        mock_tui.push_screen_wait = AsyncMock(side_effect=[QuestionResponse.YES, "my reason"])
        event = UserCompositeInteractionEvent(
            prompt="Proceed?",
            question_type=QuestionType.YES_NO,
            follow_up_prompt="Enter reason:",
        )

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_user_composite_interaction, event)

        # Then
        assert mock_tui.push_screen_wait.await_count == 2
        # Second call should be a TextPromptScreen with follow_up_prompt
        second_call_arg = mock_tui.push_screen_wait.call_args_list[1][0][0]
        assert second_call_arg.prompt == "Enter reason:"
        assert event.future.result() == (QuestionResponse.YES, "my reason")

    async def test_handle_user_composite_interaction_with_yes_and_empty_text_sets_tuple_result(
        self,
    ) -> None:
        # Given
        mock_tui = MagicMock()
        mock_tui.push_screen_wait = AsyncMock(side_effect=[QuestionResponse.YES, ""])
        event = UserCompositeInteractionEvent(
            prompt="Continue?",
            question_type=QuestionType.YES_NO,
            follow_up_prompt="Details:",
        )

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_user_composite_interaction, event)

        # Then
        assert event.future.result() == (QuestionResponse.YES, "")

    async def test_handle_user_composite_interaction_with_always_response_does_not_prompt_for_text(
        self,
    ) -> None:
        # Given
        mock_tui = MagicMock()
        mock_tui.push_screen_wait = AsyncMock(return_value=QuestionResponse.ALWAYS)
        event = UserCompositeInteractionEvent(
            prompt="Always allow?",
            question_type=QuestionType.YES_NO_ALWAYS,
            follow_up_prompt="Reason:",
        )

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_user_composite_interaction, event)

        # Then
        assert mock_tui.push_screen_wait.await_count == 1
        assert event.future.result() == (QuestionResponse.ALWAYS, "")

    async def test_handle_user_composite_interaction_pushes_question_screen_first(
        self,
    ) -> None:
        # Given
        mock_tui = MagicMock()
        mock_tui.push_screen_wait = AsyncMock(side_effect=[QuestionResponse.NO, "ignored"])
        event = UserCompositeInteractionEvent(
            prompt="First question?",
            question_type=QuestionType.YES_NO,
            follow_up_prompt="Follow up:",
        )

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            await _invoke_handler(event_handlers_module.handle_user_composite_interaction, event)

        # Then
        first_call_arg = mock_tui.push_screen_wait.call_args_list[0][0][0]
        assert first_call_arg.question == "First question?"
        assert first_call_arg.question_type == QuestionType.YES_NO


class TestHandleStatusUpdate:
    """Tests for handle_status_update."""

    @pytest.fixture
    def status_update_event(self) -> StatusUpdateEvent:
        return StatusUpdateEvent(
            agent_name="test-agent",
            provider="openai",
            model_id="gpt-4",
            thinking_level="HIGH",
            total_tokens=1500,
            context_size=8000,
            cost=0.05,
        )

    def test_handle_status_update_with_context_size_updates_status_text(
        self,
        status_update_event: StatusUpdateEvent,
    ) -> None:
        # Given
        mock_tui = MagicMock()
        mock_status = MagicMock()
        mock_tui.status = mock_status

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            event_handlers_module.handle_status_update(status_update_event)

        # Then
        mock_status.update.assert_called_once()
        status_text = mock_status.update.call_args[0][0]
        assert "test-agent" in status_text
        assert "openai/gpt-4" in status_text
        assert "high" in status_text
        assert "1,500" in status_text
        assert "8,000" in status_text
        assert "0.05$" in status_text
        assert "18.8%" in status_text

    def test_handle_status_update_with_none_context_size_shows_question_mark(
        self,
    ) -> None:
        # Given
        mock_tui = MagicMock()
        mock_status = MagicMock()
        mock_tui.status = mock_status
        event = StatusUpdateEvent(
            agent_name="agent1",
            provider="anthropic",
            model_id="claude-3",
            thinking_level="MEDIUM",
            total_tokens=500,
            context_size=None,
            cost=0.02,
        )

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            event_handlers_module.handle_status_update(event)

        # Then
        status_text = mock_status.update.call_args[0][0]
        assert "?" in status_text
        assert "500" in status_text
        # No percentage when context_size is None
        assert "%" not in status_text

    def test_handle_status_update_without_tui_status_attribute_does_not_raise(
        self,
    ) -> None:
        # Given
        mock_tui = MagicMock(spec=[])  # Empty spec means no attributes
        event = StatusUpdateEvent(
            agent_name="agent",
            provider="test",
            model_id="test-model",
            thinking_level="LOW",
            total_tokens=100,
            context_size=1000,
            cost=0.01,
        )

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            event_handlers_module.handle_status_update(event)

        # Then - no exception raised

    def test_handle_status_update_with_zero_total_tokens_shows_correct_format(
        self,
    ) -> None:
        # Given
        mock_tui = MagicMock()
        mock_status = MagicMock()
        mock_tui.status = mock_status
        event = StatusUpdateEvent(
            agent_name="new-agent",
            provider="google",
            model_id="gemini",
            thinking_level="Low",
            total_tokens=0,
            context_size=4096,
            cost=0.00,
        )

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            event_handlers_module.handle_status_update(event)

        # Then
        status_text = mock_status.update.call_args[0][0]
        assert "0" in status_text
        assert "0.00$" in status_text
        assert "0.0%" in status_text

    def test_handle_status_update_with_large_token_counts_formats_with_commas(
        self,
    ) -> None:
        # Given
        mock_tui = MagicMock()
        mock_status = MagicMock()
        mock_tui.status = mock_status
        event = StatusUpdateEvent(
            agent_name="big-agent",
            provider="anthropic",
            model_id="claude-3-opus",
            thinking_level="HIGH",
            total_tokens=1234567,
            context_size=2000000,
            cost=12.34,
        )

        # When
        with patch(TUI_PATCH_PATH, mock_tui):
            event_handlers_module.handle_status_update(event)

        # Then
        status_text = mock_status.update.call_args[0][0]
        assert "1,234,567" in status_text
        assert "2,000,000" in status_text
        assert "12.34$" in status_text
