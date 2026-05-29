from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from textual import events
from textual.containers import VerticalScroll
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from frugalbot.agents import Agents
from frugalbot.ui.autocomplete_mode import AutocompleteMode
from frugalbot.ui.commands.base import command, tui_typer, unload_commands
from frugalbot.ui.tui import Tui
from frugalbot.ui.widgets.user_message_text_area import UserMessageTextArea


@pytest.fixture(autouse=True)
def cleanup_typer():
    """Ensure tui_typer is clean before and after every test."""
    unload_commands()
    yield
    unload_commands()


@pytest.fixture(autouse=True)
def global_mocks(mocker):
    """Patches that must be in place for every test."""
    mocker.patch.object(Tui, "_autocomplete_worker_loop", return_value=None)
    mocker.patch("frugalbot.ui.tui.read_history", new_callable=AsyncMock, return_value=[])
    mocker.patch("frugalbot.ui.tui.write_history", new_callable=AsyncMock)


@pytest.fixture
def app() -> Tui:
    """Creates a Tui instance with agent set up for testing."""
    return Tui()


@pytest.fixture
def patched_app(app: Tui) -> Tui:
    mock_agent = AsyncMock()
    mock_agent.run = AsyncMock(return_value=None)
    mock_agent.name = "test-agent"
    app.autocomplete_path_worker = MagicMock()
    app.autocomplete_path_worker.cancel = MagicMock()
    agents = Agents()
    agents.agents = {"test-agent": mock_agent}
    app.init(agents, None, False, None)
    return app


async def _show_dropdown_via_history(app: Tui, history_entries: list[str], pilot) -> None:
    """Helper: show dropdown via history search and wait for it to settle."""
    app.history = history_entries
    await app.action_search_history()
    await pilot.pause()


class TestOnMount:
    """Tests for UserMessageTextArea.on_mount."""

    async def test_on_mount_sets_dropdown_reference(self, patched_app: Tui) -> None:
        # Given
        app = patched_app

        # When / Then
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            input_widget = cast(UserMessageTextArea, app.input)
            assert input_widget.dropdown is not None
            assert isinstance(input_widget.dropdown, OptionList)

    async def test_on_mount_sets_output_reference(self, patched_app: Tui) -> None:
        # Given
        app = patched_app

        # When / Then
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            input_widget = cast(UserMessageTextArea, app.input)
            assert input_widget.output is not None
            assert isinstance(input_widget.output, VerticalScroll)

    async def test_on_mount_sets_tui_reference(self, patched_app: Tui) -> None:
        # Given
        app = patched_app

        # When / Then
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            input_widget = cast(UserMessageTextArea, app.input)
            assert input_widget.tui is app


