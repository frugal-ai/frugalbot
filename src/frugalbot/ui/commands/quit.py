import typer

from frugalbot.ui.commands.base import command
from frugalbot.ui.tui import Tui


def quit(app: Tui, msg: str | None = None) -> None:
    if app.autocomplete_path_worker:
        app.autocomplete_path_worker.cancel()
    app.autocomplete_path_query_event.set()
    app.exit(msg)


@command("quit")
def cmd_quit(ctx: typer.Context):
    """Exit the application."""
    quit(ctx.obj["app"])
