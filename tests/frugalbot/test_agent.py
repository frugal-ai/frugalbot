import datetime
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, PropertyMock

import pytest
from any_llm.types.completion import ChatCompletion, ChatCompletionMessage, ChatCompletionMessageFunctionToolCall, Choice, Function, Reasoning
from pyfakefs.fake_filesystem import FakeFilesystem
from pytest_mock import MockerFixture

from frugalbot.agent import _SESSION_FILE_NAME_DATETIME_FORMAT, _SESSIONS_BASE_PATH, Agent, _get_unique_conversation_file_path
from frugalbot.clients.base import LLMClient, LLMClients
from frugalbot.config import AgentConfig, GeneralConfig, PromptsConfig, ThinkingLevel
from frugalbot.events import BulkMessageEvent, MessageEvent, MessageType
from frugalbot.hooks.base import Hooks
from frugalbot.skills import Skill, Skills
from frugalbot.tools.base import Tools


@pytest.fixture
def mock_client() -> LLMClient:
    client = AsyncMock(spec=LLMClient)
    client.provider = "test_provider"
    client.model = "test_model"
    client.supports_thinking = True
    client.name = "test_client"
    client.base_url = "https://test.example.com"
    return client  # type: ignore[return-value]


@pytest.fixture
def mock_client2() -> LLMClient:
    client = AsyncMock(spec=LLMClient)
    client.provider = "test_provider2"
    client.model = "test_model2"
    client.supports_thinking = False
    client.name = "test_client2"
    client.base_url = "https://test2.example.com"
    return client  # type: ignore[return-value]


@pytest.fixture
def general_config() -> GeneralConfig:
    return GeneralConfig(
        agents=["agent"],
        tool_output_format="yaml",
        thinking_level="HIGH",
    )


@pytest.fixture
def agent_config() -> AgentConfig:
    return AgentConfig(
        clients=["test_client"],
        prompts=PromptsConfig(
            system_prompt="System: {{ tools }}",
            user_prompt="User: {{ user_message }}",
        ),
    )


@pytest.fixture
def mock_clients(mock_client: LLMClient) -> LLMClients:
    clients = LLMClients()
    clients._clients_registry = [mock_client]
    return clients


@pytest.fixture
def mock_tools() -> Tools:
    return Tools()


@pytest.fixture
def mock_hooks() -> Hooks:
    return Hooks()


@pytest.fixture
def mock_skills() -> Skills:
    return Skills([Skill(name="TestSkill", description="Test", location="test/SKILL.md", content="content")])


@pytest.fixture
def agent(
    mocker: MockerFixture,
    general_config: GeneralConfig,
    agent_config: AgentConfig,
    mock_clients: LLMClients,
    mock_tools: Tools,
    mock_hooks: Hooks,
    mock_skills: Skills,
) -> Agent:
    mocker.patch("frugalbot.agent.Agent._emit_status_update", new_callable=AsyncMock)
    return Agent("agent", general_config, agent_config, mock_clients, mock_tools, mock_hooks, mock_skills)


def test_agent_initialization_sets_initialized_to_false(
    general_config: GeneralConfig,
    agent_config: AgentConfig,
    mock_clients: LLMClients,
    mock_tools: Tools,
    mock_hooks: Hooks,
    mock_skills: Skills,
) -> None:
    # Given
    # (all fixtures provide the necessary setup)

    # When
    agent_instance = Agent("agent", general_config, agent_config, mock_clients, mock_tools, mock_hooks, mock_skills)

    # Then
    assert agent_instance._initialized is False


def test_agent_initialization_sets_client_index_to_zero(
    general_config: GeneralConfig,
    agent_config: AgentConfig,
    mock_clients: LLMClients,
    mock_tools: Tools,
    mock_hooks: Hooks,
    mock_skills: Skills,
) -> None:
    # Given
    # (all fixtures provide the necessary setup)

    # When
    agent_instance = Agent("agent", general_config, agent_config, mock_clients, mock_tools, mock_hooks, mock_skills)

    # Then
    assert agent_instance.client_index == 0


