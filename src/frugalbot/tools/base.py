import inspect
from collections.abc import Iterable
from typing import Any, ClassVar, Self, get_type_hints

import jsonschema
import pydantic

from frugalbot.utils.loader import load_dynamic_modules_with_config
from frugalbot.utils.typing import python_type_to_json_schema

__all__ = ["ToolBase", "ToolError", "Tools"]


DEFAULT_TOOLS_PACKAGE = "frugalbot.tools"


class ToolError(Exception):
    """Base exception for tool-related errors."""


class ToolConfig(pydantic.BaseModel):
    enabled: bool = True


class ToolBase[ResultType: pydantic.BaseModel, ConfigType: ToolConfig = ToolConfig]:
    """Base protocol for all tools. T is the type of result returned by the tool. U is the type of config."""

    _registry: ClassVar[list[type[Self]]] = []
    _skip_registry: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls._skip_registry:
            ToolBase._registry.append(cls)

    def __init__(self, config: ConfigType) -> None:
        self._config = config

    def get_schema(self) -> dict[str, Any]:
        hints = get_type_hints(type(self).run, include_extras=True)
        properties = {}
        sig = inspect.signature(type(self).run)
        for param, hint in hints.items():
            if param in ("return", "self"):
                continue
            metadata = getattr(hint, "__metadata__", None)
            if not metadata:
                raise TypeError(f"All parameters of the tool must be annotated with Annotated and include a description. Missing description for parameter '{param}' in tool '{type(self).__name__}'.")
            properties[param] = python_type_to_json_schema(hint)
            properties[param]["description"] = metadata[0]
            if sig.parameters[param].default is not inspect.Parameter.empty:
                properties[param]["description"] += f" (default: {sig.parameters[param].default})"
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": [param_name for param_name, param in sig.parameters.items() if param.default is param.empty and param_name != "self"],
                },
            },
        }

    def get_guidelines(self) -> list[str]:
        """Return any special guidelines for using this tool, or an empty string if there are none."""
        return []

    @property
    def config(self) -> ConfigType:
        return self._config

    @property
    def name(self) -> str:
        return type(self).__name__.lower()

    @property
    def description(self) -> str:
        return self.__doc__ or ""

    async def run(self, *args, **kwargs) -> ResultType: ...

    def validate_args(self, args: dict[str, Any]) -> None:
        jsonschema.validate(args, self.get_schema()["function"]["parameters"])


class Tools:
    def __init__(self) -> None:
        self._tools_registry: dict[str, ToolBase] = {}

    def _register_tool(self, name: str, tool: ToolBase) -> None:
        self._tools_registry[name] = tool

    def load(self, tools_config: dict[str, dict[str, Any]]):
        load_dynamic_modules_with_config(
            default_package_name=DEFAULT_TOOLS_PACKAGE,
            base_cls=ToolBase,
            config_base_cls=ToolConfig,
            error_cls=ToolError,
            register_fn=self._register_tool,
            config_dict=tools_config,
            module_type_name="tool",
        )

    def add(self, tools: list[ToolBase] | ToolBase) -> None:
        if isinstance(tools, ToolBase):
            tools = [tools]
        for tool in tools:
            self._tools_registry[tool.name] = tool

    def unload(self):
        ToolBase._registry.clear()
        self._tools_registry.clear()

    def get_all(self) -> Iterable[ToolBase]:
        return [tool for tool in self._tools_registry.values() if tool.config.enabled]

    def get(self, tool_name: str) -> ToolBase:
        if tool_name not in self._tools_registry:
            raise KeyError(f"Invalid tool name: '{tool_name}'")
        tool = self._tools_registry[tool_name]
        if not tool.config.enabled:
            raise ValueError(f"Tool {tool_name} is disabled")
        return tool
