import tomllib
from importlib import resources
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from frugalbot.utils.dict import deep_merge

ENV_FILE_PATH = Path.home() / ".frugalbot/.env"
CONFIG_FILE_PATH = Path.home() / ".frugalbot/config.toml"


ThinkingLevel = Literal["NONE", "LOW", "MEDIUM", "HIGH"]
ToolOutputFormat = Literal["yaml", "json"]


class PromptsConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    system_prompt: str = ""
    user_prompt: str = "{{user_message}}"


class GeneralConfig(BaseModel):
    agents: list[str] = ["coder"]
    tool_output_format: ToolOutputFormat
    thinking_level: ThinkingLevel = "HIGH"


class AgentConfig(BaseModel):
    tools: dict[str, dict[str, Any]] = Field(default_factory=dict)
    hooks: dict[str, dict[str, Any]] = Field(default_factory=dict)
    mcp: dict[str, dict[str, Any]] = Field(default_factory=dict)
    prompts: PromptsConfig = PromptsConfig()
    clients: list[str] = Field(default_factory=list)
    skills: list[str] | None = None


class _RawConfig(BaseModel):
    general: GeneralConfig
    clients: dict[str, dict[str, Any]]
    tools: dict[str, dict[str, Any]] = Field(default_factory=dict)
    hooks: dict[str, dict[str, Any]] = Field(default_factory=dict)
    mcp: dict[str, dict[str, Any]] = Field(default_factory=dict)
    prompts: PromptsConfig
    agents: dict[str, AgentConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_agent_sections(self) -> Self:
        for agent_name, agent_config in self.agents.items():
            if agent_name not in self.general.agents:
                raise ValueError(f"Invalid agent name: {agent_name}. Each agent name must be defined in 'agents' under [general].")
            for client_name in agent_config.clients:
                if client_name not in self.clients:
                    raise ValueError(f"Unknown client '{client_name}' in clients list for [agents.{agent_name}].")
        return self


class Config(BaseModel):
    general: GeneralConfig
    clients: dict[str, dict[str, Any]]
    agents: dict[str, AgentConfig] = Field(default_factory=dict)


def _merge_global_with_agent_specific_section(global_dict: dict[str, Any], agent_dict: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """
    Utility to retrieve all merged configurations for a category using
    the global and agent-specific category dictionaries.
    """
    items = [key for key in global_dict | agent_dict if key != "all"]
    global_all = global_dict.get("all", {})
    agent_all = agent_dict.get("all", {})
    merged_section = {}
    for item in items:
        merged = deep_merge({}, global_all)
        merged = deep_merge(merged, global_dict.get(item, {}))
        merged = deep_merge(merged, agent_all)
        merged = deep_merge(merged, agent_dict.get(item, {}))
        merged_section[item] = merged
    return merged_section


def load(path: Path) -> Config:
    try:
        with path.open("rb") as f:
            raw_data = tomllib.load(f)
        raw_config = _RawConfig.model_validate(raw_data, extra="forbid")
        all_client_names = [client_name for client_name in raw_config.clients.keys() if client_name != "all"]

        for agent_name in raw_config.general.agents:
            raw_config.agents.setdefault(agent_name, AgentConfig())

        for agent_name, agent_config in raw_config.agents.items():
            agent_config.tools = _merge_global_with_agent_specific_section(raw_config.tools, agent_config.tools)
            agent_config.hooks = _merge_global_with_agent_specific_section(raw_config.hooks, agent_config.hooks)
            agent_config.mcp = _merge_global_with_agent_specific_section(raw_config.mcp, agent_config.mcp)
            if not agent_config.prompts.system_prompt:
                if not raw_config.prompts.system_prompt:
                    raise ValueError(f"Agent {agent_name} has no system prompt configured. Configure one in the global [prompts] section, or in the agent-specific section [agents.{agent_name}.prompts].")
                else:
                    agent_config.prompts.system_prompt = raw_config.prompts.system_prompt
            if not agent_config.prompts.user_prompt:
                agent_config.prompts.user_prompt = raw_config.prompts.user_prompt
            if not agent_config.clients:
                agent_config.clients = all_client_names.copy()

        merged_clients_config = {}
        for client_name, client_config in raw_config.clients.items():
            if client_name == "all":
                continue
            client_config["name"] = client_name
            merged_clients_config[client_name] = deep_merge(raw_config.clients.get("all", {}), client_config)

        config = Config(general=raw_config.general, clients=merged_clients_config, agents=raw_config.agents)
        return config
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"Invalid TOML in {path}: {e}") from e


def write_default(config_file_path: Path = CONFIG_FILE_PATH, env_file_path: Path = ENV_FILE_PATH):
    template_file_path = resources.files(__package__) / "config_template.toml"
    config_file_contents = template_file_path.read_text(encoding="utf-8")
    config_file_path.parent.mkdir(parents=True, exist_ok=True)
    config_file_path.write_text(config_file_contents, encoding="utf-8")
    if not env_file_path.exists():
        config = load(config_file_path)
        env_var_names = set()
        for client_config in config.clients.values():
            api_key_env_var = client_config.get("api_key_env_var")
            if api_key_env_var:
                env_var_names.add(api_key_env_var)
        env_file_lines = [f"{env_var_name}=<CHANGE_ME>" for env_var_name in env_var_names]
        env_file_path.write_text("\n".join(env_file_lines), encoding="utf-8")
