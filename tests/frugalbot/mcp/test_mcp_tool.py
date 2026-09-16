from typing import Any, cast
from unittest.mock import MagicMock

import mcp.types as types

from frugalbot.mcp.mcp_session import MCPSession
from frugalbot.mcp.mcp_tool import MCPTool
from frugalbot.tools.base import ToolConfig


def _make_mcp_tool(input_schema: dict[str, Any]) -> MCPTool:
    session = MCPSession(session=cast(Any, MagicMock()), timeout=1.0)
    tool = types.Tool.model_validate({"name": "echo", "description": "Echoes input", "inputSchema": input_schema})
    return MCPTool(ToolConfig(), "server", session, tool)


def test_validate_args_with_valid_args_returns_normalized_args() -> None:
    # Given
    tool = _make_mcp_tool({"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]})
    args = {"text": "hello"}

    # When
    result = tool.validate_args(args)

    # Then
    assert result == {"text": "hello"}
