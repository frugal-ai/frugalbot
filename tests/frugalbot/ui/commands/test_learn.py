from unittest.mock import Mock

import pytest
import typer
from pytest_mock import MockerFixture

from frugalbot.ui.commands.learn import _USER_PROMPT, cmd_load


@pytest.fixture
def mock_app() -> Mock:
    """Creates a mock Tui app with input configured."""
    app = Mock()
    app.input = Mock()
    return app


@pytest.fixture
def mock_ctx(mock_app: Mock, mocker: MockerFixture) -> Mock:
    """Creates a mock typer.Context with app set in obj."""
    ctx = mocker.MagicMock(spec=typer.Context)
    ctx.obj = {"app": mock_app}
    return ctx


# --- Tests for app.input.load_text exit point (third-party interaction) ---


def test_cmd_learn_with_valid_context_loads_prompt_text_into_input(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given

    # When
    cmd_load(mock_ctx)

    # Then
    mock_app.input.load_text.assert_called_once_with(_USER_PROMPT)


def test_cmd_learn_with_valid_context_prompt_contains_improvement_instructions(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given

    # When
    cmd_load(mock_ctx)

    # Then
    call_args = mock_app.input.load_text.call_args
    loaded_text: str = call_args[0][0]
    assert "improvements" in loaded_text


def test_cmd_learn_with_valid_context_prompt_contains_conversation_reference(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given

    # When
    cmd_load(mock_ctx)

    # Then
    call_args = mock_app.input.load_text.call_args
    loaded_text: str = call_args[0][0]
    assert "conversation" in loaded_text


def test_cmd_learn_with_valid_context_prompt_contains_no_improvements_fallback(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given

    # When
    cmd_load(mock_ctx)

    # Then
    call_args = mock_app.input.load_text.call_args
    loaded_text: str = call_args[0][0]
    assert "No improvements needed." in loaded_text


def test_cmd_learn_with_valid_context_prompt_instructs_general_terms(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given

    # When
    cmd_load(mock_ctx)

    # Then
    call_args = mock_app.input.load_text.call_args
    loaded_text: str = call_args[0][0]
    assert "general terms" in loaded_text


def test_cmd_learn_with_valid_context_prompt_instructs_concise_direct(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given

    # When
    cmd_load(mock_ctx)

    # Then
    call_args = mock_app.input.load_text.call_args
    loaded_text: str = call_args[0][0]
    assert "concise and direct" in loaded_text


def test_cmd_learn_with_valid_context_prompt_requests_mistakes_analysis(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given

    # When
    cmd_load(mock_ctx)

    # Then
    call_args = mock_app.input.load_text.call_args
    loaded_text: str = call_args[0][0]
    assert "mistakes" in loaded_text


# --- Tests for app.run_worker exit point (third-party interaction) ---


def test_cmd_learn_with_valid_context_calls_run_worker_once(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given

    # When
    cmd_load(mock_ctx)

    # Then
    mock_app.run_worker.assert_called_once()


def test_cmd_learn_with_valid_context_run_worker_receives_action_submit_result(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given

    # When
    cmd_load(mock_ctx)

    # Then
    mock_app.action_submit.assert_called_once()
    call_args = mock_app.run_worker.call_args
    assert call_args[0][0] == mock_app.action_submit.return_value


def test_cmd_learn_with_valid_context_load_text_called_before_run_worker(
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given

    # When
    cmd_load(mock_ctx)

    # Then
    method_names = [call[0] for call in mock_app.method_calls]
    load_text_index = next(i for i, name in enumerate(method_names) if name == "input.load_text")
    run_worker_index = next(i for i, name in enumerate(method_names) if name == "run_worker")
    assert load_text_index < run_worker_index
