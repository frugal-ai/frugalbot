from typing import Annotated

import typer

from frugalbot.config import ThinkingLevel
from frugalbot.ui.commands.base import command
from frugalbot.ui.tui import Tui


async def _cmd_thinking_impl(app: Tui, level: ThinkingLevel) -> None:
    for agent in app.agents.get_all():
        await agent.set_thinking_level(level, emit_status_update=True if agent.name == app.agent.name else False)
    app.notify(f"Thinking level set to {level}")


@command("thinking")
def cmd_thinking(ctx: typer.Context, level: Annotated[ThinkingLevel, typer.Argument(help="The thinking level to set.")]):
    """Change the thinking level of the LLM."""
    app: Tui = ctx.obj["app"]
    app.run_worker(_cmd_thinking_impl(app, level))
