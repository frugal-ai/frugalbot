## 1. Architecture

```
Parent Agent (depth=0, ancestors=["coder"])
       │
       ▼ calls tool: spawn(agent="wiki_master", prompt="...")
  Spawn Tool
       │ verifies: target in allowed_agents, target not in ancestors, depth < max_depth
       │ calls: resolver("wiki_master", depth=1, ancestors=["coder", "wiki_master"])
       ▼
Sub-Agent (depth=1, ancestors=["coder", "wiki_master"])
       │ conversation initialized with emit_events=False (no bus leaks: system, user, status)
       │ runs: sub_agent.run(prompt)
       │ persists: ~/.frugalbot/sessions/subagent_wiki_master_*.json
       │ extracts: substantive response (skipping ValidateFinished confirmation)
       ▼
  SpawnResult(agent="wiki_master", status="completed", response="...")
       │
       ▼ returns to Parent Agent context
Parent Agent receives structured tool output & continues reasoning loop
```

---

## 2. Component Design

### A. New Tool: `src/frugalbot/tools/spawn.py`

```python
from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Annotated, Literal, Protocol, TYPE_CHECKING
import pydantic
from frugalbot.events import MessageEvent, MessageType, bus
from frugalbot.hooks.validate_finished import _VERIFICATION_MESSAGE_PREFIX
from frugalbot.tools.base import ToolBase, ToolConfig, ToolError

if TYPE_CHECKING:
    from frugalbot.agent import Agent
    from frugalbot.conversation import Conversation


class SpawnResult(pydantic.BaseModel):
    agent: str
    status: Literal["completed", "error"]
    response: str


class SpawnConfig(ToolConfig):
    allowed_agents: list[str] = pydantic.Field(default_factory=list)
    max_depth: int = 1


class AgentResolver(Protocol):
    def __call__(
        self,
        agent_name: str,
        spawn_depth: int,
        ancestors: list[str],
    ) -> Awaitable[Agent]: ...


def _extract_subagent_response(conversation: Conversation) -> str:
    """Extract substantive assistant message, skipping ValidateFinished confirmation."""
    messages = conversation.messages
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if isinstance(msg, dict) or msg.role != "assistant":
            continue
        content = (msg.content or "").strip()
        is_yes = content.upper().strip(".'\"") == "YES"
        if is_yes and i > 0:
            prev_msg = messages[i - 1]
            if isinstance(prev_msg, dict) and prev_msg.get("role") == "user":
                prev_content = prev_msg.get("content", "")
                if prev_content.startswith(_VERIFICATION_MESSAGE_PREFIX):
                    continue  # Skip ValidateFinished confirmation
        if content:
            return content

    for msg in reversed(messages):
        if not isinstance(msg, dict) and msg.role == "assistant" and msg.content:
            return msg.content.strip()

    return ""


class Spawn(ToolBase[SpawnResult, SpawnConfig]):
    """Spawn a sub-agent, delegate a task to it, and return its final answer."""

    def __init__(self, config: SpawnConfig) -> None:
        super().__init__(config)
        self._parent_name: str | None = None
        self._parent_depth: int = 0
        self._ancestors: list[str] = []
        self._resolver: AgentResolver | None = None

    def set_parent_context(
        self,
        parent_name: str,
        parent_depth: int,
        ancestors: list[str],
        resolver: AgentResolver,
    ) -> None:
        self._parent_name = parent_name
        self._parent_depth = parent_depth
        self._ancestors = ancestors
        self._resolver = resolver

    def get_guidelines(self) -> list[str]:
        guidelines = [
            "Use this tool to delegate a self-contained task to a specialist agent.",
            "The sub-agent runs in an isolated conversation and cannot see the current conversation history.",
            "Provide all necessary context, background, and instructions in the prompt.",
            "Prefer performing the task yourself if it does not require the sub-agent's specialized tools or domain expertise.",
        ]
        if self.config.allowed_agents:
            guidelines.append(f"Available specialist agents you can delegate to: {', '.join(self.config.allowed_agents)}.")
        return guidelines

    async def run(
        self,
        agent: Annotated[str, "The name of the agent to spawn and delegate the task to."],
        prompt: Annotated[str, "The complete task prompt and context for the sub-agent."],
    ) -> SpawnResult:
        if self._resolver is None:
            raise ToolError("Spawn tool is not configured with an agent resolver.")

        if self._parent_depth >= self.config.max_depth:
            raise ToolError(f"Maximum spawn depth of {self.config.max_depth} reached (current depth: {self._parent_depth}).")

        if agent in self._ancestors:
            chain = " -> ".join([*self._ancestors, agent])
            raise ToolError(f"Cannot spawn agent '{agent}': cycle detected in active delegation chain ({chain}).")

        if not self.config.allowed_agents or agent not in self.config.allowed_agents:
            raise ToolError(f"Agent '{agent}' is not in allowed_agents list: {self.config.allowed_agents}.")

        sub_agent = await self._resolver(agent, self._parent_depth + 1, [*self._ancestors, agent])

        try:
            await sub_agent.run(prompt)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return SpawnResult(agent=agent, status="error", response=f"Sub-agent failed with exception: {exc!s}")

        response_text = _extract_subagent_response(sub_agent.conversation)
        if not response_text:
            response_text = "Sub-agent finished without producing a text response."

        await bus.emit_and_handle(MessageEvent(f"Sub-agent '{agent}' completed task.", MessageType.TOOL_OUTPUT))
        return SpawnResult(agent=agent, status="completed", response=response_text)
```

