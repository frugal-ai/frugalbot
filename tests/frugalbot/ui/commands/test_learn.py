from unittest.mock import MagicMock

import typer

from frugalbot.ui.commands.learn import _build_learn_prompt, cmd_learn
from frugalbot.ui.tui import Tui

LEARN_PROMPT_TEMPLATE = "Focus: {{ focus }}\nTarget: {{ target }}"


def test_build_learn_prompt_with_defaults_renders_template_with_auto_target() -> None:
    # Given
    focus = None
    target = "auto"

    # When
    prompt = _build_learn_prompt(LEARN_PROMPT_TEMPLATE, focus, target)

    # Then
    assert prompt == "Focus: None\nTarget: auto"


def test_build_learn_prompt_with_focus_and_target_renders_them_into_template() -> None:
    # Given
    focus = "pytest flags"
    target = "memory"

    # When
    prompt = _build_learn_prompt(LEARN_PROMPT_TEMPLATE, focus, target)

    # Then
    assert prompt == "Focus: pytest flags\nTarget: memory"


def test_cmd_learn_when_agent_is_running_notifies_and_does_not_launch() -> None:
    # Given
    mock_app = MagicMock(spec=Tui)
    mock_app._is_agent_running.return_value = True
    ctx = MagicMock(spec=typer.Context)
    ctx.obj = {"app": mock_app}

    # When
    cmd_learn(ctx)

    # Then
    mock_app.notify.assert_called_once_with("Cannot learn while agent is running. Wait for it to finish or press Ctrl+A to cancel.")


def test_cmd_learn_when_no_learn_prompt_configured_notifies_and_does_not_launch() -> None:
    # Given
    mock_app = MagicMock(spec=Tui)
    mock_app._is_agent_running.return_value = False
    mock_app.agent = MagicMock()
    mock_app.agent.config.prompts.learn_prompt = ""
    ctx = MagicMock(spec=typer.Context)
    ctx.obj = {"app": mock_app}

    # When
    cmd_learn(ctx)

    # Then
    mock_app.notify.assert_called_once_with("No learn prompt configured. Add 'learn_prompt' to the [prompts] section of your config.toml.")


def test_cmd_learn_when_agent_is_idle_launches_agent_with_rendered_config_prompt() -> None:
    # Given
    mock_app = MagicMock(spec=Tui)
    mock_app._is_agent_running.return_value = False
    mock_app.agent = MagicMock()
    mock_app.agent.config.prompts.learn_prompt = LEARN_PROMPT_TEMPLATE
    ctx = MagicMock(spec=typer.Context)
    ctx.obj = {"app": mock_app}

    # When
    cmd_learn(ctx, focus="linting rules", target="hook")

    # Then
    mock_app.launch_agent.assert_called_once_with("Focus: linting rules\nTarget: hook")
