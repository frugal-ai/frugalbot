import math
import traceback
from typing import Any, ClassVar, Self

from any_llm.types.completion import ChatCompletion
from pydantic import BaseModel
from tenacity import RetryCallState

from frugalbot.config import ThinkingLevel
from frugalbot.conversation import Conversation
from frugalbot.events import MessageEvent, MessageType, bus
from frugalbot.tools.base import Tools
from frugalbot.utils.loader import load_dynamic_modules_with_config

DEFAULT_CLIENTS_PACKAGE = "frugalbot.clients"
DEFAULT_THINKING_LEVEL = "HIGH"


class LLMClientConfig(BaseModel):
    name: str


class LLMClientError(Exception):
    """Base exception for tool-related errors."""


class LLMClient[ConfigType: LLMClientConfig]:
    _registry: ClassVar[list[type[Self]]] = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        LLMClient._registry.append(cls)

    def __init__(self, config: ConfigType) -> None:
        self._config = config
        self._provider = ""
        self._model = ""
        self._thinking_level: ThinkingLevel = DEFAULT_THINKING_LEVEL

    async def call(self, conversation: Conversation, tools: Tools) -> ChatCompletion: ...

    @property
    def config(self) -> ConfigType:
        return self._config

    @property
    def provider(self) -> str:
        """Returns a models.dev provider ID."""
        return self._provider

    @provider.setter
    def provider(self, provider: str) -> None:
        self._provider = provider

    @property
    def model(self) -> str:
        """Returns the provider-specific model ID currently in use."""
        return self._model

    @model.setter
    def model(self, model: str) -> None:
        self._model = model

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def supports_thinking(self) -> bool:
        """Returns True if the provider supports thinking levels."""
        ...

    @property
    def thinking_level(self) -> ThinkingLevel:
        return self._thinking_level

    @thinking_level.setter
    def thinking_level(self, level: ThinkingLevel) -> None:
        self._thinking_level = level

    @property
    def base_url(self) -> str: ...


class LLMClients:
    def __init__(self) -> None:
        self._clients_registry: list[LLMClient] = []

    def _register(self, _: str, client: LLMClient) -> None:
        self._clients_registry.append(client)

    def load(self, config: dict[str, dict[str, Any]]) -> None:
        clients_config: dict[str, list[dict[str, Any]]] = {}
        for name, client_config in config.items():
            client_type = client_config.get("type")
            if client_type is None:
                if name == "all":
                    client_type = "all"
                else:
                    raise ValueError(f"'type' is mandatory for each client configuration section. No 'type' found in section 'client.{name}'.")
            clients_of_type = clients_config.setdefault(client_type, [])
            config_no_type = client_config.copy()
            if "type" in config_no_type:
                del config_no_type["type"]
            config_no_type["name"] = name
            clients_of_type.append(config_no_type)

        load_dynamic_modules_with_config(
            default_package_name=DEFAULT_CLIENTS_PACKAGE,
            base_cls=LLMClient,
            config_base_cls=LLMClientConfig,
            error_cls=LLMClientError,
            register_fn=self._register,
            config_dict=clients_config,
            module_type_name="client",
            skip_if_no_config=True,
        )

        order = list(clients_config.keys())
        client_names = []
        for client in self._clients_registry:
            name = client.__class__.__name__.lower()
            name = name if not name.endswith("client") else name[:-6]
            client_names.append(name)
        order_map = {name: i for i, name in enumerate(order)}
        self._clients_registry = [client for _, client in sorted(zip(client_names, self._clients_registry, strict=True), key=lambda pair: order_map.get(pair[0], math.inf))]

    def unload(self) -> None:
        self._clients_registry.clear()
        LLMClient._registry.clear()

    def get_all(self) -> list[LLMClient]:
        return self._clients_registry


async def log_retry(retry_state: RetryCallState, include_traceback: bool):
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    wait = retry_state.next_action.sleep if retry_state.next_action else 0.0
    attempt = retry_state.attempt_number
    if exc:
        tb_string = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        if include_traceback:
            error_details = f"{type(exc).__name__}: {exc}\n\n{tb_string}"
        else:
            error_details = str(exc)
    else:
        error_details = "Unknown error"
    await bus.emit_and_handle(MessageEvent(f"LLM API Call Failed. Attempt {attempt} failed.\n{error_details}\nWaiting {wait:.1f}s before attempt #{attempt + 1}...", MessageType.ERROR))
