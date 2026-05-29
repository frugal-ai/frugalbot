import os
from pathlib import Path
from typing import Annotated

import typer

from frugalbot.ui.commands.base import command
from frugalbot.ui.tui import Tui


@command("cwd")
def cmd_cwd(ctx: typer.Context, path: Annotated[Path, typer.Argument(exists=True, file_okay=False, dir_okay=True, writable=False, readable=True, resolve_path=True, help="The new working directory")]):
    """Changes the current working directory."""
    app: Tui = ctx.obj["app"]
    if path.is_relative_to(Path.cwd()):
        path = path.relative_to(Path.cwd())
    else:
        path = path.absolute()
    os.chdir(path)
    app.notify(f"New cwd is {path}")
