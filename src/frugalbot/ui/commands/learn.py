from typing import Annotated, Literal

import typer
from jinja2 import Template

from frugalbot.ui.commands.base import command
from frugalbot.ui.tui import Tui

LearnTarget = Literal["auto", "memory", "skill", "command", "hook"]


def _build_learn_prompt(template: str, focus: str | None, target: LearnTarget) -> str:
    return Template(template).render(focus=focus, target=target)


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

    prompt_template = app.agent.config.prompts.learn_prompt
    if not prompt_template:
        app.notify("No learn prompt configured. Add 'learn_prompt' to the [prompts] section of your config.toml.")
        return

    prompt = _build_learn_prompt(prompt_template, focus, target)
    app.launch_agent(prompt)