async def test_set_thinking_level_sets_thinking_level_on_all_clients_and_emits_status_update(
    mocker: MockerFixture,
    general_config: GeneralConfig,
    agent_config: AgentConfig,
    mock_tools: Tools,
    mock_hooks: Hooks,
    mock_skills: Skills,
    mock_client: LLMClient,
    mock_client2: LLMClient,
) -> None:
    # Given
    mock_emit = mocker.patch("frugalbot.agent.Agent._emit_status_update", new_callable=AsyncMock)
    mock_clients = [mock_client, mock_client2]
    thinking_level_mocks = [PropertyMock(return_value="HIGH") for c in mock_clients]
    for idx, c in enumerate(mock_clients):
        type(c).thinking_level = thinking_level_mocks[idx]
    clients = LLMClients()
    clients._clients_registry = mock_clients
    agent_instance = Agent("agent", general_config, agent_config, clients, mock_tools, mock_hooks, mock_skills)
    new_thinking_level: ThinkingLevel = "MEDIUM"

    # When
    await agent_instance.set_thinking_level(new_thinking_level, emit_status_update=True)

    # Then
    (thinking_level_mock.assert_called_with(new_thinking_level) for thinking_level_mock in thinking_level_mocks)
    mock_emit.assert_called_once()


async def test_next_client_with_multiple_clients_advances_index(
    mocker: MockerFixture,
    mock_client: LLMClient,
    mock_client2: LLMClient,
    general_config: GeneralConfig,
    mock_tools: Tools,
    mock_hooks: Hooks,
    mock_skills: Skills,
) -> None:
    # Given
    mocker.patch("frugalbot.agent.Agent._emit_status_update", new_callable=AsyncMock)
    clients = LLMClients()
    clients._clients_registry = [mock_client, mock_client2]
    agent_cfg = AgentConfig(clients=["test_client", "test_client2"])
    agent_instance = Agent("agent", general_config, agent_cfg, clients, mock_tools, mock_hooks, mock_skills)
    agent_instance.client_index = 0

    # When
    await agent_instance.next_client()

    # Then
    assert agent_instance.client_index == 1


async def test_next_client_at_last_client_wraps_to_first(
    mocker: MockerFixture,
    mock_client: LLMClient,
    mock_client2: LLMClient,
    general_config: GeneralConfig,
    mock_tools: Tools,
    mock_hooks: Hooks,
    mock_skills: Skills,
) -> None:
    # Given
    mocker.patch("frugalbot.agent.Agent._emit_status_update", new_callable=AsyncMock)
    clients = LLMClients()
    clients._clients_registry = [mock_client, mock_client2]
    agent_cfg = AgentConfig(clients=["test_client", "test_client2"])
    agent_instance = Agent("agent", general_config, agent_cfg, clients, mock_tools, mock_hooks, mock_skills)
    agent_instance.client_index = 1

    # When
    await agent_instance.next_client()

    # Then
    assert agent_instance.client_index == 0


async def test_new_conversation_creates_file_path_and_appends_system_message(mocker: MockerFixture, agent: Agent) -> None:
    # Given
    mocker.patch("frugalbot.agent.render_system_prompt", new_callable=AsyncMock, return_value="System ready")
    mocker.patch("frugalbot.agent.bus.emit_and_handle", new_callable=AsyncMock)

    # When
    await agent.new_conversation()

    # Then
    assert agent.conversation.messages[0] == {"role": "system", "content": "System ready"}


async def test_new_conversation_sets_initialized_to_true(mocker: MockerFixture, agent: Agent) -> None:
    # Given
    mocker.patch("frugalbot.agent.render_system_prompt", new_callable=AsyncMock, return_value="System ready")
    mocker.patch("frugalbot.agent.bus.emit_and_handle", new_callable=AsyncMock)

    # When
    await agent.new_conversation()

    # Then
    assert agent._initialized is True


