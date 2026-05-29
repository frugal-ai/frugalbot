from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from textual.containers import VerticalScroll
from textual.widgets import Label, Markdown, OptionList, Rule, Static, TextArea
from textual.widgets.option_list import Option
from textual.worker import Worker, WorkerState

from frugalbot.agents import Agents
from frugalbot.events import MessageMarkup
from frugalbot.skills import Skill, Skills
from frugalbot.ui.autocomplete_mode import AutocompleteMode
from frugalbot.ui.commands.base import tui_typer, unload_commands
from frugalbot.ui.commands.skill import _create_skill_command
from frugalbot.ui.tui import Tui


class TestTuiApp:
    """Tests for the Tui App using Textual's run_test()."""

    @pytest.fixture(autouse=True)
    def global_mocks(self, mocker):
        # Patching is simplified and scoped to the test automatically
        mocker.patch.object(Tui, "_autocomplete_worker_loop", return_value=None)
        mocker.patch("frugalbot.ui.tui.read_history", new_callable=AsyncMock, return_value=[])
        mocker.patch("frugalbot.ui.tui.write_history", new_callable=AsyncMock)

    @pytest.fixture
    def app(self) -> Tui:
        """Creates a Tui instance with agent set up for testing."""
        return Tui()

    @pytest.fixture
    def patched_app(self, app: Tui, request) -> Tui:
        mock_agent = AsyncMock()
        mock_agent.init = AsyncMock()
        mock_agent.run = AsyncMock(return_value=None)
        mock_agent.next_client = AsyncMock()
        mock_agent.skills = Mock(spec=Skills)
        mock_agent.skills.skills = []
        mock_agent.name = "test-agent"
        mock_agents = Agents()
        mock_agents.agents = {"test-agent": mock_agent}
        app.agent_worker = None
        app.autocomplete_path_worker = MagicMock()
        app.autocomplete_path_worker.cancel = MagicMock()
        params = getattr(request, "param", {})
        one_shot_mode = params.get("one_shot_mode") or False
        unload_commands()
        app.init(mock_agents, params.get("session_file"), one_shot_mode, params.get("startup_prompt"))
        return app

    async def test_compose_contains_expected_widgets(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app

        # When
        async with app.run_test(size=(120, 40)) as _:
            assert app.query_one("#output", VerticalScroll) is not None
            assert app.query_one("#dropdown", OptionList) is not None
            assert app.query_one("#user-input", TextArea) is not None
            assert app.query_one("#bottom-bar") is not None
            assert app.query_one("#working-indicator", Static) is not None
            assert app.query_one("#status", Static) is not None

    async def test_toggle_auto_scroll_toggles_state(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as _:
            assert app.is_auto_scroll_enabled is True

            # When
            app.action_toggle_auto_scroll()

            # Then
            assert app.is_auto_scroll_enabled is False

            # When
            app.action_toggle_auto_scroll()

            # Then
            assert app.is_auto_scroll_enabled is True

    async def test_scroll_actions(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            # When / Then: scroll up does not raise
            app.action_scroll_output_up()
            await pilot.pause()
            # When / Then: scroll down does not raise
            app.action_scroll_output_down()
            await pilot.pause()
            # When / Then: scroll home does not raise
            app.action_scroll_output_home()
            await pilot.pause()
            # When / Then: scroll end does not raise
            app.action_scroll_output_end()
            await pilot.pause()

    async def test_update_spinner_cycles_frames(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as _:
            initial_index = app.spinner_index

            # When
            app.update_spinner()
            first_index = app.spinner_index

            # Then
            assert first_index == (initial_index + 1) % len(app.spinner_frames)

            # When
            app.update_spinner()

            # Then
            assert app.spinner_index == (first_index + 1) % len(app.spinner_frames)

    async def test_append_block_with_markdown_mounts_widgets(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            output = app.query_one("#output", VerticalScroll)
            initial_count = len(output.children)

            # When
            app.append_block("[bold]Test[/]", None, "# Hello\nWorld", MessageMarkup.MARKDOWN)
            await pilot.pause()

            # Then
            assert len(output.children) == initial_count + 2
            label = output.children[initial_count]
            assert isinstance(label, Label)
            assert "Test" in str(label.render())
            markdown_block = output.children[initial_count + 1]
            assert isinstance(markdown_block, Markdown)

    async def test_append_block_with_none_markup_mounts_static(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            output = app.query_one("#output", VerticalScroll)
            initial_count = len(output.children)

            # When
            app.append_block("[bold]ERROR[/]", None, "Something went wrong", MessageMarkup.NONE)
            await pilot.pause()

            # Then
            assert len(output.children) == initial_count + 2
            label = output.children[initial_count]
            assert isinstance(label, Label)
            static_block = output.children[initial_count + 1]
            assert isinstance(static_block, Static)
            assert static_block.render() is not None

    async def test_append_block_with_style_applies_style(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            output = app.query_one("#output", VerticalScroll)
            initial_count = len(output.children)

            # When
            app.append_block("[bold]DIM[/]", "dim", "Dim text", MessageMarkup.MARKDOWN)
            await pilot.pause()

            # Then
            markdown_block = output.children[initial_count + 1]
            assert isinstance(markdown_block, Markdown)
            assert markdown_block.styles.text_style.dim is True

    async def test_append_rule_mounts_rule_widget(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            output = app.query_one("#output", VerticalScroll)
            initial_count = len(output.children)

            # When
            app.append_rule()
            await pilot.pause()

            # Then
            assert len(output.children) == initial_count + 1
            rule = output.children[initial_count]
            assert isinstance(rule, Rule)

    async def test_start_and_append_to_streaming_block(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            output = app.query_one("#output", VerticalScroll)
            initial_count = len(output.children)

            # When - start streaming
            app.start_streaming_block("[bold]STREAM[/]", None, "Hello")
            await pilot.pause()

            # Then
            assert len(output.children) == initial_count + 2
            assert app.md_stream is not None

            # When - append to stream
            await app.append_to_streaming_block(" World")
            await pilot.pause()

    async def test_execute_help_command(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            # When
            app.execute_command("/help")
            await pilot.pause()

            # Then - the help command pushes a screen, no crash

    async def test_execute_quit_command(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            # When
            app.execute_command("/quit")
            await pilot.pause()

            # Then - the app exits, no crash

    async def test_execute_unknown_command_displays_error(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            output = app.query_one("#output", VerticalScroll)
            initial_count = len(output.children)

            # When
            app.execute_command("/unknown_command")
            await pilot.pause()

            # Then - error is appended to output
            assert len(output.children) > initial_count

    async def test_action_submit_with_command_clears_input(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            app.input.load_text("/help")

            # When
            await app.action_submit()
            await pilot.pause()

            # Then
            assert app.input.text == ""

    async def test_action_submit_with_text_adds_to_history(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        app.history = []
        async with app.run_test(size=(120, 40)) as pilot:
            app.input.load_text("Hello agent")

            # When
            await app.action_submit()
            await pilot.pause()

            # Then
            assert "Hello agent" in app.history
            assert app.input.text == ""

    async def test_action_cancel_agent_cancels_worker(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            # Replace the agent_worker with a mock for the test
            mock_worker = MagicMock()
            mock_worker.state = WorkerState.RUNNING
            mock_worker.cancel = MagicMock()
            app.agent_worker = mock_worker

            # When
            app.action_cancel_agent()
            await pilot.pause()

            # Then
            mock_worker.cancel.assert_called_once()

    async def test_action_cancel_agent_with_no_worker_does_nothing(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        app.agent_worker = None
        async with app.run_test(size=(120, 40)) as pilot:
            # When / Then - no crash
            app.action_cancel_agent()
            await pilot.pause()

    async def test_action_search_history_shows_dropdown(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            # When
            app.history = ["Hello", "World", "Test"]
            await app.action_search_history()
            await pilot.pause()

            # Then
            assert app.autocomplete_mode == AutocompleteMode.HISTORY
            assert app.dropdown.styles.display == "block"

    async def test_on_text_area_changed_with_slash_shows_command_autocomplete(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            app.input.load_text("/")

            # When
            await pilot.pause()

            # Then
            assert app.autocomplete_mode == AutocompleteMode.COMMAND
            assert app.dropdown.styles.display == "block"

    async def test_on_text_area_changed_with_at_shows_file_autocomplete(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            app.input.load_text("@")
            app.input.move_cursor_relative(0, 1)

            # When
            await pilot.pause()

            # Then
            assert app.autocomplete_mode == AutocompleteMode.FILE_PATH
            assert app.dropdown.styles.display == "block"

    async def test_on_text_area_changed_with_plain_text_hides_dropdown(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            app.input.load_text("hello")

            # When
            await pilot.pause()

            # Then
            assert app.autocomplete_mode == AutocompleteMode.NONE
            assert app.dropdown.styles.display == "none"

    async def test_on_text_area_cursor_moved_with_at_shows_file_autocomplete(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            app.input.load_text("prefix @file")
            app.input.move_cursor(location=(0, 7))

            # When
            await pilot.pause()

            # Then
            assert app.autocomplete_mode == AutocompleteMode.FILE_PATH
            assert app.dropdown.styles.display == "block"

    async def test_update_dropdown_options_shows_options(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            options = [Option("Item 1", id="1"), Option("Item 2", id="2")]

            # When
            app.dropdown.styles.display = "block"
            app._update_dropdown_options(options)
            await pilot.pause()

            # Then
            assert app.dropdown.option_count == 2

    async def test_update_dropdown_options_with_empty_list_does_not_change(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            app.dropdown.styles.display = "block"
            app._update_dropdown_options([Option("Existing", id="1")])
            await pilot.pause()

            # When - empty options
            app._update_dropdown_options([])
            await pilot.pause()

            # Then - existing options are preserved
            assert app.dropdown.option_count == 1

    async def test_worker_state_changed_running_shows_spinner(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        worker = MagicMock()
        worker.name = "agent"
        async with app.run_test(size=(120, 40)) as pilot:
            # When - worker starts running
            event = Worker.StateChanged(worker=worker, state=WorkerState.RUNNING)
            await app.on_worker_state_changed(event)
            await pilot.pause()

            # Then
            assert "Working..." in cast(Any, app.working_indicator.render()).plain

    async def test_worker_state_changed_success_hides_spinner(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        worker = MagicMock()
        worker.name = "agent"
        async with app.run_test(size=(120, 40)) as pilot:
            await app.on_worker_state_changed(Worker.StateChanged(worker=worker, state=WorkerState.RUNNING))
            await pilot.pause()

            # When - worker succeeds
            await app.on_worker_state_changed(Worker.StateChanged(worker=worker, state=WorkerState.SUCCESS))
            await pilot.pause()

            # Then
            assert "Worked for" in cast(Any, app.working_indicator.render()).plain

    async def test_worker_state_changed_error_hides_spinner(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        worker = MagicMock()
        worker.name = "agent"
        async with app.run_test(size=(120, 40)) as pilot:
            await app.on_worker_state_changed(Worker.StateChanged(worker=worker, state=WorkerState.RUNNING))
            await pilot.pause()

            # When - worker errors
            await app.on_worker_state_changed(Worker.StateChanged(worker=worker, state=WorkerState.ERROR))
            await pilot.pause()

            # Then
            assert "Worked for" in cast(Any, app.working_indicator.render()).plain

    async def test_action_cycle_model_calls_agent_next_client(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            # When
            await app.action_cycle_model()
            await pilot.pause()

            # Then
            cast(Any, app.agent.next_client).assert_awaited_once()

    async def test_action_submit_with_skills_command_doesnt_raise(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        skill = Skill(name="grill-me", description="", location="", content="")
        cast(Any, app.agent.skills).get.return_value = skill
        skill_func = _create_skill_command(skill.name)
        tui_typer.command(name=f"skill:{skill.name}", add_help_option=False, help=skill.description)(skill_func)
        async with app.run_test(size=(120, 40)) as pilot:
            app.input.load_text("/skill:grill-me My plan is to add a /reload command that reloads all dynamic modules (tools, commands, hooks, clients)'")

            # When
            await app.action_submit()
            await pilot.pause()

            # Then
            assert app.input.text == ""

    @pytest.mark.parametrize("patched_app", [{"startup_prompt": "Hello world"}], indirect=True)
    async def test_on_ready_submits_startup_prompt(self, patched_app: Tui, mocker) -> None:
        # Given
        app = patched_app
        # action_submit is mocked to avoid running the actual agent
        app.action_submit = AsyncMock()

        async with app.run_test(size=(120, 40)) as pilot:
            # When
            await pilot.pause()

            # Then
            app.action_submit.assert_called_once()
            assert app.input.text == "Hello world"

    @pytest.mark.parametrize("patched_app", [{"one_shot_mode": True, "startup_prompt": "prompt"}], indirect=True)
    async def test_worker_state_changed_one_shot_submits_quit(self, patched_app: Tui, mocker) -> None:
        # Given
        app = patched_app
        # Call init to avoid RuntimeError in on_mount.
        # Set startup_prompt to None to avoid an initial call to action_submit.
        app.action_submit = AsyncMock()
        worker = MagicMock()
        worker.name = "agent"

        async with app.run_test(size=(120, 40)) as pilot:
            # When - worker succeeds
            event = Worker.StateChanged(worker=worker, state=WorkerState.SUCCESS)
            await app.on_worker_state_changed(event)
            await pilot.pause()

            # Then
            assert app.input.text == "/quit"
            app.action_submit.assert_called()


class TestOutputUnhandledException:
    """Tests for Tui._output_unhandled_exception."""

    @pytest.fixture(autouse=True)
    def global_mocks(self, mocker):
        mocker.patch.object(Tui, "_autocomplete_worker_loop", return_value=None)
        mocker.patch("frugalbot.ui.history.read_history", new_callable=AsyncMock, return_value=[])
        mocker.patch("frugalbot.ui.history.write_history", new_callable=AsyncMock)

    @pytest.fixture
    def app(self) -> Tui:
        return Tui()

    @pytest.fixture
    def patched_app(self, app: Tui) -> Tui:
        mock_agent = AsyncMock()
        mock_agent.skills = Mock(spec=Skills)
        mock_agent.skills.skills = []
        mock_agent.name = "test-agent"
        mock_agents = Agents()
        mock_agents.agents = {"test-agent": mock_agent}
        unload_commands()
        app.init(mock_agents, None, False, None)
        return app

    async def test_output_unhandled_exception_with_exception_calls_append_block(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        app.append_block = MagicMock()
        exception = ValueError("something broke")
        try:
            raise exception
        except ValueError:
            pass  # Ensure traceback is attached

        # When
        app._output_unhandled_exception(exception)

        # Then
        app.append_block.assert_called_once()
        call_args = app.append_block.call_args
        assert call_args[0][0] == "[bold red]UNEXPECTED ERROR[/]"
        assert call_args[0][1] is None
        assert "something broke" in call_args[0][2]
        assert "Traceback" in call_args[0][2]
        assert call_args[0][3] == MessageMarkup.NONE

    async def test_output_unhandled_exception_with_exception_without_traceback_includes_error_message(
        self,
        patched_app: Tui,
    ) -> None:
        # Given
        app = patched_app
        app.append_block = MagicMock()
        exception = RuntimeError("no traceback attached")

        # When
        app._output_unhandled_exception(exception)

        # Then
        app.append_block.assert_called_once()
        call_args = app.append_block.call_args
        assert "no traceback attached" in call_args[0][2]
        assert "RuntimeError" in call_args[0][2]


class TestExecuteCommandValueErrorHandled:
    """Tests for Bug 2: execute_command re-raising ValueError on shlex parse failure."""

    @pytest.fixture(autouse=True)
    def global_mocks(self, mocker):
        mocker.patch.object(Tui, "_autocomplete_worker_loop", return_value=None)
        mocker.patch("frugalbot.ui.history.read_history", new_callable=AsyncMock, return_value=[])
        mocker.patch("frugalbot.ui.history.write_history", new_callable=AsyncMock)

    @pytest.fixture
    def app(self) -> Tui:
        return Tui()

    @pytest.fixture
    def patched_app(self, app: Tui) -> Tui:
        mock_agent = AsyncMock()
        mock_agent.skills = Mock(spec=Skills)
        mock_agent.skills.skills = []
        mock_agent.name = "test-agent"
        mock_agents = Agents()
        mock_agents.agents = {"test-agent": mock_agent}
        unload_commands()
        app.init(mock_agents, None, False, None)
        return app

    async def test_execute_command_with_unmatched_quotes_on_help_does_not_raise(
        self,
        patched_app: Tui,
    ) -> None:
        """Bug 2: When shlex.split() fails with unmatched quotes on a command that
        does NOT accept nargs=-1 (like /help), the ValueError must NOT propagate
        and crash the app. Instead, a friendly error must be displayed."""
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            output = app.query_one("#output", VerticalScroll)
            initial_count = len(output.children)

            # When - unmatched quote on /help (which does NOT have nargs=-1)
            app.call_after_refresh(app.execute_command, '/help "unmatched')
            await pilot.pause()

            # Then - no exception raised, and an error message is appended to output
            assert len(output.children) > initial_count

    @pytest.mark.parametrize(
        "malformed_input",
        [
            '/help "hello',
            '/quit "unterminated',
            "/help 'missing",
            '/help "unclosed "inner',
        ],
    )
    async def test_execute_command_with_various_malformed_quotes_does_not_raise(
        self,
        patched_app: Tui,
        malformed_input: str,
    ) -> None:
        """Bug 2: Various forms of unmatched/malformed quotes on commands without
        nargs=-1 must not crash the app."""
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            # When / Then - no exception raised for any malformed input
            app.execute_command(malformed_input)
            await pilot.pause()
