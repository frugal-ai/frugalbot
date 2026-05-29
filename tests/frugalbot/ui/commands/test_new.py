from unittest.mock import MagicMock

import typer

from frugalbot.ui.commands.new import cmd_new


def test_cmd_new_with_context_removes_children():
    # Given
    mock_app = MagicMock()
    ctx = MagicMock(spec=typer.Context)
    ctx.obj = {"app": mock_app}

    # When
    cmd_new(ctx)

    # Then
    mock_app.output.remove_children.assert_called_once()


def test_cmd_new_with_context_runs_worker():
    # Given
    mock_app = MagicMock()
    mock_conv = MagicMock()
    mock_app.agent.new_conversation.return_value = mock_conv
    ctx = MagicMock(spec=typer.Context)
    ctx.obj = {"app": mock_app}

    # When
    cmd_new(ctx)

    # Then
    mock_app.run_worker.assert_called_once_with(mock_conv, name="new_conversation")
