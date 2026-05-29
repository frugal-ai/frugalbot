import pytest
from textual.app import App
from textual.widgets import Button, Markdown

from frugalbot.ui.screens.help import HelpScreen


@pytest.fixture
def help_content() -> str:
    return "# Help\n\nThis is help content."


@pytest.fixture
def help_screen(help_content: str) -> HelpScreen:
    return HelpScreen(help_content)


@pytest.fixture
def app_with_help_screen(help_content: str) -> App[None]:
    """Creates a minimal Textual app for testing HelpScreen via run_test()."""

    class TestApp(App[None]):
        def on_mount(self) -> None:
            self.push_screen(HelpScreen(help_content))

    return TestApp()


# --- Tests for __init__ ---


def test_init_with_valid_content_stores_content(help_content: str) -> None:
    # Given

    # When
    screen = HelpScreen(help_content)

    # Then
    assert screen.content == help_content


def test_init_with_empty_content_stores_empty_string() -> None:
    # Given

    # When
    screen = HelpScreen("")

    # Then
    assert screen.content == ""


# --- Tests for compose ---


async def test_compose_with_valid_content_contains_dialog(
    app_with_help_screen: App[None],
) -> None:
    # Given
    app = app_with_help_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, HelpScreen)
        dialog = screen.query_one("#dialog")
        assert dialog is not None


async def test_compose_with_valid_content_contains_markdown_widget(
    app_with_help_screen: App[None],
) -> None:
    # Given
    app = app_with_help_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, HelpScreen)
        content_widget = screen.query_one("#content", Markdown)
        assert content_widget is not None


async def test_compose_with_valid_content_contains_close_button(
    app_with_help_screen: App[None],
) -> None:
    # Given
    app = app_with_help_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, HelpScreen)
        close_button = screen.query_one("#close", Button)
        assert close_button is not None


async def test_compose_with_valid_content_close_button_has_primary_variant(
    app_with_help_screen: App[None],
) -> None:
    # Given
    app = app_with_help_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, HelpScreen)
        close_button = screen.query_one("#close", Button)
        assert close_button.variant == "primary"


async def test_compose_with_valid_content_close_button_label_is_close(
    app_with_help_screen: App[None],
) -> None:
    # Given
    app = app_with_help_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, HelpScreen)
        close_button = screen.query_one("#close", Button)
        assert str(close_button.label) == "Close"


async def test_compose_with_valid_content_contains_button_group(
    app_with_help_screen: App[None],
) -> None:
    # Given
    app = app_with_help_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, HelpScreen)
        button_group = screen.query_one("#button-group")
        assert button_group is not None


# --- Tests for on_mount ---


async def test_on_mount_sets_help_text_widget_reference(
    app_with_help_screen: App[None],
) -> None:
    # Given
    app = app_with_help_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, HelpScreen)
        assert screen.help_text_widget is not None
        assert isinstance(screen.help_text_widget, Markdown)


async def test_on_mount_help_text_widget_is_content_widget(
    app_with_help_screen: App[None],
) -> None:
    # Given
    app = app_with_help_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, HelpScreen)
        content_widget = screen.query_one("#content", Markdown)
        assert screen.help_text_widget is content_widget


# --- Tests for scroll actions ---


async def test_action_scroll_text_page_up_calls_scroll_page_up(
    app_with_help_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_help_screen
    mock_scroll = mocker.patch("textual.widgets.Markdown.scroll_page_up", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, HelpScreen)
        await pilot.pause()

        screen.action_scroll_text_page_up()

        mock_scroll.assert_called_once()


async def test_action_scroll_text_page_down_calls_scroll_page_down(
    app_with_help_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_help_screen
    mock_scroll = mocker.patch("textual.widgets.Markdown.scroll_page_down", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, HelpScreen)
        await pilot.pause()

        screen.action_scroll_text_page_down()

        mock_scroll.assert_called_once()


async def test_action_scroll_text_home_calls_scroll_home(
    app_with_help_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_help_screen
    mock_scroll = mocker.patch("textual.widgets.Markdown.scroll_home", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, HelpScreen)
        await pilot.pause()

        screen.action_scroll_text_home()

        mock_scroll.assert_called_once()


async def test_action_scroll_text_end_calls_scroll_end(
    app_with_help_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_help_screen
    mock_scroll = mocker.patch("textual.widgets.Markdown.scroll_end", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, HelpScreen)
        await pilot.pause()

        screen.action_scroll_text_end()

        mock_scroll.assert_called_once()


# --- Tests for on_button_pressed ---


async def test_on_button_pressed_with_close_button_calls_dismiss(
    app_with_help_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_help_screen
    mock_dismiss = mocker.patch.object(HelpScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, HelpScreen)
        await pilot.pause()

        close_button = screen.query_one("#close", Button)
        screen.post_message(Button.Pressed(close_button))
        await pilot.pause()

        mock_dismiss.assert_called_once()


async def test_on_button_pressed_with_non_close_button_does_not_call_dismiss(
    app_with_help_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_help_screen
    mock_dismiss = mocker.patch.object(HelpScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, HelpScreen)
        await pilot.pause()

        # Create a fake button with a different id
        fake_button = Button("Other", id="other")
        screen.post_message(Button.Pressed(fake_button))
        await pilot.pause()

        mock_dismiss.assert_not_called()