class TestActionCursorUp:
    """Tests for UserMessageTextArea.action_cursor_up."""

    async def test_action_cursor_up_with_dropdown_visible_delegates_to_dropdown(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            await _show_dropdown_via_history(app, ["Opt1", "Opt2"], pilot)
            app.dropdown.highlighted = 1

            # When
            input_widget.action_cursor_up()

            # Then
            assert app.dropdown.highlighted == 0

    async def test_action_cursor_up_with_dropdown_hidden_delegates_to_parent(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            input_widget.load_text("Hello\nWorld")
            input_widget.move_cursor((1, 0))
            await pilot.pause()

            # When
            input_widget.action_cursor_up()

            # Then
            assert input_widget.cursor_location == (0, 0)


class TestActionCursorDown:
    """Tests for UserMessageTextArea.action_cursor_down."""

    async def test_action_cursor_down_with_dropdown_visible_delegates_to_dropdown(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            await _show_dropdown_via_history(app, ["Opt1", "Opt2"], pilot)
            # highlighted should be 0 after search_history

            # When
            input_widget.action_cursor_down()

            # Then
            assert app.dropdown.highlighted == 1

    async def test_action_cursor_down_with_dropdown_hidden_delegates_to_parent(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            input_widget.load_text("Hello\nWorld")
            input_widget.move_cursor((0, 0))
            await pilot.pause()

            # When
            input_widget.action_cursor_down()

            # Then
            assert input_widget.cursor_location == (1, 0)


class TestActionCursorPageUp:
    """Tests for UserMessageTextArea.action_cursor_page_up."""

    async def test_action_cursor_page_up_with_dropdown_visible_delegates_to_dropdown(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            await _show_dropdown_via_history(app, [f"Opt{i}" for i in range(10)], pilot)
            app.dropdown.highlighted = 5

            # When
            input_widget.action_cursor_page_up()

            # Then - dropdown handles the page up (moves up)
            assert app.dropdown.highlighted is not None
            assert app.dropdown.highlighted < 5

    async def test_action_cursor_page_up_with_dropdown_hidden_delegates_to_parent(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            input_widget.load_text("\n".join([f"Line {i}" for i in range(20)]))
            input_widget.move_cursor((15, 0))
            await pilot.pause()

            # When
            input_widget.action_cursor_page_up()

            # Then - text area handles the page up (cursor moved upward)
            assert input_widget.cursor_location[0] < 15


class TestActionCursorPageDown:
    """Tests for UserMessageTextArea.action_cursor_page_down."""

    async def test_action_cursor_page_down_with_dropdown_visible_delegates_to_dropdown(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            await _show_dropdown_via_history(app, [f"Opt{i}" for i in range(10)], pilot)
            app.dropdown.highlighted = 2

            # When
            input_widget.action_cursor_page_down()

            # Then - dropdown handles the page down (moves down)
            assert app.dropdown.highlighted is not None
            assert app.dropdown.highlighted > 2

    async def test_action_cursor_page_down_with_dropdown_hidden_delegates_to_parent(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            input_widget.load_text("\n".join([f"Line {i}" for i in range(20)]))
            input_widget.move_cursor((0, 0))
            await pilot.pause()

            # When
            input_widget.action_cursor_page_down()

            # Then - text area handles the page down (cursor moved downward)
            assert input_widget.cursor_location[0] > 0


class TestOnKeyWithDropdownVisible:
    """Tests for UserMessageTextArea._on_key when the dropdown is visible.

    NOTE: Assertions are made immediately after `await _on_key()` returns, **before**
    `pilot.pause()`. The `_on_key` method modifies text, autocomplete_mode, and
    dropdown display synchronously within its execution. Calling `pilot.pause()`
    afterwards would let Textual's event queue process TextArea.Changed /
    SelectionChanged events, which fire the TUI's @on-decorated handlers and
    overwrite the state we want to verify.
    """

    async def test_on_key_with_enter_and_history_mode_replaces_text(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            await _show_dropdown_via_history(app, ["hello world"], pilot)
            input_widget.load_text("hello")
            await pilot.pause()

            # When
            key_event = events.Key(key="enter", character="\r")
            await input_widget._on_key(key_event)

            # Then — assert immediately before pilot.pause() to avoid @on handlers
            assert input_widget.text == "hello world"
            assert app.autocomplete_mode == AutocompleteMode.NONE
            assert app.dropdown.styles.display == "none"

    async def test_on_key_with_enter_and_command_mode_without_params_replaces_and_submits(self, patched_app: Tui) -> None:
        # Given
        app = patched_app

        @command("test-cmd")
        def dummy_cmd():
            pass

        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            await _show_dropdown_via_history(app, ["unused"], pilot)
            app.autocomplete_mode = AutocompleteMode.COMMAND
            app.dropdown.set_options([Option("/test-cmd - Test help", id="/test-cmd")])
            app.dropdown.highlighted = 0
            app.action_submit = AsyncMock()
            await pilot.pause()

            # When
            key_event = events.Key(key="enter", character="\r")
            await input_widget._on_key(key_event)

            # Then — command without params: option_text is just the id (no space)
            assert input_widget.text == "/test-cmd"
            assert app.autocomplete_mode == AutocompleteMode.NONE
            assert app.dropdown.styles.display == "none"
            app.action_submit.assert_awaited_once()

    async def test_on_key_with_enter_and_command_mode_with_params_replaces_and_does_not_submit(self, patched_app: Tui) -> None:
        # Given
        app = patched_app

        # Use a unique command name to avoid conflict with built-in /load
        @command("my-load-cmd")
        def my_load_cmd(session_file: str):
            pass

        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            await _show_dropdown_via_history(app, ["unused"], pilot)
            app.autocomplete_mode = AutocompleteMode.COMMAND
            app.dropdown.set_options([Option("/my-load-cmd - Load session", id="/my-load-cmd")])
            app.dropdown.highlighted = 0
            app.action_submit = AsyncMock()
            await pilot.pause()

            # When
            key_event = events.Key(key="enter", character="\r")
            await input_widget._on_key(key_event)

            # Then — command with params gets trailing space
            assert input_widget.text == "/my-load-cmd "
            assert app.autocomplete_mode == AutocompleteMode.NONE
            assert app.dropdown.styles.display == "none"
            app.action_submit.assert_not_called()

    async def test_on_key_with_enter_and_file_path_mode_inserts_at_cursor(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            await _show_dropdown_via_history(app, ["unused"], pilot)
            app.autocomplete_mode = AutocompleteMode.FILE_PATH
            app.dropdown.set_options([Option("src/main.py", id="src/main.py")])
            app.dropdown.highlighted = 0
            input_widget.load_text("@src")
            await pilot.pause()

            # When
            key_event = events.Key(key="enter", character="\r")
            await input_widget._on_key(key_event)

            # Then — file path mode inserts @filepath at word boundary
            assert "@src/main.py" in input_widget.text
            assert app.autocomplete_mode == AutocompleteMode.NONE
            assert app.dropdown.styles.display == "none"

    async def test_on_key_with_tab_and_history_mode_replaces_text(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            await _show_dropdown_via_history(app, ["search history"], pilot)
            input_widget.load_text("search")
            await pilot.pause()

            # When
            key_event = events.Key(key="tab", character=None)
            await input_widget._on_key(key_event)

            # Then
            assert input_widget.text == "search history"
            assert app.autocomplete_mode == AutocompleteMode.NONE

    async def test_on_key_with_alt_enter_and_history_mode_replaces_text(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            await _show_dropdown_via_history(app, ["query something"], pilot)
            input_widget.load_text("query")
            await pilot.pause()

            # When
            key_event = events.Key(key="alt+enter", character=None)
            await input_widget._on_key(key_event)

            # Then
            assert input_widget.text == "query something"

    async def test_on_key_with_escape_hides_dropdown(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            await _show_dropdown_via_history(app, ["hello world"], pilot)

            # When
            key_event = events.Key(key="escape", character=None)
            await input_widget._on_key(key_event)
            await pilot.pause()

            # Then
            assert app.autocomplete_mode == AutocompleteMode.NONE
            assert app.dropdown.styles.display == "none"

    async def test_on_key_with_none_highlighted_option_does_nothing(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            await _show_dropdown_via_history(app, ["hello world"], pilot)
            input_widget.load_text("hello")
            await pilot.pause()
            app.dropdown.highlighted = None

            # When
            key_event = events.Key(key="enter", character="\r")
            await input_widget._on_key(key_event)
            await pilot.pause()

            # Then - text should remain unchanged
            assert input_widget.text == "hello"

    async def test_on_key_with_none_option_id_shows_error_notification(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            await _show_dropdown_via_history(app, ["hello world"], pilot)
            input_widget.load_text("hello")
            await pilot.pause()
            # Replace with an option that has None id
            app.dropdown.set_options([Option("hello world", id=None)])
            app.dropdown.highlighted = 0

            # When
            key_event = events.Key(key="enter", character="\r")
            await input_widget._on_key(key_event)
            await pilot.pause()

            # Then - text should remain unchanged
            assert input_widget.text == "hello"


class TestOnKeyWithDropdownHidden:
    """Tests for UserMessageTextArea._on_key when the dropdown is hidden."""

    async def test_on_key_with_enter_and_hidden_dropdown_returns_early(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            input_widget.load_text("hello")
            await pilot.pause()

            # When
            key_event = events.Key(key="enter", character="\r")
            await input_widget._on_key(key_event)
            await pilot.pause()

            # Then - text should remain unchanged (event not consumed)
            assert input_widget.text == "hello"

    async def test_on_key_with_escape_and_hidden_dropdown_returns_early(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            input_widget.load_text("hello")
            await pilot.pause()

            # When
            key_event = events.Key(key="escape", character=None)
            await input_widget._on_key(key_event)
            await pilot.pause()

            # Then - text should remain unchanged
            assert input_widget.text == "hello"


class TestOnKeyEdgeCases:
    """Edge case tests for UserMessageTextArea._on_key."""

    async def test_on_key_with_unsupported_autocomplete_mode_raises_value_error(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            # Show dropdown via history, then switch mode to NONE (unsupported in this context)
            await _show_dropdown_via_history(app, ["test option"], pilot)
            input_widget.load_text("test")
            await pilot.pause()
            app._autocomplete_mode = AutocompleteMode.NONE

            # When / Then
            key_event = events.Key(key="enter", character="\r")
            with pytest.raises(ValueError, match="Unsupported autocomplete type"):
                await input_widget._on_key(key_event)

    async def test_on_key_with_non_selection_key_does_not_modify_text(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            await _show_dropdown_via_history(app, ["hello world"], pilot)
            input_widget.load_text("hello")
            await pilot.pause()

            # When
            key_event = events.Key(key="a", character="a")
            await input_widget._on_key(key_event)
            await pilot.pause()

            # Then - text should remain unchanged
            assert input_widget.text == "hello"

    async def test_on_key_enter_cursors_to_end_of_replaced_text(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            await _show_dropdown_via_history(app, ["hello world completion"], pilot)
            input_widget.load_text("hello")
            await pilot.pause()

            # When
            key_event = events.Key(key="enter", character="\r")
            await input_widget._on_key(key_event)

            # Then — cursor should be at end of the new text
            expected_line_count = input_widget.document.line_count
            last_row = expected_line_count - 1 if expected_line_count else 0
            expected_col = len(input_widget.document.get_line(last_row))
            assert input_widget.cursor_location == (last_row, expected_col)

    async def test_on_key_with_enter_and_command_with_skill_prefix_does_not_submit(self, patched_app: Tui) -> None:
        # Given
        app = patched_app
        # Register a skill: prefixed command (these should not auto-submit)
        tui_typer.command(name="skill:grill-me", add_help_option=False, help="Grill a plan")(lambda: None)

        async with app.run_test(size=(120, 40)) as pilot:
            input_widget = cast(UserMessageTextArea, app.input)
            await _show_dropdown_via_history(app, ["unused"], pilot)
            app.autocomplete_mode = AutocompleteMode.COMMAND
            app.dropdown.set_options([Option("/skill:grill-me - Grill a plan", id="/skill:grill-me")])
            app.dropdown.highlighted = 0
            app.action_submit = AsyncMock()

            # When
            key_event = events.Key(key="enter", character="\r")
            await input_widget._on_key(key_event)

            # Then — skill commands should not auto-submit
            assert input_widget.text == "/skill:grill-me"
            app.action_submit.assert_not_called()
