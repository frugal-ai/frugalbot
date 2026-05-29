import asyncio
import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

import frugalbot.config
from frugalbot.agents import Agents
from frugalbot.ui.tui import tui

app = typer.Typer(rich_markup_mode="rich", pretty_exceptions_show_locals=False, add_completion=False)
console = Console(markup=True)


async def _app_init(config_file: Path | None, session_file: Path | None, one_shot: bool, prompt: str | None):
    with console.status("[bold green]Starting...") as status:
        agents = Agents()
        await agents.load(config_file or frugalbot.config.CONFIG_FILE_PATH, status=status)
        tui.init(agents, session_file, one_shot, prompt)


@app.command()
def main(
    one_shot: Annotated[bool, typer.Option(help="Enable one-shot mode. Submits the prompt and exits once the LLM has finished. Must specify a --prompt parameter.")] = False,
    prompt: Annotated[str | None, typer.Option(help="Prompt to submit in one-shot mode or prompt to submit on start.")] = None,
    config_file: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            file_okay=True,
            dir_okay=False,
            writable=False,
            readable=True,
            resolve_path=True,
            help=f"Path to config file. If omitted, uses {frugalbot.config.CONFIG_FILE_PATH}, which will be created if it doesn't exist.",
        ),
    ] = None,
    start_directory: Annotated[
        Path | None, typer.Option(exists=True, file_okay=False, dir_okay=True, writable=False, readable=True, resolve_path=True, help="Directory to run in. If omitted, stays in the current working directory.")
    ] = None,
    session_file: Annotated[
        Path | None, typer.Option(exists=True, file_okay=True, dir_okay=False, writable=False, readable=True, resolve_path=True, help="Path of JSON session file to load on startup.")
    ] = None,
):
    if one_shot and not prompt:
        console.print("[red]Error: You must provide a [bold]--prompt[/bold] when using [bold]--one-shot[/bold].[/red]")
        raise typer.Exit(code=1)
    if not config_file and not frugalbot.config.CONFIG_FILE_PATH.exists():
        frugalbot.config.write_default()
        console.print(
            f"Config file created at [yellow]{frugalbot.config.CONFIG_FILE_PATH}[/].\n\nEnv file created at [yellow]{frugalbot.config.ENV_FILE_PATH}[/]\n\n"
            "Please review, customize as needed and run again to use."
        )
        return
    if start_directory:
        os.chdir(start_directory)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_app_init(config_file, session_file, one_shot, prompt))
    msg = tui.run(loop=loop)
    if msg:
        console.print(msg)
