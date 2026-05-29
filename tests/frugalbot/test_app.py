from pathlib import Path
from typing import NamedTuple
from unittest.mock import ANY, MagicMock

import pytest
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from frugalbot.app import app

runner = CliRunner()


class _AppMocks(NamedTuple):
    """Container for mocked app dependencies used in tests that reach past the config-existence gate."""

    config_path: MagicMock
    env_path: MagicMock
    agents_instance: MagicMock
    agents_class: MagicMock
    tui: MagicMock


@pytest.fixture
def app_mocks(mocker: MockerFixture) -> _AppMocks:
    """Patch common app dependencies so the CLI reaches tui.init / tui.run."""
    mock_config_path = mocker.patch("frugalbot.config.CONFIG_FILE_PATH")
    mock_config_path.exists.return_value = True

    mock_env_path = mocker.patch("frugalbot.config.ENV_FILE_PATH")

    mock_agents_instance = MagicMock()
    mock_agents_instance.load = mocker.AsyncMock()
    mock_agents_class = mocker.patch("frugalbot.app.Agents", return_value=mock_agents_instance)
    mock_tui = mocker.patch("frugalbot.app.tui")

    return _AppMocks(
        config_path=mock_config_path,
        env_path=mock_env_path,
        agents_instance=mock_agents_instance,
        agents_class=mock_agents_class,
        tui=mock_tui,
    )


# -- One-shot mode: missing prompt ---------------------------------------------


def test_main_one_shot_without_prompt_exits_with_error_code() -> None:
    # Given
    # No mocks needed -- exits before calling any dependencies

    # When
    result = runner.invoke(app, ["--one-shot"])

    # Then
    assert result.exit_code == 1


def test_main_one_shot_without_prompt_prints_error_message() -> None:
    # Given
    # No mocks needed -- exits before calling any dependencies

    # When
    result = runner.invoke(app, ["--one-shot"])

    # Then
    assert "Error: You must provide a --prompt when using --one-shot." in result.stdout


def test_main_one_shot_with_empty_prompt_exits_with_error_code() -> None:
    # Given
    # An empty string prompt is falsy and should trigger the same validation

    # When
    result = runner.invoke(app, ["--one-shot", "--prompt", ""])

    # Then
    assert result.exit_code == 1


# -- Default config file missing ------------------------------------------------


def test_main_without_config_file_calls_write_default(app_mocks: _AppMocks, mocker: MockerFixture) -> None:
    # Given
    app_mocks.config_path.exists.return_value = False
    mock_write_default = mocker.patch("frugalbot.config.write_default")

    # When
    runner.invoke(app)

    # Then
    mock_write_default.assert_called_once()


def test_main_without_config_file_prints_config_created_message(app_mocks: _AppMocks, mocker: MockerFixture) -> None:
    # Given
    app_mocks.config_path.exists.return_value = False
    mocker.patch("frugalbot.config.write_default")

    # When
    result = runner.invoke(app)

    # Then
    assert "Config file created at" in result.stdout


def test_main_without_config_file_prints_env_file_created_message(app_mocks: _AppMocks, mocker: MockerFixture) -> None:
    # Given
    app_mocks.config_path.exists.return_value = False
    mocker.patch("frugalbot.config.write_default")

    # When
    result = runner.invoke(app)

    # Then
    assert "Env file created at" in result.stdout


def test_main_without_config_file_does_not_start_tui(app_mocks: _AppMocks, mocker: MockerFixture) -> None:
    # Given
    app_mocks.config_path.exists.return_value = False
    mocker.patch("frugalbot.config.write_default")

    # When
    runner.invoke(app)

    # Then
    app_mocks.tui.run.assert_not_called()


def test_main_without_config_file_does_not_instantiate_agents(app_mocks: _AppMocks, mocker: MockerFixture) -> None:
    # Given
    app_mocks.config_path.exists.return_value = False
    mocker.patch("frugalbot.config.write_default")

    # When
    runner.invoke(app)

    # Then
    app_mocks.agents_class.assert_not_called()


# -- Normal flow with default config --------------------------------------------


def test_main_with_default_config_loads_agents(app_mocks: _AppMocks) -> None:
    # Given
    # app_mocks sets config_path.exists() = True

    # When
    runner.invoke(app)

    # Then
    app_mocks.agents_instance.load.assert_called_once()


def test_main_with_default_config_passes_config_path_to_load(app_mocks: _AppMocks) -> None:
    # Given
    # app_mocks sets config_path.exists() = True

    # When
    runner.invoke(app)

    # Then
    app_mocks.agents_instance.load.assert_called_once_with(app_mocks.config_path, status=ANY)


def test_main_with_default_config_initializes_tui_with_defaults(app_mocks: _AppMocks) -> None:
    # Given
    # app_mocks sets config_path.exists() = True

    # When
    runner.invoke(app)

    # Then
    app_mocks.tui.init.assert_called_once_with(app_mocks.agents_instance, None, False, None)


def test_main_with_default_config_runs_tui(app_mocks: _AppMocks) -> None:
    # Given
    # app_mocks sets config_path.exists() = True

    # When
    runner.invoke(app)

    # Then
    app_mocks.tui.run.assert_called_once()


# -- One-shot with prompt -------------------------------------------------------


def test_main_one_shot_with_prompt_initializes_tui_with_flags(app_mocks: _AppMocks) -> None:
    # Given
    # app_mocks sets config_path.exists() = True

    # When
    runner.invoke(app, ["--one-shot", "--prompt", "Fix the bug"])

    # Then
    app_mocks.tui.init.assert_called_once_with(app_mocks.agents_instance, None, True, "Fix the bug")


