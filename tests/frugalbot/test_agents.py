from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_mock import MockerFixture

from frugalbot.agent import Agent
from frugalbot.agents import Agents, _create_agents
from frugalbot.clients.base import LLMClient, LLMClients
from frugalbot.config import AgentConfig, Config, GeneralConfig
from frugalbot.hooks.base import Hooks
from frugalbot.skills import Skill, Skills
from frugalbot.tools.base import Tools

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_llm_client() -> LLMClient:
    client = MagicMock(spec=LLMClient)
    client.provider = "test_provider"
    client.model = "test_model"
    client.name = "test_client"
    return client


@pytest.fixture
def general_config() -> GeneralConfig:
    return GeneralConfig(
        agents=["coder"],
        tool_output_format="yaml",
        thinking_level="HIGH",
    )


@pytest.fixture
def mock_clients(mock_llm_client: LLMClient) -> LLMClients:
    clients = LLMClients()
    clients._clients_registry = [mock_llm_client]
    return clients


@pytest.fixture
def mock_skills() -> Skills:
    return Skills([Skill(name="test-skill", description="Test skill", location="test/SKILL.md", content="content")])


@pytest.fixture
def single_agent_config(general_config: GeneralConfig) -> Config:
    return Config(
        general=general_config,
        clients={"test_client": {"type": "test"}},
        agents={"coder": AgentConfig(clients=["test_client"], tools={}, hooks={})},
    )


@pytest.fixture
def multi_agent_config() -> Config:
    return Config(
        general=GeneralConfig(agents=["coder", "reviewer"], tool_output_format="yaml"),
        clients={"test_client": {"type": "test"}},
        agents={
            "coder": AgentConfig(clients=["test_client"], tools={}, hooks={}),
            "reviewer": AgentConfig(clients=["test_client"], tools={}, hooks={}),
        },
    )


VALID_CONFIG_TOML = """\
[general]
agents = ["coder"]
tool_output_format = "yaml"

[clients.test_client]
type = "manual"

[prompts]
system_prompt = "You are a test assistant."
user_prompt = "{{user_message}}"
"""


MULTI_AGENT_CONFIG_TOML = """\
[general]
agents = ["coder", "reviewer"]
tool_output_format = "yaml"

[clients.test_client]
type = "manual"

[prompts]
system_prompt = "You are a test assistant."
user_prompt = "{{user_message}}"
"""


# =============================================================================
# _create_agents() Tests
# =============================================================================


async def test_create_agents_with_single_agent_returns_dict_with_one_entry(single_agent_config: Config, mock_clients: LLMClients, mock_skills: Skills, mocker: MockerFixture) -> None:
    # Given
    mocker.patch.object(Tools, "load")
    mocker.patch.object(Hooks, "load")

    # When
    agents = await _create_agents(single_agent_config, mock_clients, mock_skills, None)

    # Then
    assert "coder" in agents


async def test_create_agents_with_single_agent_returns_agent_instance(single_agent_config: Config, mock_clients: LLMClients, mock_skills: Skills, mocker: MockerFixture) -> None:
    # Given
    mocker.patch.object(Tools, "load")
    mocker.patch.object(Hooks, "load")

    # When
    agents = await _create_agents(single_agent_config, mock_clients, mock_skills, None)

    # Then
    assert isinstance(agents["coder"], Agent)


async def test_create_agents_with_empty_agents_config_returns_empty_dict(general_config: GeneralConfig, mock_clients: LLMClients, mock_skills: Skills) -> None:
    # Given
    config = Config(
        general=general_config,
        clients={"test_client": {"type": "test"}},
        agents={},
    )

    # When
    agents = await _create_agents(config, mock_clients, mock_skills, None)

    # Then
    assert agents == {}


async def test_create_agents_with_multiple_agents_returns_all_agents(multi_agent_config: Config, mock_clients: LLMClients, mock_skills: Skills, mocker: MockerFixture) -> None:
    # Given
    mocker.patch.object(Tools, "load")
    mocker.patch.object(Hooks, "load")

    # When
    agents = await _create_agents(multi_agent_config, mock_clients, mock_skills, None)

    # Then
    assert "coder" in agents
    assert "reviewer" in agents
    assert len(agents) == 2


