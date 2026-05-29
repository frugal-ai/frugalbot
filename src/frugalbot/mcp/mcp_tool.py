from typing import Any, ClassVar

import jsonschema
import mcp

from frugalbot.events import MessageEvent, MessageMarkup, MessageType, bus
from frugalbot.mcp.mcp_session import MCPSession
from frugalbot.mcp.mcp_tool_result import MCPToolResult
from frugalbot.tools.base import ToolBase, ToolConfig
from frugalbot.utils.json import json_to_readable_yaml


def _clean_schema(schema: dict[str, Any]):
    """
    Recursively removes keys that are incompatible with LLM APIs
    strict client-side validation (such as additionalProperties and $schema).
    """
    if not isinstance(schema, dict):
        return schema

    # Keys to omit from any level of the schema dictionary
    unsupported_keys = {"additionalProperties", "additional_properties", "$schema"}

    cleaned = {}
    for key, val in schema.items():
        if key in unsupported_keys:
            continue

        # Recursively clean nested dictionaries and lists of dictionaries
        if isinstance(val, dict):
            cleaned[key] = _clean_schema(val)
        elif isinstance(val, list):
            cleaned[key] = [_clean_schema(item) if isinstance(item, dict) else item for item in val]
        else:
            cleaned[key] = val

    return cleaned


class MCPTool(ToolBase[MCPToolResult]):
    """Wraps a single MCP-discovered tool as a ToolBase instance."""

    _skip_registry: ClassVar[bool] = True

    def __init__(self, config: ToolConfig, server_name: str, session: MCPSession, tool: mcp.types.Tool):
        super().__init__(config)
        self._server_name = server_name
        self._session = session
        self._tool = tool

    @property
    def mcp_server_name(self) -> str:
        return self._server_name

    @property
    def mcp_tool_name(self) -> str:
        return self._tool.name

    @property
    def name(self) -> str:
        return f"{self._server_name}.{self._tool.name}"

    @property
    def description(self) -> str:
        return self._tool.description or "No description available"

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": _clean_schema(self._tool.inputSchema),
            },
        }

    def get_guidelines(self) -> list[str]:
        return []

    def validate_args(self, args: dict[str, Any]) -> None:
        jsonschema.validate(args, self._tool.inputSchema)

    async def run(self, *args: Any, **kwargs: dict[str, Any]) -> MCPToolResult:
        """Delegate to MCP server. Accepts *args for signature compatibility with ToolBase."""
        result = await self._session.call_tool(self._tool.name, kwargs)
        await bus.emit_and_handle(MessageEvent(json_to_readable_yaml(result.model_dump_json()), MessageType.TOOL_OUTPUT, MessageMarkup.YAML))
        return result