async def test_load_conversation_from_file_with_valid_messages_emits_bulk_event(mocker: MockerFixture, agent: Agent) -> None:
    # Given
    file_path = Path("session.json")
    mock_emit = mocker.patch("frugalbot.agent.bus.emit_and_handle", new_callable=AsyncMock)

    async def mock_load(path: Path) -> None:
        agent.conversation._messages = [
            {"role": "system", "content": "You are an agent"},
            {"role": "user", "content": "User context"},
            (
                "provider",
                ChatCompletion(
                    id="id",
                    created=0,
                    model="model",
                    object="chat.completion",
                    choices=[
                        Choice(
                            index=0,
                            finish_reason="stop",
                            message=ChatCompletionMessage(
                                role="assistant",
                                reasoning=Reasoning(content="Reasoning content"),
                                content="Content",
                                tool_calls=[ChatCompletionMessageFunctionToolCall(id="id", type="function", function=Function(name="tool name", arguments='{"path":"/hello"}'))],
                            ),
                        )
                    ],
                ),
            ),
            {"role": "tool", "name": "tool name", "content": '{"result":"tool result"}'},
        ]

    mocker.patch("frugalbot.conversation.Conversation.load_from_file", side_effect=mock_load)

    # When
    await agent.load_conversation_from_file(file_path)

    # Then
    mock_emit.assert_called()
    bulk_msg_event: BulkMessageEvent = mock_emit.call_args.args[0]
    assert len(bulk_msg_event.messages) == 6
    assert "agent" in bulk_msg_event.messages[0].message
    assert bulk_msg_event.messages[0].message_type == MessageType.SYSTEM
    assert "User" in bulk_msg_event.messages[1].message
    assert bulk_msg_event.messages[1].message_type == MessageType.USER
    assert "Reasoning" in bulk_msg_event.messages[2].message
    assert bulk_msg_event.messages[2].message_type == MessageType.THINKING
    assert "Content" in bulk_msg_event.messages[3].message
    assert bulk_msg_event.messages[3].message_type == MessageType.ASSISTANT
    assert "tool_name" in bulk_msg_event.messages[4].message
    assert bulk_msg_event.messages[4].message_type == MessageType.TOOL_CALL
    assert "result:" in bulk_msg_event.messages[5].message
    assert bulk_msg_event.messages[5].message_type == MessageType.TOOL_OUTPUT


async def test_run_with_uninitialized_agent_calls_new_conversation(mocker: MockerFixture, agent: Agent, mock_client: LLMClient) -> None:
    # Given
    mocker.patch("frugalbot.agent.render_user_prompt", new_callable=AsyncMock, return_value="Rendered prompt")
    mocker.patch("frugalbot.agent.bus.emit_and_handle", new_callable=AsyncMock)
    mock_new_conv = mocker.patch.object(agent, "new_conversation", new_callable=AsyncMock)

    assistant_msg = ChatCompletionMessage(role="assistant", content="Done", tool_calls=None)
    completion = ChatCompletion(id="1", choices=[Choice(index=0, message=assistant_msg, finish_reason="stop")], model="model", created=123, object="chat.completion")
    cast(AsyncMock, mock_client).call.return_value = completion

    agent._initialized = False

    # When
    await agent.run("task")

    # Then
    mock_new_conv.assert_called_once()


async def test_run_with_valid_completion_appends_assistant_message(mocker: MockerFixture, agent: Agent, mock_client: LLMClient) -> None:
    # Given
    agent._initialized = True
    mocker.patch("frugalbot.agent.render_user_prompt", new_callable=AsyncMock, return_value="Hello")
    mocker.patch("frugalbot.agent.bus.emit_and_handle", new_callable=AsyncMock)

    assistant_msg = ChatCompletionMessage(role="assistant", content="Hi there", tool_calls=None)
    completion = ChatCompletion(id="1", choices=[Choice(index=0, message=assistant_msg, finish_reason="stop")], model="model", created=123, object="chat.completion")
    cast(AsyncMock, mock_client).call.return_value = completion

    # When
    await agent.run("Hello")

    # Then
    assert agent.conversation.latest_assistant_message().content == "Hi there"


async def test_run_with_empty_choices_emits_error_event(mocker: MockerFixture, agent: Agent, mock_client: LLMClient) -> None:
    # Given
    agent._initialized = True
    mocker.patch("frugalbot.agent.render_user_prompt", new_callable=AsyncMock, return_value="Hello")
    mock_emit = mocker.patch("frugalbot.agent.bus.emit_and_handle", new_callable=AsyncMock)

    empty_completion = ChatCompletion(id="1", choices=[], model="model", created=123, object="chat.completion")
    valid_msg = ChatCompletionMessage(role="assistant", content="Done")
    valid_completion = ChatCompletion(id="2", choices=[Choice(index=0, message=valid_msg, finish_reason="stop")], model="model", created=123, object="chat.completion")
    cast(AsyncMock, mock_client).call.side_effect = [empty_completion, valid_completion]

    # When
    with pytest.raises(RuntimeError):
        await agent.run("Hello")

    # Then
    mock_emit.assert_any_call(MessageEvent("LLM returned an empty completion.choices. Aborting run to prevent infinite loop.", MessageType.ERROR))


