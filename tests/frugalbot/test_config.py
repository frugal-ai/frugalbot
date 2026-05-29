from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from frugalbot.config import AgentConfig, Config, GeneralConfig, PromptsConfig, _merge_global_with_agent_specific_section, load, write_default

# =============================================================================
# PromptsConfig Tests
# =============================================================================


def test_prompts_config_with_default_values_sets_empty_system_prompt() -> None:
    # Given / When
    config = PromptsConfig()

    # Then
    assert config.system_prompt == ""


def test_prompts_config_with_default_values_sets_default_user_prompt() -> None:
    # Given / When
    config = PromptsConfig()

    # Then
    assert config.user_prompt == "{{user_message}}"


def test_prompts_config_with_custom_system_prompt_stores_string() -> None:
    # Given
    data: dict[str, Any] = {"system_prompt": "System: {{ name }}"}

    # When
    config = PromptsConfig.model_validate(data)

    # Then
    assert config.system_prompt == "System: {{ name }}"


def test_prompts_config_with_custom_user_prompt_stores_string() -> None:
    # Given
    data: dict[str, Any] = {"user_prompt": "Query: {{ query }}"}

    # When
    config = PromptsConfig.model_validate(data)

    # Then
    assert config.user_prompt == "Query: {{ query }}"


@pytest.mark.parametrize("invalid_value", [123, None, ["not", "a", "string"], {"key": "value"}])
def test_prompts_config_with_invalid_system_prompt_type_raises_validation_error(invalid_value: object) -> None:
    # Given
    invalid_data: dict[str, Any] = {"system_prompt": invalid_value}

    # When / Then
    with pytest.raises(ValidationError):
        PromptsConfig.model_validate(invalid_data)


# =============================================================================
# GeneralConfig Tests
# =============================================================================


def test_general_config_with_default_agents_sets_coder() -> None:
    # Given / When
    config = GeneralConfig(tool_output_format="yaml")

    # Then
    assert config.agents == ["coder"]


def test_general_config_with_custom_agents_stores_agents() -> None:
    # Given / When
    config = GeneralConfig(agents=["coder", "reviewer"], tool_output_format="json")

    # Then
    assert config.agents == ["coder", "reviewer"]


def test_general_config_with_valid_tool_output_format_stores_format() -> None:
    # Given / When
    config = GeneralConfig(tool_output_format="json")

    # Then
    assert config.tool_output_format == "json"


def test_general_config_with_default_thinking_level_sets_high() -> None:
    # Given
    config = GeneralConfig(tool_output_format="yaml")

    # When
    result = config.thinking_level

    # Then
    assert result == "HIGH"


def test_general_config_with_custom_thinking_level_stores_level() -> None:
    # Given
    config = GeneralConfig(tool_output_format="yaml", thinking_level="LOW")

    # When
    result = config.thinking_level

    # Then
    assert result == "LOW"


def test_general_config_with_invalid_tool_output_format_raises_validation_error() -> None:
    # Given
    invalid_data: dict[str, Any] = {"tool_output_format": "xml"}

    # When / Then
    with pytest.raises(ValidationError):
        GeneralConfig.model_validate(invalid_data)


def test_general_config_with_invalid_thinking_level_raises_validation_error() -> None:
    # Given
    invalid_data: dict[str, Any] = {"tool_output_format": "yaml", "thinking_level": "EXTREME"}

    # When / Then
    with pytest.raises(ValidationError):
        GeneralConfig.model_validate(invalid_data)


def test_general_config_with_missing_tool_output_format_raises_validation_error() -> None:
    # Given
    invalid_data: dict[str, Any] = {}

    # When / Then
    with pytest.raises(ValidationError):
        GeneralConfig.model_validate(invalid_data)


# =============================================================================
# AgentConfig Tests
# =============================================================================


def test_agent_config_with_default_values_sets_empty_tools() -> None:
    # Given / When
    config = AgentConfig()

    # Then
    assert config.tools == {}


def test_agent_config_with_default_values_sets_empty_hooks() -> None:
    # Given / When
    config = AgentConfig()

    # Then
    assert config.hooks == {}


def test_agent_config_with_default_values_sets_empty_clients() -> None:
    # Given / When
    config = AgentConfig()

    # Then
    assert config.clients == []


def test_agent_config_with_default_values_sets_default_prompts() -> None:
    # Given / When
    config = AgentConfig()

    # Then
    assert config.prompts.system_prompt == ""


def test_agent_config_with_custom_tools_stores_tools() -> None:
    # Given
    data: dict[str, Any] = {"tools": {"bash": {"enabled": True}}}

    # When
    config = AgentConfig.model_validate(data)

    # Then
    assert config.tools == {"bash": {"enabled": True}}


