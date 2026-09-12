from unittest.mock import MagicMock

import typer

from frugalbot.ui.commands.learn import _build_learn_prompt, cmd_learn
from frugalbot.ui.tui import Tui


def test_build_learn_prompt_with_defaults_includes_auto_target():
    # Given
    focus = None
    target = "auto"

    # When
    prompt = _build_learn_prompt(focus, target)

    # Then
    assert "Autonomously choose the best mechanism" in prompt


def test_build_learn_prompt_with_focus_and_target_includes_custom_directives():
    # Given
    focus = "pytest flags"
    target = "memory"

    # When
    prompt = _build_learn_prompt(focus, target)

    # Then
    assert "Pay special attention to this area: 'pytest flags'" in prompt
    assert "persist learnings specifically as a **memory**" in prompt


def test_cmd_learn_when_agent_is_running_notifies_and_does_not_launch():
    # Given
    mock_app = MagicMock(spec=Tui)
    mock_app._is_agent_running.return_value = True
    ctx = MagicMock(spec=typer.Context)
    ctx.obj = {"app": mock_app}

    # When
    cmd_learn(ctx)

    # Then
    mock_app.notify.assert_called_once_with("Cannot learn while agent is running. Wait for it to finish or press Ctrl+A to cancel.")


def test_cmd_learn_when_agent_is_idle_launches_agent_with_prompt():
    # Given
    mock_app = MagicMock(spec=Tui)
    mock_app._is_agent_running.return_value = False
    ctx = MagicMock(spec=typer.Context)
    ctx.obj = {"app": mock_app}

    # When
    cmd_learn(ctx, focus="linting rules", target="hook")

    # Then
    mock_app.launch_agent.assert_called_once()
    launched_prompt = mock_app.launch_agent.call_args[0][0]
    assert "linting rules" in launched_prompt
    assert "hook" in launched_prompt
