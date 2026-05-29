from unittest.mock import Mock

import pytest

from frugalbot.skills import Skill, Skills
from frugalbot.ui.commands.skill import _create_skill_command


@pytest.fixture
def mock_skills() -> Mock:
    """Creates a mock Skills object with a single skill."""
    skill = Skill(name="test-skill", description="A test skill", location="path/to/skill", content="Skill content here")
    skills = Mock(spec=Skills)
    skills.get.return_value = skill
    return skills


@pytest.fixture
def mock_tui(mocker, mock_skills: Mock) -> Mock:
    """Creates a mock tui and patches it into the skill command module."""
    mock_input = Mock()
    mock_agent = Mock()
    mock_agent.skills = mock_skills

    mock_tui_instance = Mock()
    mock_tui_instance.input = mock_input
    mock_tui_instance.agent = mock_agent
    mock_tui_instance.run_worker = Mock()
    mock_tui_instance.action_submit = Mock(return_value="submit_coro")

    mocker.patch("frugalbot.ui.commands.skill.tui", mock_tui_instance)

    return mock_tui_instance


# --- Tests for input.load_text exit point (third-party interaction) ---


def test_create_skill_command_with_args_loads_content_and_args_into_input(
    mock_tui: Mock,
) -> None:
    # Given
    skill_command = _create_skill_command("test-skill")
    args = ["arg1", "arg2"]

    # When
    skill_command(args)

    # Then
    mock_tui.input.load_text.assert_called_once_with("Skill content here\n\narg1 arg2")


def test_create_skill_command_with_none_args_loads_content_only_into_input(
    mock_tui: Mock,
) -> None:
    # Given
    skill_command = _create_skill_command("test-skill")

    # When
    skill_command(None)

    # Then
    mock_tui.input.load_text.assert_called_once_with("Skill content here\n\n")


def test_create_skill_command_with_empty_args_list_loads_content_only_into_input(
    mock_tui: Mock,
) -> None:
    # Given
    skill_command = _create_skill_command("test-skill")

    # When
    skill_command([])

    # Then
    mock_tui.input.load_text.assert_called_once_with("Skill content here\n\n")


def test_create_skill_command_with_single_arg_loads_content_and_arg_into_input(
    mock_tui: Mock,
) -> None:
    # Given
    skill_command = _create_skill_command("test-skill")
    args = ["single-arg"]

    # When
    skill_command(args)

    # Then
    mock_tui.input.load_text.assert_called_once_with("Skill content here\n\nsingle-arg")


def test_create_skill_command_uses_correct_skill_name_to_lookup(
    mock_tui: Mock,
) -> None:
    # Given
    skill_command = _create_skill_command("test-skill")

    # When
    skill_command(None)

    # Then
    mock_tui.agent.skills.get.assert_called_once_with("test-skill")


# --- Tests for run_worker exit point (third-party interaction) ---


def test_create_skill_command_calls_run_worker_once(
    mock_tui: Mock,
) -> None:
    # Given
    skill_command = _create_skill_command("test-skill")

    # When
    skill_command(None)

    # Then
    mock_tui.run_worker.assert_called_once()


def test_create_skill_command_passes_action_submit_result_to_run_worker(
    mock_tui: Mock,
) -> None:
    # Given
    skill_command = _create_skill_command("test-skill")

    # When
    skill_command(None)

    # Then
    call_args = mock_tui.run_worker.call_args
    assert call_args[0][0] == "submit_coro"


def test_create_skill_command_calls_action_submit(
    mock_tui: Mock,
) -> None:
    # Given
    skill_command = _create_skill_command("test-skill")

    # When
    skill_command(None)

    # Then
    mock_tui.action_submit.assert_called_once()