def test_agent_config_with_custom_clients_stores_clients() -> None:
    # Given
    data: dict[str, Any] = {"clients": ["client_a", "client_b"]}

    # When
    config = AgentConfig.model_validate(data)

    # Then
    assert config.clients == ["client_a", "client_b"]


# =============================================================================
# Config Tests
# =============================================================================


def test_config_with_valid_data_creates_config() -> None:
    # Given
    data = {
        "general": {"agents": ["coder"], "tool_output_format": "json"},
        "clients": {"manual": {"type": "manual", "foo": "bar"}},
    }

    # When
    config = Config.model_validate(data)

    # Then
    assert config.general.agents == ["coder"]


def test_config_with_optional_agents_defaults_to_empty_dict() -> None:
    # Given
    data = {
        "general": {"tool_output_format": "yaml"},
        "clients": {},
    }

    # When
    config = Config.model_validate(data)

    # Then
    assert config.agents == {}


def test_config_with_clients_stores_clients() -> None:
    # Given
    data = {
        "general": {"tool_output_format": "yaml"},
        "clients": {"all": {"use_xhigh_not_high": True}},
    }

    # When
    config = Config.model_validate(data)

    # Then
    assert config.clients == {"all": {"use_xhigh_not_high": True}}


def test_config_with_missing_general_raises_validation_error() -> None:
    # Given
    data: dict[str, Any] = {"clients": {}}

    # When / Then
    with pytest.raises(ValidationError):
        Config.model_validate(data)


def test_config_with_missing_clients_raises_validation_error() -> None:
    # Given
    data: dict[str, Any] = {"general": {"tool_output_format": "yaml"}}

    # When / Then
    with pytest.raises(ValidationError):
        Config.model_validate(data)


# =============================================================================
# load() Tests
# =============================================================================

VALID_CONFIG_TOML = """\
[general]
agents = ["coder"]
tool_output_format = "json"

[clients.manual]
type = "manual"
foo = "bar"

[prompts]
system_prompt = "System: {{ name }}"
user_prompt = "Initial: {{ query }}"
"""


def test_load_with_valid_toml_returns_config_with_correct_agents(fs) -> None:
    # Given
    config_file = Path("/config.toml")
    fs.create_file(config_file, contents=VALID_CONFIG_TOML)

    # When
    config = load(config_file)

    # Then
    assert config.general.agents == ["coder"]


def test_load_with_valid_toml_returns_config_with_clients_dict(fs) -> None:
    # Given
    config_file = Path("/config.toml")
    fs.create_file(config_file, contents=VALID_CONFIG_TOML)

    # When
    config = load(config_file)

    # Then
    assert isinstance(config.clients, dict)


def test_load_with_valid_toml_creates_default_agent_for_listed_agent(fs) -> None:
    # Given
    config_file = Path("/config.toml")
    fs.create_file(config_file, contents=VALID_CONFIG_TOML)

    # When
    config = load(config_file)

    # Then
    assert "coder" in config.agents


def test_load_with_nonexistent_file_raises_file_not_found_error() -> None:
    # Given
    nonexistent_path = Path("/non_existent_config.toml")

    # When / Then
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load(nonexistent_path)


def test_load_with_invalid_toml_raises_value_error(fs) -> None:
    # Given
    config_file = Path("/invalid.toml")
    fs.create_file(config_file, contents="invalid = [toml")

    # When / Then
    with pytest.raises(ValueError, match="Invalid TOML"):
        load(config_file)


def test_load_with_missing_required_fields_raises_validation_error(fs) -> None:
    # Given
    config_file = Path("/incomplete.toml")
    fs.create_file(config_file, contents='[general]\ntool_output_format = "yaml"\n')

    # When / Then
    with pytest.raises(ValidationError):
        load(config_file)


def test_load_with_thinking_level_stores_level(fs) -> None:
    # Given
    config_file = Path("/config.toml")
    content = """\
[general]
agents = ["coder"]
tool_output_format = "yaml"
thinking_level = "LOW"

[clients.manual]

[prompts]
system_prompt = "System"
user_prompt = "User"
"""
    fs.create_file(config_file, contents=content)

    # When
    config = load(config_file)

    # Then
    assert config.general.thinking_level == "LOW"


def test_load_with_agent_section_populates_agent_tools(fs) -> None:
    # Given
    config_file = Path("/config.toml")
    content = """\
[general]
agents = ["coder"]
tool_output_format = "yaml"

[clients.google]
type = "google"

[agents.coder.tools.bash]
enabled = true

[prompts]
system_prompt = "System"
user_prompt = "User"
"""
    fs.create_file(config_file, contents=content)

    # When
    config = load(config_file)

    # Then
    assert config.agents["coder"].tools == {"bash": {"enabled": True}}