---

### B. `src/frugalbot/tools/base.py`

Add an optional lookup method on `Tools` to avoid inspecting `_tools_registry` directly:

```python
    def get_optional(self, tool_name: str) -> ToolBase | None:
        return self._tools_registry.get(tool_name)
```

---

### C. `src/frugalbot/conversation.py`

Add `emit_events` to suppress TUI event emissions for sub-agents:

```python
class Conversation:
    def __init__(self, hooks: Hooks, emit_events: bool = True):
        self.hooks = hooks
        self.emit_events = emit_events
        self._messages: list[dict[str, Any] | tuple[str, ChatCompletion]] = []

    async def append_system_message(self, content: str, emit_event: bool | None = None) -> None:
        if len(self._messages) > 0:
            raise ValueError("System message must be the first message in the conversation")
        hook_data = PreSystemMessageHook(content=content)
        await self.hooks.run(hook_data)
        self._append_message(role="system", content=hook_data.content)
        should_emit = self.emit_events if emit_event is None else emit_event
        if should_emit:
            await bus.emit_and_handle(MessageEvent(hook_data.content, MessageType.SYSTEM, MessageMarkup.MARKDOWN))

    async def append_user_message(self, content: str, emit_event: bool | None = None) -> None:
        hook_data = PreUserMessageHook(content=content)
        await self.hooks.run(hook_data)
        self._append_message(role="user", content=hook_data.content)
        should_emit = self.emit_events if emit_event is None else emit_event
        if should_emit:
            await bus.emit_and_handle(MessageEvent(hook_data.content, MessageType.USER))
```

---

### D. `src/frugalbot/agent.py`

1. Update `_get_unique_conversation_file_path` to support prefixing:
   ```python
   def _get_unique_conversation_file_path(prefix: str = "") -> Path:
       stem = datetime.now().strftime(_SESSION_FILE_NAME_DATETIME_FORMAT)
       base_name = f"{prefix}{stem}" if prefix else stem
       conversation_file_path = _SESSIONS_BASE_PATH / f"{base_name}.json"
       suffix_index = 2
       while conversation_file_path.exists():
           conversation_file_path = _SESSIONS_BASE_PATH / f"{base_name}-{suffix_index}.json"
           suffix_index += 1
       return conversation_file_path
   ```

2. Add `spawn_depth: int = 0` to `Agent.__init__`:
   ```python
   class Agent:
       def __init__(
           self,
           name: str,
           general_config: GeneralConfig,
           agent_config: AgentConfig,
           clients: LLMClients,
           tools: Tools,
           hooks: Hooks,
           skills: Skills,
           spawn_depth: int = 0,
       ):
           self.name = name
           self.spawn_depth = spawn_depth
           ...
           self.conversation = Conversation(self.hooks, emit_events=(self.spawn_depth == 0))
           self._initialized = False
   ```

