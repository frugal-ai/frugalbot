import typer
import typer._click


def get_command_from_name(typer_instance: typer.Typer, name: str) -> typer._click.Command | None:
    name = name.removeprefix("/")
    for command_info in typer_instance.registered_commands:
        if command_info.name != name:
            continue
        return typer.main.get_command_from_info(command_info, pretty_exceptions_short=True, rich_markup_mode=None)
    return None