def test_load_with_undefined_agent_name_raises_validation_error(fs) -> None:
    # Given
    config_file = Path("/config.toml")
    content = """\
[general]
agents = ["coder"]
tool_output_format = "yaml"

[clients.google]
type = "google"

[agents.reviewer]

[prompts]
system_prompt = "System"
user_prompt = "User"
"""
    fs.create_file(config_file, contents=content)

    # When / Then
    with pytest.raises(ValueError, match="Invalid agent name"):
        load(config_file)


def test_load_with_unknown_client_in_agent_raises_validation_error(fs) -> None:
    # Given
    config_file = Path("/config.toml")
    content = """\
[general]
agents = ["coder"]
tool_output_format = "yaml"

[clients.google]
type = "google"

[agents.coder]
clients = ["nonexistent"]

[prompts]
system_prompt = "System"
user_prompt = "User"
"""
    fs.create_file(config_file, contents=content)

    # When / Then
    with pytest.raises(ValueError, match="Unknown client"):
        load(config_file)


def test_load_with_global_tools_merges_into_agent(fs) -> None:
    # Given
    config_file = Path("/config.toml")
    content = """\
[general]
agents = ["coder"]
tool_output_format = "yaml"

[clients.google]
type = "google"

[tools.bash]
enabled = true

[prompts]
system_prompt = "System"
user_prompt = "User"
"""
    fs.create_file(config_file, contents=content)

    # When
    config = load(config_file)

    # Then
    assert config.agents["coder"].tools["bash"] == {"enabled": True}


def test_load_with_global_hooks_merges_into_agent(fs) -> None:
    # Given
    config_file = Path("/config.toml")
    content = """\
[general]
agents = ["coder"]
tool_output_format = "yaml"

[clients.google]
type = "google"

[hooks.autoapproval]
enabled = true

[prompts]
system_prompt = "System"
user_prompt = "User"
"""
    fs.create_file(config_file, contents=content)

    # When
    config = load(config_file)

    # Then
    assert config.agents["coder"].hooks["autoapproval"] == {"enabled": True}


def test_load_with_global_prompts_propagates_to_agent(fs) -> None:
    # Given
    config_file = Path("/config.toml")
    content = """\
[general]
agents = ["coder"]
tool_output_format = "yaml"

[clients.google]
type = "google"

[prompts]
system_prompt = "Global System"
user_prompt = "Global User"
"""
    fs.create_file(config_file, contents=content)

    # When
    config = load(config_file)

    # Then
    assert config.agents["coder"].prompts.system_prompt == "Global System"


def test_load_with_agent_specific_system_prompt_does_not_override(fs) -> None:
    # Given
    config_file = Path("/config.toml")
    content = """\
[general]
agents = ["coder"]
tool_output_format = "yaml"

[clients.google]
type = "google"

[agents.coder.prompts]
system_prompt = "Agent System"

[prompts]
system_prompt = "Global System"
user_prompt = "User"
"""
    fs.create_file(config_file, contents=content)

    # When
    config = load(config_file)

    # Then
    assert config.agents["coder"].prompts.system_prompt == "Agent System"


def test_load_with_no_clients_in_agent_assigns_all_clients(fs) -> None:
    # Given
    config_file = Path("/config.toml")
    content = """\
[general]
agents = ["coder"]
tool_output_format = "yaml"

[clients.google]
type = "google"

[clients.openai]
type = "anyllm"

[prompts]
system_prompt = "System"
user_prompt = "User"
"""
    fs.create_file(config_file, contents=content)

    # When
    config = load(config_file)

    # Then
    assert set(config.agents["coder"].clients) == {"google", "openai"}


def test_load_with_agent_missing_system_prompt_and_no_global_raises_value_error(fs) -> None:
    # Given
    config_file = Path("/config.toml")
    content = """\
[general]
agents = ["coder"]
tool_output_format = "yaml"

[clients.google]
type = "google"

[prompts]
user_prompt = "User"
"""
    fs.create_file(config_file, contents=content)

    # When / Then
    with pytest.raises(ValueError, match="has no system prompt"):
        load(config_file)


# =============================================================================
# write_default() Tests
# =============================================================================

TEMPLATE_CONTENT_WITH_ONE_API_KEY = """\
[general]
agents = ["coder"]
tool_output_format = "yaml"

[clients.google]
type = "google"
model = "gemma-4-31b-it"
api_key_env_var = "GEMINI_API_KEY"

[prompts]
system_prompt = "System"
user_prompt = "User"
"""

