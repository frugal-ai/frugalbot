import typer

from frugalbot.ui.commands.base import command
from frugalbot.ui.tui import Tui


@command("new")
def cmd_new(ctx: typer.Context):
    """Start a new conversation."""
    app: Tui = ctx.obj["app"]
    app.output.remove_children()
    app.run_worker(app.agent.new_conversation(), name="new_conversation")
