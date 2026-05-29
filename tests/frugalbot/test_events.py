import asyncio
import gc

from frugalbot.events import (
    BulkMessageEvent,
    EventBus,
    HandlerEntry,
    HandlerPriority,
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

# =============================================================================
# Event Dataclass Tests
# =============================================================================


def test_message_event_with_defaults_sets_none_markup_and_not_stream() -> None:
    # Given
    message = "Processing complete"
    message_type = MessageType.INFO

    # When
    event = MessageEvent(message=message, message_type=message_type)

    # Then
    assert event.message == "Processing complete"
    assert event.message_type == MessageType.INFO
    assert event.message_markup == MessageMarkup.NONE
    assert event.is_stream is False


def test_message_event_with_all_fields_stores_values() -> None:
    # Given
    message = "```python\nprint('hi')\n```"
    message_type = MessageType.ASSISTANT
    message_markup = MessageMarkup.MARKDOWN
    is_stream = True

    # When
    event = MessageEvent(
        message=message,
        message_type=message_type,
        message_markup=message_markup,
        is_stream=is_stream,
    )

    # Then
    assert event.message_markup == MessageMarkup.MARKDOWN
    assert event.is_stream is True


def test_bulk_message_event_with_default_creates_empty_list() -> None:
    # Given / When
    event = BulkMessageEvent()

    # Then
    assert event.messages == []


def test_bulk_message_event_with_messages_stores_list() -> None:
    # Given
    messages = [
        MessageEvent("Hello", MessageType.USER),
        MessageEvent("Hi back", MessageType.ASSISTANT),
    ]

    # When
    event = BulkMessageEvent(messages=messages)

    # Then
    assert len(event.messages) == 2


def test_status_update_event_with_values_stores_data() -> None:
    # Given
    agent_name = "main"
    provider = "openai"
    model_id = "gpt-4"
    thinking_level = "medium"
    total_tokens = 1500
    context_size = 8000
    cost = 0.03

    # When
    event = StatusUpdateEvent(
        agent_name=agent_name,
        provider=provider,
        model_id=model_id,
        thinking_level=thinking_level,
        total_tokens=total_tokens,
        context_size=context_size,
        cost=cost,
    )

    # Then
    assert event.agent_name == "main"
    assert event.provider == "openai"
    assert event.model_id == "gpt-4"
    assert event.thinking_level == "medium"
    assert event.total_tokens == 1500
    assert event.context_size == 8000
    assert event.cost == 0.03


def test_status_update_event_with_none_context_size_stores_none() -> None:
    # Given / When
    event = StatusUpdateEvent(
        agent_name="agent1",
        provider="anthropic",
        model_id="claude-3",
        thinking_level="low",
        total_tokens=500,
        context_size=None,
        cost=0.01,
    )

    # Then
    assert event.context_size is None


async def test_user_choice_interaction_event_with_prompt_creates_future() -> None:
    # Given
    prompt = "Approve this action?"

    # When
    event = UserChoiceInteractionEvent(prompt=prompt, question_type=QuestionType.YES_NO)

    # Then
    assert event.prompt == "Approve this action?"
    assert event.question_type == QuestionType.YES_NO
    assert isinstance(event.future, asyncio.Future)


async def test_user_text_interaction_event_with_prompt_creates_future() -> None:
    # Given
    prompt = "Enter your name:"

    # When
    event = UserTextInteractionEvent(prompt=prompt)

    # Then
    assert event.prompt == "Enter your name:"
    assert isinstance(event.future, asyncio.Future)


async def test_user_composite_interaction_event_with_follow_up_stores_data() -> None:
    # Given
    prompt = "Continue?"
    follow_up = "Enter reason:"

    # When
    event = UserCompositeInteractionEvent(
        prompt=prompt,
        question_type=QuestionType.YES_NO,
        follow_up_prompt=follow_up,
    )

    # Then
    assert event.prompt == "Continue?"
    assert event.question_type == QuestionType.YES_NO
    assert event.follow_up_prompt == "Enter reason:"
    assert isinstance(event.future, asyncio.Future)


# =============================================================================
# Enum Tests
# =============================================================================


def test_question_type_has_three_values() -> None:
    # Given / When / Then
    assert QuestionType.OK_ONLY.value == 1
    assert QuestionType.YES_NO.value == 2
    assert QuestionType.YES_NO_ALWAYS.value == 3


def test_question_response_has_five_values() -> None:
    # Given / When / Then
    assert QuestionResponse.UNDEFINED.value == 1
    assert QuestionResponse.YES.value == 2
    assert QuestionResponse.NO.value == 3
    assert QuestionResponse.ALWAYS.value == 4
    assert QuestionResponse.OK.value == 5


def test_message_type_has_all_variants() -> None:
    # Given / When / Then
    assert MessageType.INFO.value == 1
    assert MessageType.WARNING.value == 2
    assert MessageType.ERROR.value == 3
    assert MessageType.USER.value == 4
    assert MessageType.ASSISTANT.value == 5
    assert MessageType.THINKING.value == 6
    assert MessageType.TOOL_CALL.value == 7
    assert MessageType.TOOL_OUTPUT.value == 8
    assert MessageType.SYSTEM.value == 9


def test_message_markup_has_all_variants() -> None:
    # Given / When / Then
    assert MessageMarkup.NONE.value == 1
    assert MessageMarkup.MARKDOWN.value == 2
    assert MessageMarkup.YAML.value == 3
    assert MessageMarkup.JSON.value == 4


def test_handler_priority_has_correct_ordering() -> None:
    # Given / When / Then
    assert HandlerPriority.HIGHEST.value == 1
    assert HandlerPriority.HIGH.value == 10
    assert HandlerPriority.MEDIUM.value == 50
    assert HandlerPriority.LOW.value == 100
    assert HandlerPriority.LOWEST.value == 1000


# =============================================================================
# EventBus - Basic Subscription Tests
# =============================================================================


async def test_event_bus_subscribe_with_single_handler_invokes_handler() -> None:
    # Given
    bus = EventBus()
    handler_called = False

    def handler(event: MessageEvent) -> None:
        nonlocal handler_called
        handler_called = True

    bus.subscribe(MessageEvent)(handler)

    # When
    await bus.emit_and_handle(MessageEvent(message="Test", message_type=MessageType.INFO))

    # Then
    assert handler_called is True


async def test_event_bus_subscribe_with_decorator_syntax_invokes_handler() -> None:
    # Given
    bus = EventBus()
    handler_called = False

    @bus.subscribe(MessageEvent)
    def handler(event: MessageEvent) -> None:
        nonlocal handler_called
        handler_called = True

    # When
    await bus.emit_and_handle(MessageEvent(message="System", message_type=MessageType.SYSTEM))

    # Then
    assert handler_called is True


async def test_event_bus_subscribe_with_async_handler_awaits_handler() -> None:
    # Given
    bus = EventBus()
    handler_called = False

    async def handler(event: MessageEvent) -> None:
        nonlocal handler_called
        handler_called = True

    bus.subscribe(MessageEvent)(handler)

    # When
    await bus.emit_and_handle(MessageEvent(message="Async test", message_type=MessageType.INFO))

    # Then
    assert handler_called is True


async def test_event_bus_subscribe_with_no_handlers_does_not_raise() -> None:
    # Given
    bus = EventBus()

    # When / Then (no exception raised)
    await bus.emit_and_handle(MessageEvent(message="No one is listening", message_type=MessageType.INFO))


async def test_event_bus_subscribe_with_different_events_only_invokes_matching_handler() -> None:
    # Given
    bus = EventBus()
    info_handled = False
    warning_handled = False

    @bus.subscribe(MessageEvent)
    def handler_info(_: MessageEvent) -> None:
        nonlocal info_handled
        info_handled = True

    @bus.subscribe(StatusUpdateEvent)
    def handler_warning(_: StatusUpdateEvent) -> None:
        nonlocal warning_handled
        warning_handled = True

    # When
    await bus.emit_and_handle(MessageEvent(message="User", message_type=MessageType.INFO))

    # Then
    assert info_handled is True
    assert warning_handled is False


async def test_event_bus_subscribe_with_multiple_handlers_for_same_event_invokes_all() -> None:
    # Given
    bus = EventBus()
    call_count = 0

    def handler1(event: MessageEvent) -> None:
        nonlocal call_count
        call_count += 1

    def handler2(event: MessageEvent) -> None:
        nonlocal call_count
        call_count += 1

    bus.subscribe(MessageEvent)(handler1)
    bus.subscribe(MessageEvent)(handler2)

    # When
    await bus.emit_and_handle(MessageEvent(message="Test", message_type=MessageType.INFO))

    # Then
    assert call_count == 2


# =============================================================================
# EventBus - Handler Priority Tests
# =============================================================================


async def test_event_bus_emit_with_mixed_priorities_invokes_in_priority_order() -> None:
    # Given
    bus = EventBus()
    call_order: list[str] = []

    def low_handler(event: MessageEvent) -> None:
        call_order.append("low")

    def high_handler(event: MessageEvent) -> None:
        call_order.append("high")

    def medium_handler(event: MessageEvent) -> None:
        call_order.append("medium")

    bus.subscribe(MessageEvent, priority=HandlerPriority.LOW)(low_handler)
    bus.subscribe(MessageEvent, priority=HandlerPriority.HIGH)(high_handler)
    bus.subscribe(MessageEvent, priority=HandlerPriority.MEDIUM)(medium_handler)

    # When
    await bus.emit_and_handle(MessageEvent(message="Priority test", message_type=MessageType.INFO))

    # Then
    assert call_order == ["high", "medium", "low"]


async def test_event_bus_emit_with_same_priority_invokes_in_registration_order() -> None:
    # Given
    bus = EventBus()
    call_order: list[str] = []

    def first_handler(event: MessageEvent) -> None:
        call_order.append("first")

    def second_handler(event: MessageEvent) -> None:
        call_order.append("second")

    bus.subscribe(MessageEvent, priority=HandlerPriority.HIGH)(first_handler)
    bus.subscribe(MessageEvent, priority=HandlerPriority.HIGH)(second_handler)

    # When
    await bus.emit_and_handle(MessageEvent(message="Order test", message_type=MessageType.INFO))

    # Then
    assert call_order == ["first", "second"]


# =============================================================================
# EventBus - Class Method Subscription Tests
# =============================================================================


async def test_event_bus_subscribe_class_method_with_instance_method_invokes_handler() -> None:
    # Given
    bus = EventBus()
    handler_called = False

    class EventHandler:
        def __init__(self) -> None:
            bus.subscribe_class_method(MessageEvent, self.handle_event)

        def handle_event(self, event: MessageEvent) -> None:
            nonlocal handler_called
            handler_called = True

    _ = EventHandler()

    # When
    await bus.emit_and_handle(MessageEvent(message="Class method test", message_type=MessageType.INFO))

    # Then
    assert handler_called is True


async def test_event_bus_subscribe_class_method_with_async_method_awaits_handler() -> None:
    # Given
    bus = EventBus()
    handler_called = False

    class AsyncEventHandler:
        def __init__(self) -> None:
            bus.subscribe_class_method(MessageEvent, self.handle_event)

        async def handle_event(self, event: MessageEvent) -> None:
            nonlocal handler_called
            handler_called = True

    _ = AsyncEventHandler()

    # When
    await bus.emit_and_handle(MessageEvent(message="Async class method", message_type=MessageType.INFO))

    # Then
    assert handler_called is True


async def test_event_bus_subscribe_class_method_with_collected_instance_does_not_invoke_handler() -> None:
    # Given
    bus = EventBus()
    handler_called = False

    class EphemeralHandler:
        def __init__(self) -> None:
            bus.subscribe_class_method(MessageEvent, self.handle_event)

        def handle_event(self, event: MessageEvent) -> None:
            nonlocal handler_called
            handler_called = True

    handler_instance = EphemeralHandler()
    del handler_instance
    gc.collect()

    # When
    await bus.emit_and_handle(MessageEvent(message="After gc", message_type=MessageType.INFO))

    # Then
    assert handler_called is False


async def test_event_bus_subscribe_class_method_with_priority_invokes_in_order() -> None:
    # Given
    bus = EventBus()
    call_order: list[str] = []

    class PriorityHandler:
        def __init__(self) -> None:
            bus.subscribe_class_method(MessageEvent, self.handle_low, priority=HandlerPriority.LOW)
            bus.subscribe_class_method(MessageEvent, self.handle_high, priority=HandlerPriority.HIGH)

        def handle_low(self, event: MessageEvent) -> None:
            call_order.append("low")

        def handle_high(self, event: MessageEvent) -> None:
            call_order.append("high")

    _ = PriorityHandler()

    # When
    await bus.emit_and_handle(MessageEvent(message="Priority class", message_type=MessageType.INFO))

    # Then
    assert call_order == ["high", "low"]


# =============================================================================
# EventBus - clear_subscribers Tests
# =============================================================================


async def test_event_bus_clear_subscribers_with_registered_handlers_removes_all_handlers() -> None:
    # Given
    bus = EventBus()
    handler_called = False

    @bus.subscribe(MessageEvent)
    def handler(event: MessageEvent) -> None:
        nonlocal handler_called
        handler_called = True

    bus.clear_subscribers()

    # When
    await bus.emit_and_handle(MessageEvent(message="After clear", message_type=MessageType.INFO))

    # Then
    assert handler_called is False


async def test_event_bus_clear_subscribers_with_no_handlers_does_not_raise() -> None:
    # Given
    bus = EventBus()

    # When / Then (no exception)
    bus.clear_subscribers()


# =============================================================================
# EventBus - Handler receives correct event data
# =============================================================================


async def test_event_bus_emit_with_message_event_passes_data_to_handler() -> None:
    # Given
    bus = EventBus()
    received_message: str | None = None

    def handler(event: MessageEvent) -> None:
        nonlocal received_message
        received_message = event.message

    bus.subscribe(MessageEvent)(handler)

    # When
    await bus.emit_and_handle(MessageEvent(message="Payload test", message_type=MessageType.INFO))

    # Then
    assert received_message == "Payload test"


async def test_event_bus_emit_with_message_event_passes_type_to_handler() -> None:
    # Given
    bus = EventBus()
    received_type: MessageType | None = None

    def handler(event: MessageEvent) -> None:
        nonlocal received_type
        received_type = event.message_type

    bus.subscribe(MessageEvent)(handler)

    # When
    await bus.emit_and_handle(MessageEvent(message="Warning!", message_type=MessageType.WARNING))

    # Then
    assert received_type == MessageType.WARNING


async def test_event_bus_emit_with_status_update_event_passes_data_to_handler() -> None:
    # Given
    bus = EventBus()
    received_tokens: int | None = None

    def handler(event: StatusUpdateEvent) -> None:
        nonlocal received_tokens
        received_tokens = event.total_tokens

    bus.subscribe(StatusUpdateEvent)(handler)

    # When
    await bus.emit_and_handle(
        StatusUpdateEvent(
            agent_name="main",
            provider="openai",
            model_id="gpt-4",
            thinking_level="high",
            total_tokens=2000,
            context_size=8192,
            cost=0.05,
        )
    )

    # Then
    assert received_tokens == 2000


async def test_event_bus_emit_with_status_update_event_passes_agent_name_to_handler() -> None:
    # Given
    bus = EventBus()
    received_agent: str | None = None

    def handler(event: StatusUpdateEvent) -> None:
        nonlocal received_agent
        received_agent = event.agent_name

    bus.subscribe(StatusUpdateEvent)(handler)

    # When
    await bus.emit_and_handle(
        StatusUpdateEvent(
            agent_name="worker",
            provider="anthropic",
            model_id="claude-3",
            thinking_level="low",
            total_tokens=100,
            context_size=4096,
            cost=0.01,
        )
    )

    # Then
    assert received_agent == "worker"


async def test_event_bus_emit_with_bulk_message_event_passes_messages_to_handler() -> None:
    # Given
    bus = EventBus()
    received_count: int | None = None

    def handler(event: BulkMessageEvent) -> None:
        nonlocal received_count
        received_count = len(event.messages)

    bus.subscribe(BulkMessageEvent)(handler)
    bulk_event = BulkMessageEvent(
        messages=[
            MessageEvent("msg1", MessageType.USER),
            MessageEvent("msg2", MessageType.ASSISTANT),
            MessageEvent("msg3", MessageType.INFO),
        ]
    )

    # When
    await bus.emit_and_handle(bulk_event)

    # Then
    assert received_count == 3


# =============================================================================
# HandlerEntry Tests
# =============================================================================


def test_handler_entry_with_function_stores_handler_and_priority() -> None:
    # Given
    def my_handler(event: MessageEvent) -> None:
        pass

    # When
    entry = HandlerEntry(handler=my_handler, priority=HandlerPriority.MEDIUM)

    # Then
    assert entry.handler is my_handler
    assert entry.priority == HandlerPriority.MEDIUM


def test_handler_entry_with_high_priority_stores_values() -> None:
    # Given
    def my_handler(event: MessageEvent) -> None:
        pass

    # When
    entry = HandlerEntry(handler=my_handler, priority=HandlerPriority.HIGH)

    # Then
    assert entry.priority == HandlerPriority.HIGH
