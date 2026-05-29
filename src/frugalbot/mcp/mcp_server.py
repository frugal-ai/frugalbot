import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Implementation, Tool

from frugalbot.mcp.mcp_server_config import MCPServerConfig
from frugalbot.mcp.mcp_session import MCPSession


class MCPServer:
    def __init__(self, name: str, config: MCPServerConfig):
        self.name = name
        self.config = config
        self.tools: list[Tool] | None = None

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[MCPSession]:
        server_params = StdioServerParameters(
            command=self.config.command[0],
            args=self.config.command[1:],
            env=self.config.env if self.config.env else None,
            cwd=self.config.cwd,
        )
        async with asyncio.timeout(self.config.connection_timeout) as timeout:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(
                    read,
                    write,
                    client_info=Implementation(name="frugalbot", version="0.1.0"),
                ) as session:
                    await session.initialize()
                    timeout.reschedule(None)
                    yield MCPSession(session, self.config.execution_timeout)
