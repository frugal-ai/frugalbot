import typer
from textual.worker import WorkerState

from frugalbot.events import bus
from frugalbot.ui.commands.base import command, unload_commands
from frugalbot.ui.commands.quit import quit
from frugalbot.ui.tui import Tui


async def _cmd_reload_impl(app: Tui):
    try:
        # if the current conversation isn't empty, we'll want to preserve it
        conversation_file_path = None
        if len(app.agent.conversation.messages) > 1:
            conversation_file_path = app.agent.conversation_file_path
        bus.clear_subscribers()
        unload_commands()
        await app.agents.reload()
        app.initialized = False
        app.init(app.agents)
        msg_suffix = ""
        app.output.remove_children()
        if not conversation_file_path:
            await app.agent.new_conversation()
        else:
            await app.agent.load_conversation_from_file(conversation_file_path)
            msg_suffix = " System prompt changes will take effect in the next conversation."
        app.notify(f"Reload successful.{msg_suffix}")
    except Exception as e:
        quit(app, f"Fatal error while trying to reload:\n{e!s}")


@command("reload")
def cmd_reload(ctx: typer.Context):
    """Reload config, hooks, tools, commands, etc."""
    app: Tui = ctx.obj["app"]
    if app.agent_worker and app.agent_worker.state in (WorkerState.RUNNING, WorkerState.PENDING):
        app.notify("Cannot reload while agent is running. Wait for it to finish or ctrl+a to stop agent.")
        return
    app.run_worker(_cmd_reload_impl(app))