3. Update `new_conversation()` to prefix file names and suppress tools schema on the bus when `spawn_depth > 0`:
   ```python
       async def new_conversation(self) -> None:
           self.conversation = Conversation(self.hooks, emit_events=(self.spawn_depth == 0))
           prefix = f"subagent_{self.name}_" if self.spawn_depth > 0 else ""
           self.conversation_file_path = _get_unique_conversation_file_path(prefix)
           sys_msg = await render_system_prompt(self.general_config, self.tools, self.skills, self.hooks, self.config.prompts.system_prompt)
           if self.spawn_depth == 0:
               await bus.emit_and_handle(
                   MessageEvent(f"Tools schema:\n```json\n{json.dumps([tool.get_schema() for tool in self.tools.get_all()], option=json.OPT_INDENT_2).decode('utf-8')}\n```", MessageType.SYSTEM, MessageMarkup.MARKDOWN)
               )
           await self.conversation.append_system_message(sys_msg)
           await self._emit_status_update()
           self._initialized = True
   ```

4. In `_emit_status_update()`, suppress status bar emission when running as a sub-agent:
   ```python
       async def _emit_status_update(self) -> None:
           if self.spawn_depth > 0:
               return  # Do not clobber parent agent's TUI status bar
           ...
           await bus.emit_and_handle(StatusUpdateEvent(self.name, provider.lower(), self.client.model, self.client.thinking_level, self.conversation.get_usage().total_tokens, context_size, cost))
   ```

---

### E. `src/frugalbot/agents.py`

1. Retain `self.config` and `self.skills` on `Agents`.
2. Ensure state attributes are initialized **before** creating agents.
3. Implement `build_agent` and refactor agent creation:

```python
async def build_agent(
    self,
    agent_name: str,
    spawn_depth: int = 0,
    ancestors: list[str] | None = None,
) -> Agent:
    if self.config is None or self.skills is None or self.clients is None:
        raise RuntimeError("Agents manager not initialized.")
    if agent_name not in self.config.agents:
        raise KeyError(f"Unknown agent '{agent_name}'")

    agent_config = self.config.agents[agent_name]
    tools = Tools()
    tools.load(agent_config.tools)

    mcp_tools = await self.mcp_sessions.get_tools() if self.mcp_sessions else []
    tools.add(cast(list[ToolBase], _build_mcp_tool_list_for_agent(agent_config, mcp_tools)))

    current_ancestors = ancestors or [agent_name]

    spawn_tool_raw = tools.get_optional("spawn")
    if spawn_tool_raw is not None:
        from frugalbot.tools.spawn import Spawn

        spawn_tool = cast(Spawn, spawn_tool_raw)
        if spawn_tool.config.enabled:
            if not spawn_tool.config.allowed_agents:
                raise ValueError(f"Agent '{agent_name}' has spawn tool enabled but 'allowed_agents' list is empty.")
            for target in spawn_tool.config.allowed_agents:
                if target == agent_name:
                    raise ValueError(f"Agent '{agent_name}' cannot have itself in 'allowed_agents' for spawn tool.")
                if target not in self.config.agents:
                    raise ValueError(f"Agent '{agent_name}' has invalid allowed_agent '{target}' for spawn tool. Must be one of: {list(self.config.agents.keys())}")
        spawn_tool.set_parent_context(
            parent_name=agent_name,
            parent_depth=spawn_depth,
            ancestors=current_ancestors,
            resolver=self.build_agent,
        )

    hooks = Hooks()
    hooks.load(agent_config.hooks)
    agent_skills = Skills([skill for skill in self.skills.get_all() if agent_config.skills is None or skill.name in agent_config.skills])

    return Agent(
        name=agent_name,
        general_config=self.config.general,
        agent_config=agent_config,
        clients=self.clients,
        tools=tools,
        hooks=hooks,
        skills=agent_skills,
        spawn_depth=spawn_depth,
    )
```

4. Update `Agents.load()` and `Agents.reload()`:
```python
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

    # Set dependencies prior to building agents so build_agent has full context
    self.config = config
    self.skills = skills
    self.clients = clients
    self.mcp_servers = mcp_servers
    self.mcp_sessions = mcp_sessions
    self.config_file_path = config_file_path
    self.env_file_path = env_file_path

    try:
        _update_status(status, "[bold green]Loading agents...")
        self.agents = {}
        for agent_name in config.agents:
            self.agents[agent_name] = await self.build_agent(agent_name, spawn_depth=0)
    except Exception:
        self.config = None
        self.skills = None
        self.clients = None
        self.mcp_sessions = None
        self.agents.clear()
        if self.mcp_servers:
            try:
                await self.mcp_servers.disconnect_all()
            except Exception:
                pass
            self.mcp_servers = None
        raise


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
    self.config = None
    self.skills = None
    self.mcp_servers = None
    self.mcp_sessions = None
    await self.load(self.config_file_path, self.env_file_path)
```

