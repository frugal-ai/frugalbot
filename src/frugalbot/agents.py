from pathlib import Path
from typing import cast

from dotenv import load_dotenv
from rich.status import Status

import frugalbot.config
from frugalbot.agent import Agent
from frugalbot.clients.base import LLMClients
from frugalbot.config import AgentConfig, Config
from frugalbot.hooks.base import Hooks
from frugalbot.mcp.mcp_server_config import MCPServerConfig
from frugalbot.mcp.mcp_servers import MCPServers
from frugalbot.mcp.mcp_sessions import MCPSessions
from frugalbot.mcp.mcp_tool import MCPTool
from frugalbot.skills import Skills, discover_skills
from frugalbot.tools.base import ToolBase, Tools
from frugalbot.utils.dict import get_next_value


def _build_mcp_tool_list_for_agent(agent_config: AgentConfig, mcp_tools: list[MCPTool]) -> list[MCPTool]:
    validated_configs = {server_name: MCPServerConfig.model_validate(raw_config) for server_name, raw_config in agent_config.mcp.items()}

    tools = []
    for tool in mcp_tools:
        mcp_server_config = validated_configs.get(tool.mcp_server_name)
        if mcp_server_config is None or not mcp_server_config.enabled:
            continue
        tools.append(tool)
    return tools


async def _create_agents(config: Config, clients: LLMClients, skills: Skills, mcp_sessions: MCPSessions | None) -> dict[str, Agent]:
    agents: dict[str, Agent] = {}
    mcp_tools = await mcp_sessions.get_tools() if mcp_sessions else []
    for agent_name, agent_config in config.agents.items():
        tools = Tools()
        tools.load(agent_config.tools)
        tools.add(cast(list[ToolBase], _build_mcp_tool_list_for_agent(agent_config, mcp_tools)))
        hooks = Hooks()
        hooks.load(agent_config.hooks)
        agent_skills = Skills([skill for skill in skills.get_all() if agent_config.skills is None or skill.name in agent_config.skills])
        agents[agent_name] = Agent(agent_name, config.general, agent_config, clients, tools, hooks, agent_skills)
    return agents


async def _init_mcp(config: Config) -> tuple[MCPServers, MCPSessions | None]:
    servers = MCPServers()
    enabled_server_configs: dict[str, MCPServerConfig] = {}
    for agent_config in config.agents.values():
        for server_name, raw_mcp_server_config in agent_config.mcp.items():
            mcp_server_config = MCPServerConfig.model_validate(raw_mcp_server_config)
            if not mcp_server_config.enabled:
                continue
            if server_name in enabled_server_configs:
                if enabled_server_configs[server_name].command != mcp_server_config.command:
                    raise ValueError(
                        f"Command for mcp.{server_name} cannot have different values:\n{enabled_server_configs[server_name].command}\n{mcp_server_config.command}\n\n"
                        "Use different mcp section names to configure servers with different commands."
                    )
            else:
                enabled_server_configs[server_name] = mcp_server_config
    sessions = await servers.connect_all(enabled_server_configs)
    return (servers, sessions)


def _update_status(status: Status | None, text: str):
    if status:
        status.update(text)


class Agents:
    def __init__(self) -> None:
        self.agents: dict[str, Agent] = {}
        self.config_file_path: Path | None = None
        self.env_file_path: Path | None = None
        self.clients: LLMClients | None = None
        self.mcp_servers: MCPServers | None = None
        self.mcp_sessions: MCPSessions | None = None

    async def load(self, config_file_path: Path = frugalbot.config.CONFIG_FILE_PATH, env_file_path: Path = frugalbot.config.ENV_FILE_PATH, status: Status | None = None) -> None:
        if self.agents:
            raise ValueError("Agents already loaded. Call unload first.")
        load_dotenv(env_file_path)
        config = frugalbot.config.load(config_file_path)
        clients = LLMClients()
        clients.load(config.clients)
        if not clients.get_all():
            raise ValueError("Must configure at least one client in config file")
        for client in clients.get_all():
            client.thinking_level = config.general.thinking_level
        _update_status(status, "[bold green]Loading skills...")
        skills = discover_skills()
        _update_status(status, "[bold green]Loading MCP servers...")
        mcp_servers, mcp_sessions = await _init_mcp(config)
        try:
            _update_status(status, "[bold green]Loading agents...")
            self.agents = await _create_agents(config, clients, skills, mcp_sessions)
        except Exception:
            try:
                await mcp_servers.disconnect_all()
            except Exception:
                pass
            raise

        # do this last once we know we're successful to make sure that we set all of them, or none of them
        self.config_file_path = config_file_path
        self.env_file_path = env_file_path
        self.clients = clients
        self.mcp_servers = mcp_servers
        self.mcp_sessions = mcp_sessions

    async def reload(self):
        if not self.agents or not self.config_file_path or not self.env_file_path or not self.clients:
            return
        self.clients.unload()
        for agent in self.agents.values():
            agent.hooks.unload()
            agent.tools.unload()
        if self.mcp_servers:
            await self.mcp_servers.disconnect_all()
        self.agents.clear()
        self.clients = None
        self.mcp_servers = None
        self.mcp_sessions = None
        await self.load(self.config_file_path, self.env_file_path)

    def next(self, name_of_current_agent: str | None = None) -> Agent:
        if not self.agents:
            raise RuntimeError("No agents are currently loaded.")
        if name_of_current_agent is None:
            return next(iter(self.agents.values()))
        if name_of_current_agent not in self.agents:
            raise KeyError(f"Unknown agent name {name_of_current_agent}")
        return get_next_value(self.agents, name_of_current_agent)

    def get_all(self) -> list[Agent]:
        return list(self.agents.values())