async def test_create_agents_with_different_skills_returns_agents_with_configured_skills(multi_agent_config: Config, mock_clients: LLMClients, mocker: MockerFixture) -> None:
    # Given
    mocker.patch.object(Tools, "load")
    mocker.patch.object(Hooks, "load")
    skills = Skills([
        Skill(name="test-skill", description="Test skill", location="test/SKILL.md", content="content"),
        Skill(name="test-skill2", description="Test skill2", location="test2/SKILL.md", content="content"),
    ])
    multi_agent_config.agents["searcher"] = AgentConfig(clients=["test_client"], tools={}, hooks={}, skills=["test-skill2"])
    multi_agent_config.agents["assistant"] = AgentConfig(clients=["test_client"], tools={}, hooks={}, skills=["unknown-skill"])
    multi_agent_config.agents["coder"].skills = []

    def skill_names(agent: Agent) -> list[str]:
        return sorted(s.name for s in agent.skills.skills)

    # When
    agents = await _create_agents(multi_agent_config, mock_clients, skills, None)

    # Then
    assert skill_names(agents["coder"]) == []
    assert skill_names(agents["reviewer"]) == sorted(["test-skill", "test-skill2"])
    assert skill_names(agents["searcher"]) == ["test-skill2"]
    assert skill_names(agents["assistant"]) == []


async def test_create_agents_with_tools_config_loads_tools(single_agent_config: Config, mock_clients: LLMClients, mock_skills: Skills, mocker: MockerFixture) -> None:
    # Given
    mocker.patch.object(Hooks, "load")
    mock_tools_load = mocker.patch.object(Tools, "load")
    single_agent_config.agents["coder"].tools = {"bash": {"enabled": True}}

    # When
    await _create_agents(single_agent_config, mock_clients, mock_skills, None)

    # Then
    mock_tools_load.assert_called_once_with({"bash": {"enabled": True}})


async def test_create_agents_with_hooks_config_loads_hooks(single_agent_config: Config, mock_clients: LLMClients, mock_skills: Skills, mocker: MockerFixture) -> None:
    # Given
    mocker.patch.object(Tools, "load")
    mock_hooks_load = mocker.patch.object(Hooks, "load")
    single_agent_config.agents["coder"].hooks = {"autoapproval": {"enabled": True}}

    # When
    await _create_agents(single_agent_config, mock_clients, mock_skills, None)

    # Then
    mock_hooks_load.assert_called_once_with({"autoapproval": {"enabled": True}})


async def test_create_agents_with_multiple_agents_loads_tools_for_each(multi_agent_config: Config, mock_clients: LLMClients, mock_skills: Skills, mocker: MockerFixture) -> None:
    # Given
    mocker.patch.object(Hooks, "load")
    mock_tools_load = mocker.patch.object(Tools, "load")
    multi_agent_config.agents["coder"].tools = {"bash": {"enabled": True}}
    multi_agent_config.agents["reviewer"].tools = {"edit": {"enabled": True}}

    # When
    await _create_agents(multi_agent_config, mock_clients, mock_skills, None)

    # Then
    assert mock_tools_load.call_count == 2
    mock_tools_load.assert_any_call({"bash": {"enabled": True}})
    mock_tools_load.assert_any_call({"edit": {"enabled": True}})


async def test_create_agents_creates_new_tools_and_hooks_per_agent(multi_agent_config: Config, mock_clients: LLMClients, mock_skills: Skills, mocker: MockerFixture) -> None:
    # Given
    tools_instances: list[Tools] = []
    hooks_instances: list[Hooks] = []

    original_tools_init = Tools.__init__
    original_hooks_init = Hooks.__init__

    def tracking_tools_init(self: Tools) -> None:
        original_tools_init(self)
        tools_instances.append(self)

    def tracking_hooks_init(self: Hooks) -> None:
        original_hooks_init(self)
        hooks_instances.append(self)

    mocker.patch.object(Tools, "__init__", tracking_tools_init)
    mocker.patch.object(Hooks, "__init__", tracking_hooks_init)
    mocker.patch.object(Tools, "load")
    mocker.patch.object(Hooks, "load")

    # When
    await _create_agents(multi_agent_config, mock_clients, mock_skills, None)

    # Then
    assert len(tools_instances) == 2
    assert len(hooks_instances) == 2
    assert tools_instances[0] is not tools_instances[1]
    assert hooks_instances[0] is not hooks_instances[1]


async def test_create_agents_agent_receives_correct_name(single_agent_config: Config, mock_clients: LLMClients, mock_skills: Skills, mocker: MockerFixture) -> None:
    # Given
    mocker.patch.object(Tools, "load")
    mocker.patch.object(Hooks, "load")

    # When
    agents = await _create_agents(single_agent_config, mock_clients, mock_skills, None)

    # Then
    assert agents["coder"].name == "coder"