---

### F. Configuration (`config_template.toml`)

```toml
[tools.spawn]
enabled = false
# List of agent names this tool is permitted to delegate to.
# Must match agent names defined under [agents.<name>].
allowed_agents = ["wiki_master"]
# Maximum recursion depth for nested delegations (default: 1).
max_depth = 1
```

---

## 3. Summary of Files Changed

| File | Change |
|---|---|
| `src/frugalbot/tools/spawn.py` | **New**: `Spawn`, `SpawnResult`, `SpawnConfig`, `AgentResolver`, and response extraction. |
| `src/frugalbot/tools/base.py` | Add `Tools.get_optional()`. |
| `src/frugalbot/conversation.py` | Add `emit_events` flag to `Conversation` and default message append methods. |
| `src/frugalbot/agent.py` | Add `spawn_depth` parameter; prefix subagent session file names; suppress tools schema and `StatusUpdateEvent` for sub-agents. |
| `src/frugalbot/agents.py` | Retain `config` & `skills`; initialize attributes before building agents; add `build_agent()` with config-time validation. |
| `src/frugalbot/config_template.toml` | Document `[tools.spawn]`. |
| `tests/frugalbot/tools/test_spawn.py` | **New**: Comprehensive unit tests covering all GWT scenarios and edge cases. |
| `tests/frugalbot/test_agents.py` | Tests for `build_agent`, validation, depth increments, and event isolation. |

---

## 4. Test Specifications (GWT Pattern & Strict Typing)

All tests must follow `docs/testing_guidelines.md` (in-memory, single assertion exit point, no test logic):

### `tests/frugalbot/tools/test_spawn.py`
1. `test_run_with_uninitialized_resolver_raises_tool_error`: Calling `run()` before `set_parent_context()` raises `ToolError`.
2. `test_run_with_disallowed_agent_raises_tool_error`: Target not in `allowed_agents` raises `ToolError`.
3. `test_run_with_ancestor_target_raises_tool_error`: Spawning an agent present in `_ancestors` raises `ToolError`.
4. `test_run_when_depth_equals_max_depth_raises_tool_error`: `parent_depth >= max_depth` raises `ToolError`.
5. `test_run_with_valid_agent_and_prompt_returns_completed_result`: Resolves sub-agent, runs prompt, and returns `SpawnResult(status="completed", ...)`.
6. `test_run_with_validate_finished_confirmation_extracts_substantive_response`: Extracts the pre-confirmation response when the final message is `"YES"`.
7. `test_run_with_validate_finished_punctuation_extracts_substantive_response`: Extracts the pre-confirmation response when the final confirmation is `"YES."`.
8. `test_run_when_subagent_raises_exception_returns_error_result`: Captures exception and returns `SpawnResult(status="error", response=...)`.
9. `test_run_when_subagent_cancelled_propagates_cancellation_error`: Verifies `asyncio.CancelledError` is not swallowed.
10. `test_get_guidelines_with_allowed_agents_returns_specialist_list`: Guidelines string lists allowed agents.
11. `test_get_schema_always_returns_valid_parameter_schema`: Validates that parameter descriptions are generated for `agent` and `prompt`.

### `tests/frugalbot/test_agents.py`
1. `test_build_agent_with_spawn_tool_injects_parent_context`: Injects resolver, `parent_depth`, and `ancestors`.
2. `test_build_agent_with_missing_allowed_agents_raises_value_error`: Enabled spawn tool with empty `allowed_agents` raises `ValueError`.
3. `test_build_agent_with_self_in_allowed_agents_raises_value_error`: Target matching own name raises `ValueError`.
4. `test_build_agent_with_unknown_allowed_agent_raises_value_error`: Target missing from `config.agents` raises `ValueError`.
5. `test_build_agent_when_subagent_spawned_increments_spawn_depth`: Generated sub-agent receives `parent_depth + 1`.
6. `test_new_conversation_with_subagent_depth_suppresses_system_bus_events`: `spawn_depth > 0` produces zero `MessageType.SYSTEM` events.
7. `test_emit_status_update_with_subagent_depth_suppresses_status_bus_event`: `spawn_depth > 0` produces zero `StatusUpdateEvent` occurrences.
