# frugalbot

Yet another coding harness agent.

Goals of the project:
- Minimize the context size
- Minimize costs (by reducing context size AND the number of LLM API calls)
- Maximize operating efficiency (having the right tools to do the job)
- Provide general agent functionality beyond coding (e.g. knowledge-base management)
- Maximize transparency of what is sent to the LLM
- Maximize customizability and extensibility

## Features

- **Multi-LLM Support**: Works with Google Gemini (natively), any provider supported by [any-llm-sdk](https://docs.mozilla.ai/providers) (OpenRouter, Anthropic, OpenAI, etc.), the official GitHub Copilot runtime, and manual human-in-the-loop mode.
- **Multi-Agent System**: Run specialized agents (e.g., `coder`, `wiki_master`), cycle between them dynamically, and customize toolsets, prompts, hooks, and client fallbacks per agent.
- **Cross-Platform Shell Execution**: Built-in `powershell` (Windows) and `bash` (Linux/macOS) execution with AST-level safety evaluation via Tree-sitter and PowerShell AST.
- **Rich Tool Ecosystem**: File operations (`read`, `write`, `edit` with optional hashline support, `listfiles`), searching (`grep`), code execution (`bash`, `powershell`), and external MCP integration.
- **Textual TUI**: Modern, responsive terminal UI with live Markdown streaming, elapsed runtime spinners, and real-time token/cost telemetry via models.dev and OpenRouter.
- **Interactive Completions & History**: Instant `@path` fuzzy file mention/attachment, `/` slash command autocompletion, and `Ctrl+R` prompt history search.
- **Session Management**: Automatically persist sessions to `~/.frugalbot/sessions/` and restore them via `/load` or CLI flags.
- **Fine-Grained Safety & Approvals**: Pre-approve trusted command patterns, inspect shell commands AST-by-AST, or prompt for interactive human approval.
- **Skills Support**: Drop modular `SKILL.md` instructions into `.frugalbot/skills/`, `.agents/skills/`, `.claude/skills/`, or global directories to inject domain workflows on demand.
- **Extensible Architecture**: Add custom tools, hooks, and slash commands locally or globally.

## Platform Support

- **Windows**: Supported natively using PowerShell.
- **Linux**: Supported natively using Bash (tested in CI on Ubuntu).
- **macOS**: Supported using POSIX/Bash tooling.

## Getting Started

### Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer) package manager

### Installation

Install globally via `uv`:

```bash
uv tool install git+https://github.com/frugal-ai/frugalbot.git
```

Or run directly without installing:

```bash
uvx --from git+https://github.com/frugal-ai/frugalbot.git frugalbot
```

### Initial Configuration

Run frugalbot once to generate default configuration files:

```bash
uv tool run frugalbot
```

On first run, default files will be created in `~/.frugalbot/`:
- `~/.frugalbot/config.toml`: Application configuration, agent definitions, model chains, and tool/hook policies.
- `~/.frugalbot/.env`: API keys (e.g. `GEMINI_API_KEY`, `OPENROUTER_API_KEY`).

Edit these files with your API keys and preferred models before continuing.

### Running the Agent

Start the interactive TUI:

```bash
uv tool run frugalbot
```

#### Command-Line Options

```bash
# Run in one-shot mode (executes prompt, outputs response, and exits)
uv tool run frugalbot --one-shot --prompt "Analyze src/frugalbot/agent.py and summarize its main loop"

# Start with an initial prompt in interactive mode
uv tool run frugalbot --prompt "Fix failing unit tests"

# Resume an existing session file
uv tool run frugalbot --session-file ~/.frugalbot/sessions/2026-09-12_10-00-00.json

# Run against a specific directory
uv tool run frugalbot --start-directory /path/to/project

# Use a custom configuration file
uv tool run frugalbot --config-file ./custom_config.toml
```

## Interactive TUI Controls

### Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Alt+Enter` | Submit message or slash command |
| `Ctrl+A` | Cancel the running agent operation |
| `Ctrl+N` | Cycle between configured agents (e.g. `coder` ↔ `wiki_master`) |
| `Alt+P` / `Ctrl+P` | Cycle between configured LLM providers / fallback models |
| `Ctrl+R` | Search prompt history |
| `Alt+S` | Toggle auto-scrolling on output |
| `Alt+U` / `Alt+Up` | Scroll output page up |
| `Alt+D` / `Alt+Down` | Scroll output page down |
| `Alt+H` / `Alt+Home` | Scroll output to top |
| `Alt+E` / `Alt+End` | Scroll output to bottom |

### Mentions and Slash Commands

- **File Mentions (`@path`)**: Type `@` to open the fuzzy file picker. Mentioned files are automatically read and attached to the user prompt context.
- **Slash Commands (`/`)**: Type `/` to access built-in commands:
  - `/help`: Show keyboard bindings and navigation modal.
  - `/new`: Start a fresh conversation session.
  - `/load <path>`: Load a saved JSON session file.
  - `/resume`: Resend the conversation state as-is to the LLM.
  - `/cwd <path>`: Change working directory.
  - `/copy`: Copy full conversation formatted for web chat interfaces to clipboard.
  - `/thinking <NONE|LOW|MEDIUM|HIGH>`: Set reasoning level on the fly.
  - `/learn`: Prompt the model to critique previous steps and produce concise guidelines.
  - `/skill:<name>`: Run a discovered skill.
  - `/reload`: Hot-reload configuration, tools, hooks, and commands.
  - `/quit`: Exit frugalbot.

## Multi-Agent Configuration

Configure agents in `config.toml`. Global settings under `[tools]`, `[hooks]`, `[mcp]`, and `[prompts]` provide defaults that can be customized per agent:

```toml
[general]
agents = ["coder", "wiki_master"]
tool_output_format = "yaml"  # "yaml" (token-efficient) or "json"
thinking_level = "HIGH"

# Global client definitions
[clients.google]
type = "google"
model = "gemma-4-31b-it"
api_key_env_var = "GEMINI_API_KEY"

[clients.deepseek_flash]
type = "anyllm"
provider = "openrouter"
model = "deepseek/deepseek-v4-flash"
api_key_env_var = "OPENROUTER_API_KEY"

# Agent-specific overrides
[agents.coder]
clients = ["google", "deepseek_flash"]
skills = ["find-docs"]

[agents.coder.prompts]
system_prompt = """
You are an expert coding assistant operating inside frugalbot.
{{tools}}
{{tool_guidelines}}
{{skills}}
{{agents_md}}
"""

[agents.wiki_master.prompts]
system_prompt = """
You are an expert knowledge curator following the LLM Wiki pattern.
{{tools}}
{{tool_guidelines}}
"""
```

## GitHub Copilot Client

frugalbot can use the official [GitHub Copilot SDK](https://github.com/github/copilot-sdk) as an LLM
transport (`type = "copilot"`). It drives the Copilot *runtime* purely as a model backend: frugalbot
keeps ownership of the agent loop, conversation, tools, hooks, approvals and session persistence.
Copilot's built-in tools are disabled; frugalbot's own tools are exposed to the model and executed
locally.

### Prerequisites

1. Install the Copilot runtime (frugalbot never auto-downloads it):

   ```bash
   python -m copilot download-runtime
   ```

   Alternatively, point `clients.copilot.cli_path` (or the `COPILOT_CLI_PATH` environment variable)
   at a pre-installed runtime, or put `copilot-runtime`/`copilot` on your `PATH`.
2. Provide a GitHub token or PAT in the environment variable named by `api_key_env_var`
   (populated in `~/.frugalbot/.env`).
3. Use a model that Copilot offers, or `"auto"`.

If the runtime cannot be found at start-up, frugalbot prints install instructions and exits.

### Configuration

```toml
[clients.copilot]
type = "copilot"
model = "gpt-5"                              # or "auto"
api_key_env_var = "COPILOT_GITHUB_TOKEN"     # env var holding a GitHub token/PAT
# output_traceback_on_error = false
# cli_path = "C:\\path\\to\\copilot-runtime"   # pre-installed runtime; else COPILOT_CLI_PATH
# base_directory = "~/.frugalbot/copilot"      # SDK state; required by mode="empty"
# auto_tier = "balance"                        # only used with model = "auto"
# reasoning_effort = "high"                    # explicit override of the thinking-level map
```

### Thinking levels

| `thinking_level` | Copilot `reasoning_effort` |
| --- | --- |
| `NONE` | omitted |
| `LOW` | `low` |
| `MEDIUM` | `high` |
| `HIGH` | `max` |

Unsupported levels are clamped to the nearest supported level with a warning. `model = "auto"`
skips reasoning-effort selection and may use `auto_tier = "efficiency" | "balance" | "intelligence" | "fast"`.

### Limitations

- Copilot's own built-in tools, MCP servers, sub-agents, skills and infinite-session compaction are
  not used; frugalbot owns context and tools.
- Because the SDK session is stateful and cannot ingest an arbitrary message array, pre-existing
  history (from `/load` or switching to Copilot mid-conversation) is restored by injecting a
  rendered transcript into the system prompt at session creation.
- BYOK custom providers, Azure, and in-process FFI transport are not supported in this client.

## Extending frugalbot

### Custom Tools

Create custom tools in `.frugalbot/tools/` (project-local) or `~/.frugalbot/tools/` (global). Each tool must:

1. Subclass `ToolBase[ResultModel, ConfigModel]`, where `ResultModel` inherits from `pydantic.BaseModel`.
2. Take its configuration model as the second parameter of `__init__`.
3. Implement `async def run(...)` with `Annotated` parameter descriptions for schema generation.

```python
from typing import Annotated
import pydantic
from frugalbot.tools.base import ToolBase, ToolConfig


class MyToolConfig(ToolConfig):
    api_key: str = ""


class MyToolResult(pydantic.BaseModel):
    result: str


class MyCustomTool(ToolBase[MyToolResult, MyToolConfig]):
    """Description of what your tool does."""

    def __init__(self, config: MyToolConfig):
        super().__init__(config)

    async def run(
        self,
        param1: Annotated[str, "Description of param1"],
        param2: Annotated[int, "Description of param2"] = 10,
    ) -> MyToolResult:
        return MyToolResult(result=f"Result: {param1} with {param2}")
```

Enable your tool in `config.toml`:

```toml
[tools.mycustomtool]
enabled = true
api_key = "your-api-key"
```

### Custom Hooks

Hooks intercept lifecycle events to sanitize messages and prompts, approve or deny tool calls, inspect tool results, or control whether the agent continues. Place custom hook modules (`*.py`) in `.frugalbot/hooks/` or `~/.frugalbot/hooks/`.

Supported hook types and their mutable data:
- `PreRenderSystemPromptHook`: Modify the system-prompt template or its arguments before rendering.
- `PreRenderUserPromptHook`: Modify the user-prompt template or its arguments before rendering.
- `PreSystemMessageHook`: Modify the rendered system message before it is added to the conversation.
- `PreUserMessageHook`: Modify a user message before it is added to the conversation.
- `PreToolCallHook`: Inspect or modify the tool name and arguments, and set the approval state. Tool calls are denied unless a hook sets `state` to `ApprovalState.APPROVED`; `NOT_SET` fails closed.
- `PostToolCallHook`: Inspect or modify the tool name and JSON result after successful execution, before the result is added to the conversation.
- `AgentStopHook`: Runs when the LLM responds without tool calls. Set `continue_conversation = True` to continue the conversation.
- `AgentFinishedHook`: Runs when an agent run finishes. Set `run_again = True` to run the agent loop again.

Implement a hook by subclassing `HookBase[HookEvent, HookConfig]` (or a `HookConfig` subclass). The class name determines its config key: the loader lowercases the class name and removes the `Hook` suffix, so `MyCustomHook` is configured as `mycustom`. Hooks run in ascending priority order (`HIGHEST` through `LOWEST`); the default is `HIGH`. Hooks are not short-circuited, so later hooks may further modify hook data; approval hooks should respect a state already set by an earlier hook.

```python
from frugalbot.hooks.base import (
    ApprovalState,
    HookBase,
    HookConfig,
    HookPriority,
    PreToolCallHook,
)


class MyHookConfig(HookConfig):
    blocked_tool: str = "bash"


class MyCustomHook(HookBase[PreToolCallHook, MyHookConfig]):
    """Block execution of specific tools."""

    def __init__(self, config: MyHookConfig):
        super().__init__(config)

    @property
    def priority(self) -> HookPriority:
        return HookPriority.MEDIUM

    async def run(self, hook_data: PreToolCallHook) -> None:
        if not self.config.enabled:
            return

        if hook_data.tool_name == self.config.blocked_tool:
            hook_data.state = ApprovalState.DENIED
            hook_data.denied_reason = f"Execution of tool '{self.config.blocked_tool}' is blocked by policy."
```

Configure hooks in `config.toml`:

```toml
[hooks.mycustomhook]
enabled = true
blocked_tool = "bash"
```

### Custom Commands

Add custom interactive slash commands by placing modules in `.frugalbot/commands/` or `~/.frugalbot/commands/`:

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

### MCP (Model Context Protocol) Support

frugalbot connects to stdio-based MCP servers and exposes discovered tools under `<server_name>.<tool_name>`.

Configure servers in `config.toml`:

```toml
[mcp.filesystem]
command = ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/files"]
enabled = true
connection_timeout = 60.0
execution_timeout = 300.0
enabled_tools = ["read_file", "list_directory"]  # Optional allowlist; defaults to all
```

### Skills

Skills provide reusable prompts and domain workflows. Create a `SKILL.md` file with frontmatter in any of:
- `.frugalbot/skills/<skill-name>/SKILL.md`
- `.agents/skills/<skill-name>/SKILL.md`
- `.claude/skills/<skill-name>/SKILL.md`
- `~/.frugalbot/skills/<skill-name>/SKILL.md`

Example:

```markdown
---
name: unit-test-writer
description: Write comprehensive pytest tests following project guidelines
---

Follow docs/testing_guidelines.md strictly:
- Given-When-Then structure
- In-memory isolation
- 100% test coverage
```

Skills are indexed automatically into `{{skills}}` in system prompts and can be triggered via `/skill:unit-test-writer`.

## Development

### Setting Up Environment

```bash
# Clone repository and sync dependencies
git clone https://github.com/frugal-ai/frugalbot.git
cd frugalbot
uv sync --all-extras --dev
```

### Quality Assurance & Testing

Before submitting changes, run the test and linting pipeline:

```bash
uv run ruff format
uv run ruff check --fix
uv run pyright
uv run pytest -q
```

All test cases must adhere to [docs/testing_guidelines.md](docs/testing_guidelines.md).
