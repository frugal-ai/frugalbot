from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar, Self

import pydantic

from frugalbot.utils.loader import load_dynamic_modules_with_config
from frugalbot.utils.typing import get_generic_type_of_base_class

if TYPE_CHECKING:
    from frugalbot.agent import Agent
    from frugalbot.conversation import Conversation

DEFAULT_HOOKS_PACKAGE = "frugalbot.hooks"


class HookError(Exception):
    """Base exception for hook-related errors."""


class HookConfig(pydantic.BaseModel):
    enabled: bool = True


class ApprovalState(Enum):
    APPROVED = 1
    DENIED = 2
    NOT_SET = 3


@dataclass(slots=True)
class PreUserMessageHook:
    content: str


@dataclass(slots=True)
class PreSystemMessageHook:
    content: str


@dataclass(slots=True)
class AgentStopHook:
    conversation: Conversation
    continue_conversation: bool = False


@dataclass(slots=True)
class AgentFinishedHook:
    agent: Agent
    run_again: bool = False


@dataclass(slots=True)
class PreToolCallHook:
    tool_name: str
    arguments: dict[str, Any]
    state: ApprovalState = ApprovalState.NOT_SET
    denied_reason: str = ""


@dataclass(slots=True)
class PostToolCallHook:
    tool_name: str
    result_json: str


@dataclass(slots=True)
class PreRenderSystemPromptHook:
    prompt_template: str
    prompt_arguments: dict[str, str]


@dataclass(slots=True)
class PreRenderUserPromptHook:
    prompt_template: str
    prompt_arguments: dict[str, str]


HookType = PreUserMessageHook | PreSystemMessageHook | AgentStopHook | PreToolCallHook | PostToolCallHook | PreRenderSystemPromptHook | PreRenderUserPromptHook | AgentFinishedHook


class HookPriority(Enum):
    HIGHEST = 1
    HIGH = 10
    MEDIUM = 50
    LOW = 100
    LOWEST = 1000


class HookBase[T: HookType, ConfigType: HookConfig]:
    _registry: ClassVar[list[type[Self]]] = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        HookBase._registry.append(cls)

    def __init__(self, config: ConfigType) -> None:
        self._config = config

    @property
    def config(self) -> ConfigType:
        return self._config

    @property
    def name(self) -> str:
        return type(self).__name__.lower()

    async def run(self, hook_data: T): ...

    @property
    def priority(self) -> HookPriority:
        return HookPriority.HIGH


class Hooks:
    def __init__(self) -> None:
        self._hooks_registry: dict[str, HookBase] = {}

    def _get_hook_type(self, hook: HookBase) -> type | None:
        return get_generic_type_of_base_class(hook, HookBase, 0)

    def _get_hook_config_type(self, hook: HookBase) -> type | None:
        return get_generic_type_of_base_class(hook, HookBase, 1)

    def _register(self, name: str, tool: HookBase) -> None:
        self._hooks_registry[name] = tool

    def load(self, hooks_config: dict[str, dict[str, Any]]):
        load_dynamic_modules_with_config(
            default_package_name=DEFAULT_HOOKS_PACKAGE,
            base_cls=HookBase,
            config_base_cls=HookConfig,
            error_cls=HookError,
            register_fn=self._register,
            config_dict=hooks_config,
            module_type_name="hook",
        )

    def unload(self):
        HookBase._registry.clear()
        self._hooks_registry.clear()

    async def run(self, hook_data: HookType):
        hooks_to_run: list[HookBase] = []
        for hook in self._hooks_registry.values():
            if issubclass(type(hook.config), HookConfig) and not hook.config.enabled:
                continue
            hook_type = self._get_hook_type(hook)
            if hook_type is None:
                continue
            if isinstance(hook_data, hook_type):
                hooks_to_run.append(hook)
        hooks_to_run.sort(key=lambda h: h.priority.value)
        for hook in hooks_to_run:
            await hook.run(hook_data)
