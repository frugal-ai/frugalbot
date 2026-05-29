import pyperclip
import typer

from frugalbot.ui.commands.base import command
from frugalbot.ui.tui import Tui


@command("copy")
def cmd_copy(ctx: typer.Context):
    """Copy the current conversation to the clipboard."""
    app: Tui = ctx.obj["app"]
    text = app.agent.conversation.convert_into_web_chat_prompt()
    pyperclip.copy(text)
    app.notify("Conversation copied to clipboard!")
