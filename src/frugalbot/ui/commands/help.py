from typing import cast

import typer
from textual.binding import Binding

from frugalbot.ui.commands.base import command
from frugalbot.ui.screens.help import HelpScreen
from frugalbot.ui.tui import Tui

_HELP_CONTENT = """# Help

## Navigation & Interaction
- Type `/` to open the command autocomplete menu.
- Type `@` to reference and search for local files.
- Use `Ctrl+R` to search through your message history.
- Use `Ctrl+A` to cancel the current agent operation.

## Keyboard Shortcuts
| Shortcut | Description |
|---|---|
"""


@command("help")
def cmd_help(ctx: typer.Context):
    """Display the help screen."""
    app: Tui = ctx.obj["app"]

    content = _HELP_CONTENT
    for binding in Tui.BINDINGS:
        if isinstance(binding, tuple):
            keys_str = cast(str, binding[0])
            description = binding[2] if len(binding) > 2 else ""
        elif isinstance(binding, Binding):
            keys_str = binding.key
            description = binding.description
        else:
            raise TypeError(f"Unsupported binding type {type(binding)}")
        shortcut = keys_str.replace(",", " or ")
        content += f"| `{shortcut}` | {description} |\n"
    app.call_after_refresh(app.push_screen, HelpScreen(content))