# =============================================================================
# Agents.load() Tests
# =============================================================================


async def test_agents_load_with_valid_config_returns_agents_dict(fs, mocker: MockerFixture) -> None:
    # Given
    config_file = Path("/home/user/.frugalbot/config.toml")
    fs.create_file(config_file, contents=VALID_CONFIG_TOML)
    mocker.patch("frugalbot.agents.load_dotenv")
    mock_clients_obj = mocker.patch("frugalbot.agents.LLMClients")
    mock_client_instance = MagicMock(spec=LLMClient)
    mock_client_instance.name = "test_client"
    mock_clients_obj.return_value.get_all.return_value = [mock_client_instance]
    mocker.patch("frugalbot.agents.discover_skills", return_value=Skills([]))
    mocker.patch("frugalbot.agents._init_mcp", new_callable=AsyncMock, return_value=(MagicMock(), None))
    mocker.patch("frugalbot.agents._create_agents", new_callable=AsyncMock, return_value={"coder": MagicMock(spec=Agent)})

    # When
    agents = Agents()
    await agents.load(config_file_path=config_file)

    # Then
    assert isinstance(agents.agents, dict)


async def test_agents_load_with_valid_config_contains_coder_agent(fs, mocker: MockerFixture) -> None:
    # Given
    config_file = Path("/home/user/.frugalbot/config.toml")
    fs.create_file(config_file, contents=VALID_CONFIG_TOML)
    mocker.patch("frugalbot.agents.load_dotenv")
    mock_clients_obj = mocker.patch("frugalbot.agents.LLMClients")
    mock_client_instance = MagicMock(spec=LLMClient)
    mock_client_instance.name = "test_client"
    mock_clients_obj.return_value.get_all.return_value = [mock_client_instance]
    mocker.patch("frugalbot.agents.discover_skills", return_value=Skills([]))
    mocker.patch("frugalbot.agents._init_mcp", new_callable=AsyncMock, return_value=(MagicMock(), None))
    expected_agents: dict[str, MagicMock] = {"coder": MagicMock(spec=Agent)}
    mocker.patch("frugalbot.agents._create_agents", new_callable=AsyncMock, return_value=expected_agents)

    # When
    agents = Agents()
    await agents.load(config_file_path=config_file)

    # Then
    assert "coder" in agents.agents


async def test_agents_load_with_valid_config_returns_agent_instance(fs, mocker: MockerFixture) -> None:
    # Given
    config_file = Path("/home/user/.frugalbot/config.toml")
    fs.create_file(config_file, contents=VALID_CONFIG_TOML)
    mocker.patch("frugalbot.agents.load_dotenv")
    mock_clients_obj = mocker.patch("frugalbot.agents.LLMClients")
    mock_client_instance = MagicMock(spec=LLMClient)
    mock_client_instance.name = "test_client"
    mock_clients_obj.return_value.get_all.return_value = [mock_client_instance]
    mocker.patch("frugalbot.agents.discover_skills", return_value=Skills([]))
    mocker.patch("frugalbot.agents._init_mcp", new_callable=AsyncMock, return_value=(MagicMock(), None))
    mock_agent = MagicMock(spec=Agent)
    mocker.patch("frugalbot.agents._create_agents", new_callable=AsyncMock, return_value={"coder": mock_agent})

    # When
    agents = Agents()
    await agents.load(config_file_path=config_file)

    # Then
    assert isinstance(agents.agents["coder"], Agent)


async def test_agents_load_calls_load_dotenv_with_default_env_path(fs, mocker: MockerFixture) -> None:
    # Given
    config_file = Path("/home/user/.frugalbot/config.toml")
    env_file = Path("/home/user/.frugalbot/.env")
    fs.create_file(config_file, contents=VALID_CONFIG_TOML)
    mock_load_dotenv = mocker.patch("frugalbot.agents.load_dotenv")
    mock_clients_obj = mocker.patch("frugalbot.agents.LLMClients")
    mock_client_instance = MagicMock(spec=LLMClient)
    mock_client_instance.name = "test_client"
    mock_clients_obj.return_value.get_all.return_value = [mock_client_instance]
    mocker.patch("frugalbot.agents.discover_skills", return_value=Skills([]))
    mocker.patch("frugalbot.agents._init_mcp", new_callable=AsyncMock, return_value=(MagicMock(), None))
    mocker.patch("frugalbot.agents._create_agents", new_callable=AsyncMock, return_value={})

    # When
    agents = Agents()
    await agents.load(config_file_path=config_file, env_file_path=env_file)

    # Then
    mock_load_dotenv.assert_called_once_with(env_file)


