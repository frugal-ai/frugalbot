import typer

from frugalbot.ui.commands.base import command
from frugalbot.ui.tui import tui

_NONE_ARGUMENT = typer.Argument(None)


def _create_skill_command(name: str):
    def _execute_skill_command(args: list[str] | None = _NONE_ARGUMENT):
        tui.input.load_text(f"{tui.agent.skills.get(name).content}\n\n{' '.join(args) if args else ''}")
        tui.run_worker(tui.action_submit())

    return _execute_skill_command


for skill in tui.agent.skills.skills if hasattr(tui, "agent") else []:
    skill_func = _create_skill_command(skill.name)
    command(f"skill:{skill.name}", help=skill.description)(skill_func)
