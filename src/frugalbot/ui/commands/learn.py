from typing import Annotated, Literal

import typer

from frugalbot.ui.commands.base import command
from frugalbot.ui.tui import Tui

LearnTarget = Literal["auto", "memory", "skill", "command", "hook"]

_LEARN_PROMPT_TEMPLATE = """\
You are executing frugalbot's active self-improvement routine (`/learn`).
Your task is NOT to write suggestions or advice to the user. You MUST actively take action using your tools (`read`, `write`, `edit`) to persist improvements into the codebase.

## Objective
Analyze the current conversation to identify:
1. Mistakes, incorrect assumptions, or dead-ends made during the session.
2. User corrections, preferences, and feedback.
3. Repetitive manual procedures that could be automated.
4. Project-specific quirks (e.g. test flags, build commands, file structure).

{focus_instruction}
{target_instruction}

## Persistence Mechanisms & Targets
Select the most appropriate mechanism for each distinct learning:

### 1. Source-Controlled Memory (`AGENTS.md`)
- **When to use**: General conventions, testing rules, coding standards, environment gotchas, dos & don'ts.
- **Action**:
  - Use `read` on `AGENTS.md` (or `CLAUDE.md` if it exists).
  - Use `edit` to append or update a clean `## Learned Guidelines & Conventions` section (or update an existing section).
  - Keep additions concise, bulleted, and non-redundant.

### 2. Skill (`.frugalbot/skills/<skill-name>/SKILL.md`)
- **When to use**: Reusable multi-step recipes, playbooks, or complex recurring procedures.
- **Action**: Use `write` to create `.frugalbot/skills/<skill-name>/SKILL.md` using this exact structure:
  ```markdown
  ---
  name: <kebab-case-skill-name>
  description: <Concise 1-sentence description of what this skill does and when to use it>
  ---

  # <Skill Name>

  ## Overview
  ...

  ## Instructions & Steps
  1. ...
  2. ...
  ```

### 3. Custom Slash Command (`.frugalbot/commands/<command_name>.py`)
- **When to use**: Reusable user shortcuts for the TUI chat prompt (invoked via `/<command_name>`).
- **Action**: Use `write` to create `.frugalbot/commands/<command_name>.py` using this exact structure:
  ```python
  import typer
  from frugalbot.ui.commands.base import command
  from frugalbot.ui.tui import Tui

  @command("<command_name>")
  def cmd_<command_name>(ctx: typer.Context) -> None:
      \"\"\"<Help text displayed in autocomplete menu>\"\"\"
      app: Tui = ctx.obj["app"]
      app.input.load_text("<templated message or prompt>")
      app.run_worker(app.action_submit())
  ```

### 4. Custom Hook (`.frugalbot/hooks/<hook_name>.py`)
- **When to use**: Deterministic programmatic guardrails, safety policies, or pre/post-tool call inspections.
- **Action**: Use `write` to create `.frugalbot/hooks/<hook_name>.py` using this exact structure:
  ```python
  from frugalbot.hooks.base import ApprovalState, HookBase, HookConfig, HookPriority, PreToolCallHook

  class <HookName>Config(HookConfig):
      enabled: bool = True

  class <HookName>Hook(HookBase[PreToolCallHook, <HookName>Config]):
      \"\"\"<Description of hook policy>\"\"\"

      @property
      def priority(self) -> HookPriority:
          return HookPriority.MEDIUM

      async def run(self, hook_data: PreToolCallHook) -> None:
          if not self.config.enabled:
              return
          # Implement deterministic check here
  ```

## Execution Instructions
1. First, `read` existing target files before modifying them to avoid duplication.
2. Execute all necessary `write` or `edit` tool calls.
3. If there are genuinely no mistakes, quirks, or reusable workflows in this session, reply with "No improvements needed" without modifying any files.
4. Conclude with a concise summary of the files created or modified, explaining what was learned and advising the user to run `/reload` if new Python commands or hooks were added.
"""


def _build_learn_prompt(focus: str | None, target: LearnTarget) -> str:
    focus_instruction = f"**User Focus**: Pay special attention to this area: '{focus}'." if focus else ""
    target_instruction = (
        f"**Target Restriction**: The user requested that you persist learnings specifically as a **{target}**."
        if target != "auto"
        else "**Target**: Autonomously choose the best mechanism from the list below."
    )
    return _LEARN_PROMPT_TEMPLATE.format(
        focus_instruction=focus_instruction,
        target_instruction=target_instruction,
    )


@command("learn")
def cmd_learn(
    ctx: typer.Context,
    focus: Annotated[
        str | None,
        typer.Argument(
            help="Optional specific topic, friction point, or workflow to focus the learning on.",
        ),
    ] = None,
    target: Annotated[
        LearnTarget,
        typer.Option(
            "--target",
            "-t",
            help="Force target type: 'memory', 'skill', 'command', 'hook', or 'auto' (default).",
        ),
    ] = "auto",
) -> None:
    """Analyze the session and take action to persist improvements as memories, skills, commands, or hooks."""
    app: Tui = ctx.obj["app"]
    if app._is_agent_running():
        app.notify("Cannot learn while agent is running. Wait for it to finish or press Ctrl+A to cancel.")
        return

    prompt = _build_learn_prompt(focus, target)
    app.launch_agent(prompt)