async def test_run_with_runtime_error_serializes_conversation(
    mocker: MockerFixture,
    general_config: GeneralConfig,
    agent_config: AgentConfig,
    mock_clients: LLMClients,
    mock_tools: Tools,
    mock_hooks: Hooks,
    mock_skills: Skills,
    mock_client: LLMClient,
) -> None:
    # Given
    mocker.patch("frugalbot.agent.Agent._emit_status_update", new_callable=AsyncMock)
    session_file = Path("session.json")
    agent_instance = Agent("agent", general_config, agent_config, mock_clients, mock_tools, mock_hooks, mock_skills)
    agent_instance._initialized = True
    agent_instance.conversation_file_path = session_file

    mocker.patch("frugalbot.agent.render_user_prompt", new_callable=AsyncMock, return_value="Rendered prompt")
    mocker.patch("frugalbot.agent.bus.emit_and_handle", new_callable=AsyncMock)

    cast(AsyncMock, mock_client).call.side_effect = RuntimeError
    mock_serialize = mocker.patch("frugalbot.conversation.Conversation.serialize_to_file", new_callable=AsyncMock)

    # When
    with pytest.raises(RuntimeError):
        await agent_instance.run("task")

    # Then
    mock_serialize.assert_called_once_with(session_file)


def test_get_unique_conversation_file_path_when_file_exists_appends_unique_suffix(mocker: MockerFixture, fs: FakeFilesystem) -> None:
    # given
    dt = datetime.datetime(2026, 5, 14)
    fs.create_dir(_SESSIONS_BASE_PATH)
    formatted_datetime = dt.strftime(_SESSION_FILE_NAME_DATETIME_FORMAT)
    fs.create_file(_SESSIONS_BASE_PATH / f"{formatted_datetime}.json")
    mocker.patch("frugalbot.agent.datetime").now.return_value = dt

    # when
    convo_file_path = _get_unique_conversation_file_path()

    # then
    assert convo_file_path == _SESSIONS_BASE_PATH / f"{formatted_datetime}-2.json"


def test_agent_init_with_empty_clients_raises(
    general_config: GeneralConfig,
    agent_config: AgentConfig,
    mock_clients: LLMClients,
    mock_tools: Tools,
    mock_hooks: Hooks,
    mock_skills: Skills,
) -> None:
    mock_clients._clients_registry = []
    with pytest.raises(ValueError):
        Agent("agent", general_config, agent_config, mock_clients, mock_tools, mock_hooks, mock_skills)


async def test_agent_next_client_with_empty_clients_raises(
    general_config: GeneralConfig,
    agent_config: AgentConfig,
    mock_clients: LLMClients,
    mock_tools: Tools,
    mock_hooks: Hooks,
    mock_skills: Skills,
) -> None:
    # given
    agent = Agent("agent", general_config, agent_config, mock_clients, mock_tools, mock_hooks, mock_skills)
    agent.clients.clear()

    # when / then
    with pytest.raises(ValueError):
        await agent.next_client()


async def test_agent_load_conversation_from_file_when_load_from_file_raises_emits_error_and_creates_new_convo(mocker: MockerFixture, agent: Agent) -> None:
    # given
    mock_new_conv = mocker.patch.object(agent, "new_conversation")
    mock_emit = mocker.patch("frugalbot.agent.bus.emit_and_handle")

    # when
    await agent.load_conversation_from_file(Path("does/not/exit/ever/never.json"))

    # then
    mock_new_conv.assert_called_once()
    mock_emit.assert_called_once()
    assert mock_emit.call_args and mock_emit.call_args.args
    assert "error" in mock_emit.call_args.args[0].message.lower()


@pytest.mark.parametrize(("provider", "models_dev_patched_method"), [("openrouter", "get_provider_by_url"), ("other", "get_provider_by_url"), ("other", "get_model")])
async def test_emit_status_update_with_openrouter_provider_when_openrouter_client_raises_handles_gracefully(
    provider: str,
    models_dev_patched_method: str,
    mocker: MockerFixture,
    general_config: GeneralConfig,
    agent_config: AgentConfig,
    mock_clients: LLMClients,
    mock_tools: Tools,
    mock_hooks: Hooks,
    mock_skills: Skills,
) -> None:
    # given
    agent = Agent("agent", general_config, agent_config, mock_clients, mock_tools, mock_hooks, mock_skills)
    mocker.patch.object(agent.openrouter_client, "get_model", side_effect=ValueError())
    mocker.patch.object(agent.models_dev_client, models_dev_patched_method, side_effect=ValueError())
    mock_emit = mocker.patch("frugalbot.agent.bus.emit_and_handle")
    agent.client.provider = provider

    # when
    await agent._emit_status_update()

    # then
    mock_emit.assert_called_once()
