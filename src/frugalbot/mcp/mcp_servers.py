import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass, field

from frugalbot.events import MessageEvent, MessageMarkup, MessageType, bus
from frugalbot.mcp.mcp_server import MCPServer
from frugalbot.mcp.mcp_server_config import MCPServerConfig
from frugalbot.mcp.mcp_session import MCPSession
from frugalbot.mcp.mcp_sessions import MCPSessions


# entering / exiting from the async connect context must be done from the same asyncio task due to the mcp library implementation
@dataclass(slots=True)
class _ConnectDisconnectTaskContext:
    connected_event: asyncio.Event = field(default_factory=asyncio.Event)
    disconnect_request_event: asyncio.Event = field(default_factory=asyncio.Event)
    servers: dict[str, MCPServer] = field(default_factory=dict)
    sessions: MCPSessions | None = None
    errors: list[str] = field(default_factory=list)
    exit_stack: AsyncExitStack = field(default_factory=AsyncExitStack)
    task: asyncio.Task | None = None


async def _connect_one(server: MCPServer, exit_stack: AsyncExitStack) -> tuple[str, MCPSession | None, str | None]:
    """Connect to a single server. Returns (name, session, error)."""
    try:
        session = await exit_stack.enter_async_context(server.connect())
        return (server.name, session, None)
    except TimeoutError:
        return (server.name, None, f"MCP server '{server.name}' failed to connect within configured timeout")
    except Exception as e:
        return (server.name, None, f"MCP server '{server.name}' failed to connect: {e}")


async def _runner_task(ctx: _ConnectDisconnectTaskContext) -> None:
    """Connect to all configured servers."""
    try:
        sessions: dict[str, MCPSession] = {}
        for server in list(ctx.servers.values()):
            server_name, session, error = await _connect_one(server, ctx.exit_stack)
            if session is not None:
                sessions[server_name] = session
            elif error is not None:
                ctx.servers.pop(server_name)
                ctx.errors.append(f"- {error}")

        configs = {name: server.config for name, server in ctx.servers.items()}
        ctx.sessions = MCPSessions(configs, sessions) if sessions else None
        ctx.connected_event.set()
        await ctx.disconnect_request_event.wait()
    finally:
        await ctx.exit_stack.aclose()


class MCPServers:
    def __init__(self):
        self._servers: dict[str, MCPServer] = {}
        self._contexts: list[_ConnectDisconnectTaskContext] = []
        self._exit_stack = None

    def _is_server_running(self, name: str) -> bool:
        for ctx in self._contexts:
            if name in ctx.servers:
                return True
        return False

    async def connect_all(self, config: dict[str, MCPServerConfig]) -> MCPSessions | None:
        ctx = _ConnectDisconnectTaskContext()

        ctx.servers = {name: MCPServer(name, config) for name, config in config.items() if config.enabled and not self._is_server_running(name)}
        if not ctx.servers:
            return None

        ctx.task = asyncio.create_task(_runner_task(ctx))
        self._contexts.append(ctx)
        await ctx.connected_event.wait()

        if ctx.errors:
            await bus.emit_and_handle(
                MessageEvent(
                    f"[red]✗[/] One or more errors occurred while connecting to MCP server(s):\n{'\n'.join(ctx.errors)}\n\nAffected MCP server(s) will not be available.",
                    MessageType.ERROR,
                    MessageMarkup.NONE,
                )
            )
        return ctx.sessions

    async def disconnect_all(self) -> None:
        for ctx in reversed(self._contexts):
            ctx.disconnect_request_event.set()
            if ctx.task:
                await ctx.task
        self._contexts.clear()
