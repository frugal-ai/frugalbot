from pathlib import Path
from typing import Annotated

import typer

from frugalbot.ui.commands.base import command
from frugalbot.ui.tui import Tui


@command("load")
def cmd_load(ctx: typer.Context, path: Annotated[Path, typer.Argument(exists=True, file_okay=True, dir_okay=False, writable=False, readable=True, resolve_path=True, help="JSON session file path")]):
    """Load a conversation from a file."""
    app: Tui = ctx.obj["app"]
    app.output.remove_children()
    app.run_worker(app.agent.load_conversation_from_file(path), name="load_conversation")