TEMPLATE_CONTENT_WITH_TWO_API_KEYS = """\
[general]
agents = ["coder"]
tool_output_format = "yaml"

[clients.google]
type = "google"
model = "gemma-4-31b-it"
api_key_env_var = "GEMINI_API_KEY"

[clients.anyllm]
type = "anyllm"
provider = "openai"
model = "gpt-4"
api_key_env_var = "OPENAI_API_KEY"

[prompts]
system_prompt = "System"
user_prompt = "User"
"""


def _create_mock_resources(mocker: MockerFixture, template_content: str) -> None:
    """Helper to mock importlib.resources.files for write_default tests."""
    mock_file = MagicMock()
    mock_file.read_text.return_value = template_content
    mock_root = MagicMock()
    mock_root.__truediv__.return_value = mock_file
    mocker.patch("frugalbot.config.resources.files", return_value=mock_root)


def test_write_default_creates_config_file_from_template(fs, mocker: MockerFixture) -> None:
    # Given
    config_path = Path("/home/user/.frugalbot/config.toml")
    env_path = Path("/home/user/.frugalbot/.env")
    _create_mock_resources(mocker, TEMPLATE_CONTENT_WITH_ONE_API_KEY)

    # When
    write_default(config_file_path=config_path, env_file_path=env_path)

    # Then
    assert config_path.exists()


def test_write_default_writes_template_content_to_config_file(fs, mocker: MockerFixture) -> None:
    # Given
    config_path = Path("/home/user/.frugalbot/config.toml")
    env_path = Path("/home/user/.frugalbot/.env")
    _create_mock_resources(mocker, TEMPLATE_CONTENT_WITH_ONE_API_KEY)

    # When
    write_default(config_file_path=config_path, env_file_path=env_path)

    # Then
    assert config_path.read_text(encoding="utf-8") == TEMPLATE_CONTENT_WITH_ONE_API_KEY


def test_write_default_creates_env_file_when_not_exists(fs, mocker: MockerFixture) -> None:
    # Given
    config_path = Path("/home/user/.frugalbot/config.toml")
    env_path = Path("/home/user/.frugalbot/.env")
    _create_mock_resources(mocker, TEMPLATE_CONTENT_WITH_ONE_API_KEY)

    # When
    write_default(config_file_path=config_path, env_file_path=env_path)

    # Then
    assert env_path.exists()


def test_write_default_writes_api_key_vars_to_env_file(fs, mocker: MockerFixture) -> None:
    # Given
    config_path = Path("/home/user/.frugalbot/config.toml")
    env_path = Path("/home/user/.frugalbot/.env")
    _create_mock_resources(mocker, TEMPLATE_CONTENT_WITH_TWO_API_KEYS)

    # When
    write_default(config_file_path=config_path, env_file_path=env_path)

    # Then
    assert "GEMINI_API_KEY=<CHANGE_ME>" in env_path.read_text(encoding="utf-8")


def test_write_default_with_existing_env_file_does_not_overwrite(fs, mocker: MockerFixture) -> None:
    # Given
    config_path = Path("/home/user/.frugalbot/config.toml")
    env_path = Path("/home/user/.frugalbot/.env")
    original_env_content = "EXISTING_KEY=existing_value"
    fs.create_file(env_path, contents=original_env_content)
    _create_mock_resources(mocker, TEMPLATE_CONTENT_WITH_ONE_API_KEY)

    # When
    write_default(config_file_path=config_path, env_file_path=env_path)

    # Then
    assert env_path.read_text(encoding="utf-8") == original_env_content


def test_write_default_creates_parent_directories(fs, mocker: MockerFixture) -> None:
    # Given
    config_path = Path("/home/user/.frugalbot/nested/config.toml")
    env_path = Path("/home/user/.frugalbot/nested/.env")
    _create_mock_resources(mocker, TEMPLATE_CONTENT_WITH_ONE_API_KEY)

    # When
    write_default(config_file_path=config_path, env_file_path=env_path)

    # Then
    assert config_path.parent.exists()


def test_merge_global_with_agent_specific_section_keeps_most_specific_config() -> None:
    # given
    all_section_name = "all"
    section_name = "foo"
    global_config = {
        all_section_name: {"global_all": "gao1", "global_specific": "gsbad1", "agent_all": "aabad1", "agent_specific": "bad1"},
        section_name: {"global_specific": "gs1", "agent_all": "aabad2", "agent_specific": "bad2"},
    }
    agent_config = {all_section_name: {"agent_all": "aa1", "agent_specific": "bad3"}, section_name: {"agent_specific": "ias1"}}

    # when
    merged = _merge_global_with_agent_specific_section(global_config, agent_config)

    # then
    assert all_section_name not in merged
    assert merged[section_name]["global_all"] == "gao1"
    assert merged[section_name]["global_specific"] == "gs1"
    assert merged[section_name]["agent_all"] == "aa1"
    assert merged[section_name]["agent_specific"] == "ias1"
