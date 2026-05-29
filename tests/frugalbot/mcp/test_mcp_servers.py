from collections.abc import Generator
from contextlib import AsyncExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from frugalbot.events import bus
from frugalbot.mcp.mcp_server_config import MCPServerConfig
from frugalbot.mcp.mcp_servers import MCPServers, _connect_one


@pytest.fixture(autouse=True)
def _clear_bus() -> Generator[None]:
    bus.clear_subscribers()
    yield
    bus.clear_subscribers()


def _make_async_cm_mock(yield_value: object = None, raise_exception: BaseException | None = None) -> AsyncMock:
    """Create a mock async context manager."""
    cm = AsyncMock()
    if raise_exception is not None:
        cm.__aenter__ = AsyncMock(side_effect=raise_exception)
    else:
        cm.__aenter__.return_value = yield_value
    cm.__aexit__.return_value = None
    return cm


def _make_mock_server(name: str, connect_cm: AsyncMock) -> MagicMock:
    """Create a mock MCPServer with the given name and connect context manager."""
    server = MagicMock()
    server.name = name
    server.connect.return_value = connect_cm
    return server


# =============================================================================
# _connect_one tests
# =============================================================================


async def test_connect_one_with_successful_connection_returns_session() -> None:
    # Given
    mock_session = AsyncMock()
    connect_cm = _make_async_cm_mock(yield_value=mock_session)
    server = _make_mock_server("test-server", connect_cm)
    exit_stack = AsyncExitStack()

    # When
    name, session, error = await _connect_one(server, exit_stack)

    # Then
    assert name == "test-server"
    assert session is mock_session
    assert error is None


@pytest.mark.parametrize(
    ("exception", "expected_error"),
    [
        (
            TimeoutError(),
            "MCP server 'test-server' failed to connect within configured timeout",
        ),
        (
            ConnectionError("refused"),
            "MCP server 'test-server' failed to connect: refused",
        ),
    ],
)
async def test_connect_one_with_connection_failure_returns_error(exception: BaseException, expected_error: str) -> None:
    # Given
    connect_cm = _make_async_cm_mock(raise_exception=exception)
    server = _make_mock_server("test-server", connect_cm)
    exit_stack = AsyncExitStack()

    # When
    name, session, error = await _connect_one(server, exit_stack)

    # Then
    assert name == "test-server"
    assert session is None
    assert error == expected_error


# =============================================================================
# MCPServers.connect_all tests
# =============================================================================


async def test_connect_all_with_empty_config_returns_none() -> None:
    # Given
    servers = MCPServers()

    # When
    result = await servers.connect_all({})

    # Then
    assert result is None


async def test_connect_all_with_all_disabled_servers_returns_none() -> None:
    # Given
    servers = MCPServers()
    config = {"server1": MCPServerConfig(command=["echo", "hello"], enabled=False)}

    # When
    result = await servers.connect_all(config)

    # Then
    assert result is None


async def test_connect_all_with_successful_connection_returns_sessions() -> None:
    # Given
    servers = MCPServers()
    config = {"server1": MCPServerConfig(command=["echo", "hello"])}
    mock_session = AsyncMock()
    connect_cm = _make_async_cm_mock(yield_value=mock_session)
    mock_server = _make_mock_server("server1", connect_cm)

    with patch("frugalbot.mcp.mcp_servers.MCPServer", return_value=mock_server):
        # When
        result = await servers.connect_all(config)

        # Then
        assert result is not None


async def test_connect_all_with_successful_connection_does_not_emit_error() -> None:
    # Given
    servers = MCPServers()
    config = {"server1": MCPServerConfig(command=["echo", "hello"])}
    mock_session = AsyncMock()
    connect_cm = _make_async_cm_mock(yield_value=mock_session)
    mock_server = _make_mock_server("server1", connect_cm)

    with patch("frugalbot.mcp.mcp_servers.MCPServer", return_value=mock_server):
        with patch.object(bus, "emit_and_handle", new_callable=AsyncMock) as mock_emit:
            # When
            await servers.connect_all(config)

            # Then
            mock_emit.assert_not_called()


