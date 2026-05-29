from collections.abc import Callable

import typer.models

tui_typer = typer.Typer(add_completion=False, no_args_is_help=True, help="Internal Commands", pretty_exceptions_enable=False, rich_markup_mode=None)


def unload_commands():
    tui_typer.registered_callback = None
    tui_typer.registered_commands.clear()
    tui_typer.registered_groups.clear()


def command(name_no_slash: str, **kwargs) -> Callable[[typer.models.CommandFunctionType], typer.models.CommandFunctionType]:
    return tui_typer.command(name_no_slash, add_help_option=False, **kwargs)
