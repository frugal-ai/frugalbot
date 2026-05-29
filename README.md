# frugalbot

Yet another coding harness agent.

Goals of the project:
- Minimize the context size
- Minimize costs (by reducing context size AND the number of LLM API calls)
- Maximize operating efficiency (having the right tools to do the job)
- Provide general agent functionality beyond coding
- Maximize transparency of what is sent to the LLM
- Maximize customizability and extensiblity

## Features

- **Multi-LLM Support**: Works with Google Gemini (natively), any provider supported by any-llm-sdk ([list](https://docs.mozilla.ai/providers)) and manually (human-in-the-loop)
- **Rich Tool Ecosystem**: Built-in tools for file operations and code execution
- **Textual TUI**: Modern terminal user interface built with [Textual](https://textual.textualize.io/)
- **Session Management**: Save and restore conversation sessions
- **Token Usage Tracking**: Monitor token consumption and estimated costs
- **Plugin System**: Extensible architecture with support for custom hooks
- **Tool Approval Workflow**: Pre-approve tools or require user confirmation for safety
- **Configuration**: TOML-based configuration system

## Limitations

The project has currently only been tested on Windows. Linux and macOS support likely requires small fixes.

## Getting Started

### Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer) package manager

### Installation

```bash
uv tool install git+https://github.com/frugal-ai/frugalbot.git
```

or if you want to try it without installing:

```bash
uvx --from git+https://github.com/frugal-ai/frugalbot.git frugalbot
```

### Configuration

Run frugalbot:

```bash
uv tool run frugalbot
```

The first time you run frugalbot, it will generate default config and env files in `~/.frugalbot/`. Open and edit the files to customize them for your environment. The documentation for all configuration options is in the generated config file.

If you're looking for free LLM API options, see [here](https://github.com/mnfst/awesome-free-llm-apis).

### Running the Agent

Once you've run frugalbot once and have customized the configuration files, run frugalbot again:

```bash
uv tool run frugalbot

# There's a few command-line options available, use --help to see them
uv tool run frugalbot --help
```

### Session Files

Sessions are saved in json files under `~/.frugalbot/sessions/`.

## Extending frugalbot

### Custom Tools

Create custom tools by placing Python files in `.frugalbot/tools/` (local) or `~/.frugalbot/tools/` (global). Each tool must:

1. Inherit from `ToolBase[T]` where `T` is the result type
2. Have an `__init__` method that accepts a config object (`ToolConfig` or a sub-class of `ToolConfig`)
3. Implement the async `run` method with properly annotated parameters using `Annotated` for descriptions

```python
from typing import Annotated
import pydantic
from frugalbot.tools.base import ToolBase, ToolConfig


class MyToolConfig(ToolConfig):
    api_key: str = ""


class MyCustomTool(ToolBase[str]):
    """Description of what your tool does."""

    def __init__(self, config: MyToolConfig):
        self.config = config

    async def run(
        self,
        param1: Annotated[str, "Description of param1"],
        param2: Annotated[int, "Description of param2"] = 10,
    ) -> str:
        # Your tool logic here
        return f"Result: {param1} with {param2}"
```

Configure your tool in `config.toml`:

```toml
[tools.mycustomtool]
enabled = true
api_key = "your-api-key"
```

For more examples, see [tools](src/frugalbot/tools/).

### Custom Hooks

Hooks allow you to intercept and modify agent behavior at specific points. Create custom hooks in `.frugalbot/hooks/` or `~/.frugalbot/hooks/`.

Available hook types:
- `PreUserMessageHook` - Before processing user message
- `PreSystemMessageHook` - Before rendering system message
- `PreToolCallHook` - Before a tool is called (can approve/deny)
- `PostToolCallHook` - After a tool call completes
- `PreRenderSystemPromptHook` - Before system prompt rendering
- `PreRenderUserPromptHook` - Before user prompt rendering
- `AgentStopHook` - When agent decides to stop
- `AgentFinishedHook` - When agent finishes completely

```python
from frugalbot.hooks.base import HookBase, HookConfig, HookPriority, PreToolCallHook


class MyHookConfig(HookConfig):
    custom_setting: str = ""


class MyCustomHook(HookBase[PreToolCallHook]):
    """Description of your hook."""

    def __init__(self, config: MyHookConfig):
        self.config = config

    # priority is only needed if there are multiple hooks of the same type and they need to run in a specific order
    @property
    def priority(self) -> HookPriority:
        return HookPriority.MEDIUM

    async def run(self, hook_data: PreToolCallHook):
        if not self.config.enabled:
            return
        # Modify hook_data or perform side effects
        if hook_data.tool_name == "bash":
            hook_data.state = ApprovalState.DENIED
            hook_data.denied_reason = "Bash is disabled"
```

Configure hooks in `config.toml`:

```toml
[hooks.mycustomhook]
enabled = true
custom_setting = "value"
```

For more examples, see [hooks](src/frugalbot/hooks/).

### Custom Commands

Commands are invoked by the user with `/commandname` syntax. Create custom commands in `.frugalbot/commands/` or `~/.frugalbot/commands/`.

```python
import typer

from frugalbot.ui.commands.base import command
from frugalbot.ui.tui import Tui


@command("hello")
def cmd_hello(ctx: typer.Context) -> None:
    """Say hello to the LLM"""
    app: Tui = ctx.obj["app"]
    app.input.load_text("Hello LLM!")
    app.run_worker(app.action_submit())
```

For more examples, see [commands](src/frugalbot/ui/commands/).

### MCP (Model Context Protocol) Support

frugalbot supports MCP servers, allowing you to use tools from any MCP-compatible server. At this time only stdio transport is supported.

You can use [mcp-remote](https://github.com/geelen/mcp-remote) to convert any http server into a stdio server.

Configure MCP servers in `config.toml`:

```toml
[mcp.servername]
command = ["npx", "-y", "@modelcontextprotocol/server-name", "arg1", "arg2"]
enabled = true
env = { KEY = "value", KEYTWO = "valuetwo" }  # Optional environment variables
cwd = "/path/to/working/dir"  # Optional working directory for mcp server
connection_timeout = 60.0  # Connection / start-up timeout in seconds (default: 60.0)
execution_timeout = 300.0  # Tool execution timeout in seconds (default: 300.0)
enabled_tools = ["tool1", "tool2"]  # Optional: only enable specific tools
```

MCP tools are automatically discovered and registered with the format `servername.toolname`. They support the same approval workflows as built-in tools.

Example MCP server configuration:

```toml
# Serena code intelligence server
[mcp.serena]
command = ["uvx", "--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server"]

# Filesystem server
[mcp.filesystem]
command = ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/files"]
```

### Skills

Skills are supported. They must be in one of the following locations:
- `.frugalbot/skills/` (project-local)
- `.agents/skills/` (project-local alternative)
- `.claude/skills/` (project-local alternative)
- `~/.frugalbot/skills/` (global)

## Development

### Setting Up Development Environment

```bash
# Install with dev dependencies
uv sync --group dev

# Run tests
uv run pytest

# Type checking
uv run pyright

# Linting and formatting
uv run ruff check --fix
uv run ruff format
```

### Project Standards

This project follows modern Python practices:

- **Python 3.14+** syntax and typing features
- **`uv`** for package management (replaces pip/poetry/virtualenv)
- **Ruff** for linting and formatting
- **Pyright** for static type checking
- **Pytest** for testing with `pytest-asyncio` for async tests
- **`src` layout** for proper package structure

See [AGENTS.md](AGENTS.md) for architectural standards and coding guidelines.