async def test_connect_all_skips_already_running_server() -> None:
    # Given
    servers = MCPServers()
    config = {"server1": MCPServerConfig(command=["echo", "hello"])}
    mock_session = AsyncMock()
    connect_cm = _make_async_cm_mock(yield_value=mock_session)
    mock_server = _make_mock_server("server1", connect_cm)

    with patch("frugalbot.mcp.mcp_servers.MCPServer", return_value=mock_server):
        await servers.connect_all(config)

        # When
        result = await servers.connect_all(config)

        # Then
        assert result is None


async def test_connect_all_with_mixed_connections_returns_successful_sessions_only() -> None:
    # Given
    servers = MCPServers()
    config = {
        "good": MCPServerConfig(command=["echo", "hello"]),
        "bad": MCPServerConfig(command=["echo", "fail"]),
    }
    mock_session = AsyncMock()
    good_cm = _make_async_cm_mock(yield_value=mock_session)
    bad_cm = _make_async_cm_mock(raise_exception=ConnectionError("refused"))
    mock_good_server = _make_mock_server("good", good_cm)
    mock_bad_server = _make_mock_server("bad", bad_cm)

    with patch(
        "frugalbot.mcp.mcp_servers.MCPServer",
        side_effect=[mock_good_server, mock_bad_server],
    ):
        # When
        result = await servers.connect_all(config)

        # Then
        assert result is not None
        assert "good" in result._sessions
        assert "bad" not in result._sessions


async def test_connect_all_with_mixed_connections_does_not_emit_error_due_to_local_errors_list_bug() -> None:
    # Given
    servers = MCPServers()
    config = {
        "good": MCPServerConfig(command=["echo", "hello"]),
        "bad": MCPServerConfig(command=["echo", "fail"]),
    }
    mock_session = AsyncMock()
    good_cm = _make_async_cm_mock(yield_value=mock_session)
    bad_cm = _make_async_cm_mock(raise_exception=ConnectionError("refused"))
    mock_good_server = _make_mock_server("good", good_cm)
    mock_bad_server = _make_mock_server("bad", bad_cm)

    with patch(
        "frugalbot.mcp.mcp_servers.MCPServer",
        side_effect=[mock_good_server, mock_bad_server],
    ):
        with patch.object(bus, "emit_and_handle", new_callable=AsyncMock) as mock_emit:
            # When
            await servers.connect_all(config)

            # Then
            mock_emit.assert_called_once()


# =============================================================================
# MCPServers.disconnect_all tests
# =============================================================================


async def test_disconnect_all_completes_task() -> None:
    # Given
    servers = MCPServers()
    config = {"server1": MCPServerConfig(command=["echo", "hello"])}
    mock_session = AsyncMock()
    connect_cm = _make_async_cm_mock(yield_value=mock_session)
    mock_server = _make_mock_server("server1", connect_cm)

    with patch("frugalbot.mcp.mcp_servers.MCPServer", return_value=mock_server):
        await servers.connect_all(config)
        ctx = servers._contexts[0]

        # When
        await servers.disconnect_all()

        # Then
        assert ctx.task is not None
        assert ctx.task.done()


async def test_disconnect_all_clears_contexts() -> None:
    # Given
    servers = MCPServers()
    config = {"server1": MCPServerConfig(command=["echo", "hello"])}
    mock_session = AsyncMock()
    connect_cm = _make_async_cm_mock(yield_value=mock_session)
    mock_server = _make_mock_server("server1", connect_cm)

    with patch("frugalbot.mcp.mcp_servers.MCPServer", return_value=mock_server):
        await servers.connect_all(config)

        # When
        await servers.disconnect_all()

        # Then
        assert servers._contexts == []


async def test_disconnect_all_with_no_contexts_does_nothing() -> None:
    # Given
    servers = MCPServers()

    # When
    await servers.disconnect_all()

    # Then
    assert servers._contexts == []
