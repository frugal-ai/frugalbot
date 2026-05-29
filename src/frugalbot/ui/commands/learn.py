import typer

from frugalbot.ui.commands.base import command
from frugalbot.ui.tui import Tui

_USER_PROMPT = (
    "Based on the entire conversation, find any mistakes or issues in the assistant process and provide a short list of specific "
    "improvements the assistant could make to better accomplish the task. If there are no mistakes or improvements, respond with 'No improvements needed.' "
    "Formulate each improvement in general terms that will apply to all future tasks of the same type. When describing the improvement, be concise and direct, no fluff."
)


@command("learn")
def cmd_load(ctx: typer.Context):
    """Ask LLM to output possible improvements for future conversations"""
    app: Tui = ctx.obj["app"]
    app.input.load_text(_USER_PROMPT)
    app.run_worker(app.action_submit())
