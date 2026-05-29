from frugalbot.events import MessageEvent, MessageMarkup, MessageType, bus
from frugalbot.mcp.mcp_server_config import MCPServerConfig
from frugalbot.mcp.mcp_session import MCPSession
from frugalbot.mcp.mcp_tool import MCPTool
from frugalbot.tools.base import ToolConfig


class MCPSessions:
    def __init__(self, configs: dict[str, MCPServerConfig], sessions: dict[str, MCPSession]):
        self._configs = configs
        self._sessions: dict[str, MCPSession] = sessions
        self._tools: list[MCPTool] | None = None

    async def get_tools(self) -> list[MCPTool]:
        """Discover tools from all active server sessions."""
        if self._tools is not None:
            return self._tools
        errors = []
        self._tools = []
        for server_name, session in self._sessions.items():
            try:
                tools = await session.list_tools()
                for tool in tools:
                    if server_name not in self._configs:
                        raise KeyError(f"No config found for MCP server '{server_name}'")
                    enabled = not self._configs[server_name].enabled_tools or tool.name in self._configs[server_name].enabled_tools
                    self._tools.append(MCPTool(ToolConfig(enabled=enabled), server_name, session, tool))
            except Exception as e:
                errors.append(f"- Failed to discover tools from '{server_name}': {e}")
        if errors:
            await bus.emit_and_handle(
                MessageEvent(
                    "\n".join(errors),
                    MessageType.ERROR,
                    MessageMarkup.NONE,
                )
            )
        return self._tools
