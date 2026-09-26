import os
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_mock import MockerFixture

from frugalbot.clients.base import LLMClient, LLMClientConfig, LLMClients, log_retry
from frugalbot.events import MessageEvent, MessageType


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure a clean state before and after every test."""
    LLMClients().unload()
    yield
    LLMClients().unload()


@pytest.fixture(autouse=True)
def copilot_runtime(mocker: MockerFixture):
    """Provide a resolvable pre-installed Copilot runtime so copilot clients can be constructed."""
    mocker.patch.dict(os.environ, {"COPILOT_CLI_PATH": sys.executable})


@pytest.fixture
def mock_bus():
    """Mock the event bus to verify event emissions."""
    with patch("frugalbot.clients.base.bus.emit_and_handle", new_callable=AsyncMock) as mocked:
        yield mocked


@pytest.fixture
def mock_loader():
    """Mock the dynamic module loader to avoid actual disk IO."""
    with patch("frugalbot.clients.base.load_dynamic_modules_with_config") as mocked:
        yield mocked


@pytest.fixture
def retry_state_with_error():
    """Creates a mock Tenacity RetryCallState with an exception."""
    expected_exc = None
    try:
        raise ValueError("Test Error")
    except ValueError as e:
        expected_exc = e
    state = MagicMock()
    state.outcome.exception.return_value = expected_exc
    state.next_action.sleep = 1.5
    state.attempt_number = 1
    return state


def test_llmclient_subclass_definition_registers_class():
    """Test that defining a subclass automatically registers it."""

    # Given: A new LLMClient subclass
    class MockClient(LLMClient):
        pass

    # When: The subclass is defined
    # Then: It should be present in the LLMClient registry
    assert MockClient in LLMClient._registry


def test_llmclient_name_with_config_returns_config_name():
    """Test that the name property returns the name from config."""
    # Given: An LLMClient instance with a config
    config = LLMClientConfig(name="test_client")
    client = LLMClient(config)

    # When: Accessing the name property
    # Then: The name should match the config name
    assert client.name == "test_client"


def test_llmclients_unload_clears_registry():
    """Test that unload_clients clears the class registry."""

    # Given: A registry with an entry
    class MockClient(LLMClient):
        pass

    assert MockClient in LLMClient._registry

    # When: unload_clients is called
    LLMClients().unload()

    # Then: The class registry should be empty
    assert len(LLMClient._registry) == 0


def test_llmclients_load_with_multiple_clients_sorts_by_config_order(mock_loader):
    """Test that LLMClients.load sorts the registry based on the config keys order."""

    # Given: Two registered clients in an LLMClients instance and a specific config order
    class BetaClient(LLMClient):
        pass

    class AlphaClient(LLMClient):
        pass

    clients = LLMClients()
    clients._register("beta", BetaClient(LLMClientConfig(name="beta")))
    clients._register("alpha", AlphaClient(LLMClientConfig(name="alpha")))

    config: dict[str, dict[str, Any]] = {
        "alpha": {"type": "alpha"},  # Alpha should come first
        "beta": {"type": "beta"},
    }

    # When: load is executed
    clients.load(config)

    # Then: get_all should return them in the order specified in the config keys
    result = clients.get_all()
    assert isinstance(result[0], AlphaClient)
    assert isinstance(result[1], BetaClient)


async def test_log_retry_with_error_emits_error_event(mock_bus, retry_state_with_error):
    """Test that log_retry emits a MessageEvent to the bus."""
    # Given: A retry state with an error (provided by fixture)

    # When: log_retry is called
    await log_retry(retry_state_with_error, include_traceback=False)

    # Then: bus.emit_and_handle should be called once
    mock_bus.assert_called_once()
    event = mock_bus.call_args[0][0]
    assert isinstance(event, MessageEvent)
    assert event.message_type == MessageType.ERROR


async def test_log_retry_with_traceback_disabled_excludes_traceback(mock_bus, retry_state_with_error):
    """Test the message content when traceback is disabled."""
    # Given: A retry state
    # When: log_retry is called without traceback
    await log_retry(retry_state_with_error, include_traceback=False)

    # Then: The event message should contain the error string but not a traceback
    message = mock_bus.call_args[0][0].message
    assert "Test Error" in message
    assert "Traceback" not in message
    assert "Attempt 1 failed" in message


async def test_log_retry_with_traceback_enabled_includes_traceback(mock_bus, retry_state_with_error):
    """Test the message content when traceback is enabled."""
    # Given: A retry state

    # When: log_retry is called with traceback
    await log_retry(retry_state_with_error, include_traceback=True)

    # Then: The event message should contain the traceback
    message = mock_bus.call_args[0][0].message
    assert "Traceback (most recent call last)" in message
    assert "ValueError: Test Error" in message


async def test_llmclient_close_default_is_noop() -> None:
    """Test that the default close() releases nothing and returns None."""
    # Given
    client = LLMClient(LLMClientConfig(name="test_client"))

    # When
    result = await client.close()

    # Then
    assert result is None


async def test_llmclients_aclose_awaits_close_on_each_client() -> None:
    """Test that aclose() closes every registered client."""
    # Given
    clients = LLMClients()
    first = MagicMock(spec=LLMClient)
    first.close = AsyncMock()
    second = MagicMock(spec=LLMClient)
    second.close = AsyncMock()
    clients._clients_registry = [first, second]

    # When
    await clients.aclose()

    # Then
    assert first.close.await_count == 1
    assert second.close.await_count == 1


async def test_llmclients_load_with_copilot_type_registers_copilot_client() -> None:
    """Test discovery of the copilot client by config type."""
    # Given
    clients = LLMClients()

    # When
    clients.load({"copilot_test": {"type": "copilot", "model": "gpt-5", "api_key_env_var": "COPILOT_GITHUB_TOKEN"}})

    # Then
    assert [type(client).__name__ for client in clients.get_all()] == ["CopilotClient"]


async def test_llmclients_load_with_copilot_and_manual_preserves_config_order() -> None:
    """Test that copilot coexists with other clients in config order."""
    # Given
    clients = LLMClients()

    # When
    clients.load({"first": {"type": "manual"}, "second": {"type": "copilot", "model": "gpt-5", "api_key_env_var": "TOKEN"}})

    # Then
    assert [type(client).__name__ for client in clients.get_all()] == ["ManualClient", "CopilotClient"]


async def test_llmclients_load_copilot_after_unload_does_not_duplicate() -> None:
    """Test that unloading then reloading copilot does not duplicate registrations."""
    # Given
    clients = LLMClients()
    config = {"copilot_test": {"type": "copilot", "model": "gpt-5", "api_key_env_var": "TOKEN"}}
    clients.load(config)
    clients.unload()

    # When
    clients.load(config)

    # Then
    assert len(clients.get_all()) == 1
