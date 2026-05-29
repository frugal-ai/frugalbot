import asyncio
from typing import Any

import mcp

from frugalbot.mcp.mcp_tool_result import MCPToolResult


class MCPSession:
    def __init__(self, session: mcp.ClientSession, timeout: float):
        self.session = session
        self.timeout = timeout

    async def list_tools(self) -> list[mcp.types.Tool]:
        async with asyncio.timeout(self.timeout):
            result = await self.session.list_tools()
            return result.tools

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> MCPToolResult:
        async with asyncio.timeout(self.timeout):
            result = await self.session.call_tool(name, arguments=arguments if arguments is not None else {})
            return MCPToolResult(**result.model_dump())
