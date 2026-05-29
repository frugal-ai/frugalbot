import asyncio
import inspect
import weakref
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TypeVar

T_Response = TypeVar("T_Response")


@dataclass
class _AwaitableEventBase[T_Response]:
    future: asyncio.Future[T_Response] = field(default_factory=lambda: asyncio.get_event_loop().create_future(), init=False)


class QuestionType(Enum):
    OK_ONLY = 1
    YES_NO = 2
    YES_NO_ALWAYS = 3


class QuestionResponse(Enum):
    UNDEFINED = 1
    YES = 2
    NO = 3
    ALWAYS = 4
    OK = 5


@dataclass(slots=True)
class _UserInteractionBase[T_Response](_AwaitableEventBase[T_Response]):
    """Base class for events that pause for user feedback."""

    prompt: str


@dataclass(slots=True)
class UserChoiceInteractionEvent(_UserInteractionBase[QuestionResponse]):
    question_type: QuestionType


@dataclass(slots=True)
class UserTextInteractionEvent(_UserInteractionBase[str]):
    pass


@dataclass(slots=True)
class UserCompositeInteractionEvent(_UserInteractionBase[tuple[QuestionResponse, str]]):
    question_type: QuestionType
    follow_up_prompt: str


class MessageType(Enum):
    INFO = 1
    WARNING = 2
    ERROR = 3
    USER = 4
    ASSISTANT = 5
    THINKING = 6
    TOOL_CALL = 7
    TOOL_OUTPUT = 8
    SYSTEM = 9


class MessageMarkup(Enum):
    NONE = 1
    MARKDOWN = 2
    YAML = 3
    JSON = 4


@dataclass(slots=True)
class MessageEvent:
    message: str
    message_type: MessageType
    message_markup: MessageMarkup = MessageMarkup.NONE
    is_stream: bool = False


@dataclass(slots=True)
class BulkMessageEvent:
    messages: list[MessageEvent] = field(default_factory=list)


@dataclass(slots=True)
class StatusUpdateEvent:
    agent_name: str
    provider: str
    model_id: str
    thinking_level: str
    total_tokens: int
    context_size: int | None
    cost: float


InteractionEvent = UserChoiceInteractionEvent | UserTextInteractionEvent | UserCompositeInteractionEvent

Event = MessageEvent | StatusUpdateEvent | BulkMessageEvent | InteractionEvent
T = TypeVar("T", bound="Event")
Handler = Callable[[T], Awaitable[None] | None]


class HandlerPriority(Enum):
    HIGHEST = 1
    HIGH = 10
    MEDIUM = 50
    LOW = 100
    LOWEST = 1000


@dataclass(slots=True)
class HandlerEntry:
    handler: Handler | weakref.ReferenceType[Handler]
    priority: HandlerPriority


class EventBus:
    def __init__(self):
        self._handlers: dict[type[Event], list[HandlerEntry]] = {}

    def clear_subscribers(self):
        self._handlers.clear()

    def subscribe(self, event_type: type[T], priority: HandlerPriority = HandlerPriority.HIGH) -> Callable[[Callable[[T], Awaitable[None] | None]], Callable[[T], Awaitable[None] | None]]:
        """Decorator for registering a standalone function as an event handler for the specified event type. To register class methods, use subscribe_class_method() in your class __init__()."""

        def decorator(fn: Callable[[T], Awaitable[None] | None]):
            self._handlers.setdefault(event_type, []).append(HandlerEntry(fn, priority))
            return fn

        return decorator

    def subscribe_class_method(self, event_type: type[T], handler: Callable[[T], Awaitable[None] | None], priority: HandlerPriority = HandlerPriority.HIGH):
        """Register a class method as an event handler for the specified event type. Should be called from the class' __init__()."""
        if inspect.ismethod(handler):
            ref = weakref.WeakMethod(handler)
        else:
            ref = weakref.ref(handler)
        self._handlers.setdefault(event_type, []).append(HandlerEntry(ref, priority))

    async def emit_and_handle(self, event: Event) -> None:
        handlers = self._handlers.get(type(event), [])
        handlers.sort(key=lambda e: e.priority.value)
        for entry in handlers:
            if isinstance(entry.handler, weakref.ReferenceType):
                handler = entry.handler()
            else:
                handler = entry.handler
            if handler is not None:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
        if isinstance(event, _AwaitableEventBase):
            await event.future


bus = EventBus()