async def test_agents_load_calls_load_dotenv_with_custom_env_path(fs, mocker: MockerFixture) -> None:
    # Given
    config_file = Path("/home/user/.frugalbot/config.toml")
    custom_env_file = Path("/custom/.env")
    fs.create_file(config_file, contents=VALID_CONFIG_TOML)
    mock_load_dotenv = mocker.patch("frugalbot.agents.load_dotenv")
    mock_clients_obj = mocker.patch("frugalbot.agents.LLMClients")
    mock_client_instance = MagicMock(spec=LLMClient)
    mock_client_instance.name = "test_client"
    mock_clients_obj.return_value.get_all.return_value = [mock_client_instance]
    mocker.patch("frugalbot.agents.discover_skills", return_value=Skills([]))
    mocker.patch("frugalbot.agents._init_mcp", new_callable=AsyncMock, return_value=(MagicMock(), None))
    mocker.patch("frugalbot.agents._create_agents", new_callable=AsyncMock, return_value={})

    # When
    agents = Agents()
    await agents.load(config_file_path=config_file, env_file_path=custom_env_file)

    # Then
    mock_load_dotenv.assert_called_once_with(custom_env_file)


async def test_agents_load_loads_config_from_provided_path(fs, mocker: MockerFixture) -> None:
    # Given
    config_file = Path("/home/user/.frugalbot/config.toml")
    fs.create_file(config_file, contents=VALID_CONFIG_TOML)
    mocker.patch("frugalbot.agents.load_dotenv")
    mock_config_load = mocker.patch("frugalbot.agents.frugalbot.config.load")
    mock_clients_obj = mocker.patch("frugalbot.agents.LLMClients")
    mock_client_instance = MagicMock(spec=LLMClient)
    mock_client_instance.name = "test_client"
    mock_clients_obj.return_value.get_all.return_value = [mock_client_instance]
    mocker.patch("frugalbot.agents.discover_skills", return_value=Skills([]))
    mocker.patch("frugalbot.agents._init_mcp", new_callable=AsyncMock, return_value=(MagicMock(), None))
    mocker.patch("frugalbot.agents._create_agents", new_callable=AsyncMock, return_value={})

    # When
    agents = Agents()
    await agents.load(config_file_path=config_file)

    # Then
    mock_config_load.assert_called_once_with(config_file)


async def test_agents_load_calls_clients_load(fs, mocker: MockerFixture) -> None:
    # Given
    config_file = Path("/home/user/.frugalbot/config.toml")
    fs.create_file(config_file, contents=VALID_CONFIG_TOML)
    mocker.patch("frugalbot.agents.load_dotenv")
    mock_clients_obj = mocker.patch("frugalbot.agents.LLMClients")
    mock_client_instance = MagicMock(spec=LLMClient)
    mock_client_instance.name = "test_client"
    mock_clients_obj.return_value.get_all.return_value = [mock_client_instance]
    mocker.patch("frugalbot.agents.discover_skills", return_value=Skills([]))
    mocker.patch("frugalbot.agents._init_mcp", new_callable=AsyncMock, return_value=(MagicMock(), None))
    mocker.patch("frugalbot.agents._create_agents", new_callable=AsyncMock, return_value={})

    # When
    agents = Agents()
    await agents.load(config_file_path=config_file)

    # Then
    mock_clients_obj.return_value.load.assert_called_once_with({"test_client": {"type": "manual", "name": "test_client"}})


async def test_agents_load_with_no_clients_raises_value_error(fs, mocker: MockerFixture) -> None:
    # Given
    config_file = Path("/home/user/.frugalbot/config.toml")
    fs.create_file(config_file, contents=VALID_CONFIG_TOML)
    mocker.patch("frugalbot.agents.load_dotenv")
    mock_clients_obj = mocker.patch("frugalbot.agents.LLMClients")
    mock_clients_obj.return_value.get_all.return_value = []

    # When / Then
    agents = Agents()
    with pytest.raises(ValueError, match="Must configure at least one client"):
        await agents.load(config_file_path=config_file)


