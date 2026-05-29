import typer
from textual.worker import WorkerState

from frugalbot.ui.commands.base import command
from frugalbot.ui.tui import Tui


@command("resume")
def cmd_resume(ctx: typer.Context):
    """Resume the conversation by sending the current conversation as-is to the LLM without appending a new message."""
    app: Tui = ctx.obj["app"]
    if app.agent_worker and app.agent_worker.state in (WorkerState.RUNNING, WorkerState.PENDING):
        app.notify("Cannot resume while agent is running. Wait for it to finish or ctrl+a to stop agent.")
        return
    app.launch_agent(None)