def test_main_one_shot_with_prompt_runs_tui(app_mocks: _AppMocks) -> None:
    # Given
    # app_mocks sets config_path.exists() = True

    # When
    runner.invoke(app, ["--one-shot", "--prompt", "Fix the bug"])

    # Then
    app_mocks.tui.run.assert_called_once()


def test_main_one_shot_with_prompt_without_config_creates_default(app_mocks: _AppMocks, mocker: MockerFixture) -> None:
    # Given
    app_mocks.config_path.exists.return_value = False
    mock_write_default = mocker.patch("frugalbot.config.write_default")

    # When
    runner.invoke(app, ["--one-shot", "--prompt", "Hello"])

    # Then
    mock_write_default.assert_called_once()


def test_main_one_shot_with_prompt_without_config_does_not_start_tui(app_mocks: _AppMocks, mocker: MockerFixture) -> None:
    # Given
    app_mocks.config_path.exists.return_value = False
    mocker.patch("frugalbot.config.write_default")

    # When
    runner.invoke(app, ["--one-shot", "--prompt", "Hello"])

    # Then
    app_mocks.tui.run.assert_not_called()


# -- Prompt without one-shot (startup prompt) -----------------------------------


def test_main_with_prompt_without_one_shot_passes_prompt_to_tui(app_mocks: _AppMocks) -> None:
    # Given
    # app_mocks sets config_path.exists() = True

    # When
    runner.invoke(app, ["--prompt", "Review my code"])

    # Then
    app_mocks.tui.init.assert_called_once_with(app_mocks.agents_instance, None, False, "Review my code")


# -- Custom config file ---------------------------------------------------------


def test_main_with_custom_config_file_passes_path_to_load(app_mocks: _AppMocks, fs) -> None:
    # Given
    custom_path = Path("/custom_config.toml")
    fs.create_file(custom_path, contents='[general]\nmode = "coding"')

    # When
    runner.invoke(app, ["--config-file", str(custom_path)])

    # Then
    call_args = app_mocks.agents_instance.load.call_args
    assert call_args is not None
    passed_path = call_args[0][0]
    assert str(passed_path).endswith("custom_config.toml")


def test_main_with_custom_config_file_skips_default_config_creation(app_mocks: _AppMocks, fs, mocker: MockerFixture) -> None:
    # Given
    app_mocks.config_path.exists.return_value = False
    custom_path = Path("/custom_config.toml")
    fs.create_file(custom_path, contents='[general]\nmode = "coding"')
    mock_write_default = mocker.patch("frugalbot.config.write_default")

    # When
    runner.invoke(app, ["--config-file", str(custom_path)])

    # Then
    mock_write_default.assert_not_called()


def test_main_with_custom_config_file_runs_tui(app_mocks: _AppMocks, fs) -> None:
    # Given
    custom_path = Path("/custom_config.toml")
    fs.create_file(custom_path, contents='[general]\nmode = "coding"')

    # When
    runner.invoke(app, ["--config-file", str(custom_path)])

    # Then
    app_mocks.tui.run.assert_called_once()


# -- Start directory ------------------------------------------------------------


def test_main_with_start_directory_changes_working_directory(app_mocks: _AppMocks, fs, mocker: MockerFixture) -> None:
    # Given
    start_dir = Path("/project_dir")
    fs.create_dir(start_dir)
    mock_chdir = mocker.patch("os.chdir")

    # When
    runner.invoke(app, ["--start-directory", str(start_dir)])

    # Then
    assert mock_chdir.call_count == 1
    call_arg = mock_chdir.call_args[0][0]
    assert str(call_arg).endswith("project_dir")


def test_main_with_start_directory_loads_agents_after_chdir(app_mocks: _AppMocks, fs, mocker: MockerFixture) -> None:
    # Given
    start_dir = Path("/project_dir")
    fs.create_dir(start_dir)
    call_order: list[str] = []
    mocker.patch("os.chdir", side_effect=lambda *_: call_order.append("chdir"))

    def _track_agents() -> MagicMock:
        call_order.append("agents")
        return app_mocks.agents_instance

    app_mocks.agents_class.side_effect = _track_agents

    # When
    runner.invoke(app, ["--start-directory", str(start_dir)])

    # Then
    assert call_order == ["chdir", "agents"]


# -- Session file ---------------------------------------------------------------


def test_main_with_session_file_passes_path_to_tui_init(app_mocks: _AppMocks, fs) -> None:
    # Given
    session_file = Path("/session.json")
    fs.create_file(session_file, contents="{}")

    # When
    runner.invoke(app, ["--session-file", str(session_file)])

    # Then
    call_args = app_mocks.tui.init.call_args
    assert call_args is not None
    passed_session_file = call_args[0][1]
    assert str(passed_session_file).endswith("session.json")
    assert call_args[0][2] is False
    assert call_args[0][3] is None


# -- Combined options -----------------------------------------------------------


def test_main_with_all_options_passes_correct_args_to_tui(app_mocks: _AppMocks, fs, mocker: MockerFixture) -> None:
    # Given
    config_file = Path("/my_config.toml")
    fs.create_file(config_file, contents='[general]\nmode = "coding"')
    session_file = Path("/my_session.json")
    fs.create_file(session_file, contents="{}")
    start_dir = Path("/my_project")
    fs.create_dir(start_dir)
    mocker.patch("os.chdir")

    # When
    runner.invoke(
        app,
        [
            "--one-shot",
            "--prompt",
            "Run tests",
            "--config-file",
            str(config_file),
            "--start-directory",
            str(start_dir),
            "--session-file",
            str(session_file),
        ],
    )

    # Then
    call_args = app_mocks.tui.init.call_args
    assert call_args is not None
    passed_session_file = call_args[0][1]
    assert str(passed_session_file).endswith("my_session.json")
    assert call_args[0][2] is True
    assert call_args[0][3] == "Run tests"