async def test_agents_load_calls_discover_skills(fs, mocker: MockerFixture) -> None:
    # Given
    config_file = Path("/home/user/.frugalbot/config.toml")
    fs.create_file(config_file, contents=VALID_CONFIG_TOML)
    mocker.patch("frugalbot.agents.load_dotenv")
    mock_clients_obj = mocker.patch("frugalbot.agents.LLMClients")
    mock_client_instance = MagicMock(spec=LLMClient)
    mock_client_instance.name = "test_client"
    mock_clients_obj.return_value.get_all.return_value = [mock_client_instance]
    mock_discover_skills = mocker.patch("frugalbot.agents.discover_skills", return_value=Skills([]))
    mocker.patch("frugalbot.agents._init_mcp", new_callable=AsyncMock, return_value=(MagicMock(), None))
    mocker.patch("frugalbot.agents._create_agents", new_callable=AsyncMock, return_value={})

    # When
    agents = Agents()
    await agents.load(config_file_path=config_file)

    # Then
    mock_discover_skills.assert_called_once()


async def test_agents_load_passes_skills_to_create_agents(fs, mocker: MockerFixture) -> None:
    # Given
    config_file = Path("/home/user/.frugalbot/config.toml")
    fs.create_file(config_file, contents=VALID_CONFIG_TOML)
    mocker.patch("frugalbot.agents.load_dotenv")
    mock_clients_obj = mocker.patch("frugalbot.agents.LLMClients")
    mock_client_instance = MagicMock(spec=LLMClient)
    mock_client_instance.name = "test_client"
    mock_clients_obj.return_value.get_all.return_value = [mock_client_instance]
    expected_skills = Skills([Skill(name="s1", description="d1", location="l1", content="c1")])
    mocker.patch("frugalbot.agents.discover_skills", return_value=expected_skills)
    mock_create_agents = mocker.patch("frugalbot.agents._create_agents", new_callable=AsyncMock, return_value={})
    mocker.patch("frugalbot.agents._init_mcp", new_callable=AsyncMock, return_value=(MagicMock(), None))

    # When
    agents = Agents()
    await agents.load(config_file_path=config_file)

    # Then
    call_args = mock_create_agents.call_args
    assert call_args[0][2] is expected_skills


async def test_agents_load_passes_clients_to_create_agents(fs, mocker: MockerFixture) -> None:
    # Given
    config_file = Path("/home/user/.frugalbot/config.toml")
    fs.create_file(config_file, contents=VALID_CONFIG_TOML)
    mocker.patch("frugalbot.agents.load_dotenv")
    mock_clients_obj = mocker.patch("frugalbot.agents.LLMClients")
    mock_client_instance = MagicMock(spec=LLMClient)
    mock_client_instance.name = "test_client"
    mock_clients_obj.return_value.get_all.return_value = [mock_client_instance]
    mocker.patch("frugalbot.agents.discover_skills", return_value=Skills([]))
    mock_create_agents = mocker.patch("frugalbot.agents._create_agents", new_callable=AsyncMock, return_value={})
    mocker.patch("frugalbot.agents._init_mcp", new_callable=AsyncMock, return_value=(MagicMock(), None))

    # When
    agents = Agents()
    await agents.load(config_file_path=config_file)

    # Then
    call_args = mock_create_agents.call_args
    assert call_args[0][1] is mock_clients_obj.return_value


async def test_agents_load_passes_config_to_create_agents(fs, mocker: MockerFixture) -> None:
    # Given
    config_file = Path("/home/user/.frugalbot/config.toml")
    fs.create_file(config_file, contents=VALID_CONFIG_TOML)
    mocker.patch("frugalbot.agents.load_dotenv")
    mock_clients_obj = mocker.patch("frugalbot.agents.LLMClients")
    mock_client_instance = MagicMock(spec=LLMClient)
    mock_client_instance.name = "test_client"
    mock_clients_obj.return_value.get_all.return_value = [mock_client_instance]
    mocker.patch("frugalbot.agents.discover_skills", return_value=Skills([]))
    mock_create_agents = mocker.patch("frugalbot.agents._create_agents", new_callable=AsyncMock, return_value={})
    mocker.patch("frugalbot.agents._init_mcp", new_callable=AsyncMock, return_value=(MagicMock(), None))

    # When
    agents = Agents()
    await agents.load(config_file_path=config_file)

    # Then
    call_args = mock_create_agents.call_args
    loaded_config = call_args[0][0]
    assert loaded_config.general.agents == ["coder"]


async def test_agents_load_with_nonexistent_config_file_raises_file_not_found_error(
    mocker: MockerFixture,
) -> None:
    # Given
    nonexistent_path = Path("/nonexistent/config.toml")
    mocker.patch("frugalbot.agents.load_dotenv")

    # When / Then
    agents = Agents()
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        await agents.load(config_file_path=nonexistent_path)
