import pytest
from textual.app import App
from textual.widgets import Button, Label, TextArea

from frugalbot.ui.screens.text_prompt import TextPromptScreen

# --- Fixtures ---


@pytest.fixture
def text_prompt_screen() -> TextPromptScreen:
    return TextPromptScreen("Enter your name:")


@pytest.fixture
def app_with_text_prompt_screen() -> App[None]:
    """Creates a minimal Textual app for testing TextPromptScreen."""

    class TestApp(App[None]):
        def on_mount(self) -> None:
            self.push_screen(TextPromptScreen("Enter your name:"))

    return TestApp()


# --- Tests for __init__ ---


def test_init_with_prompt_stores_prompt() -> None:
    # Given
    prompt = "Enter your name:"

    # When
    screen = TextPromptScreen(prompt)

    # Then
    assert screen.prompt == prompt


def test_init_with_empty_string_stores_empty_prompt() -> None:
    # Given
    prompt = ""

    # When
    screen = TextPromptScreen(prompt)

    # Then
    assert screen.prompt == prompt


def test_init_with_long_prompt_stores_prompt() -> None:
    # Given
    prompt = "Please enter a detailed description of the changes you would like to make to the configuration file:"

    # When
    screen = TextPromptScreen(prompt)

    # Then
    assert screen.prompt == prompt


# --- Tests for compose ---


async def test_compose_with_valid_prompt_contains_dialog(
    app_with_text_prompt_screen: App[None],
) -> None:
    # Given
    app = app_with_text_prompt_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, TextPromptScreen)
        dialog = screen.query_one("#dialog")
        assert dialog is not None


async def test_compose_with_valid_prompt_contains_prompt_label(
    app_with_text_prompt_screen: App[None],
) -> None:
    # Given
    app = app_with_text_prompt_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, TextPromptScreen)
        label = screen.query_one("#prompt-label", Label)
        assert label is not None
        assert str(label.content) == "Enter your name:"


async def test_compose_with_valid_prompt_contains_prompt_input(
    app_with_text_prompt_screen: App[None],
) -> None:
    # Given
    app = app_with_text_prompt_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, TextPromptScreen)
        text_area = screen.query_one("#prompt-input", TextArea)
        assert text_area is not None


async def test_compose_with_valid_prompt_contains_button_group(
    app_with_text_prompt_screen: App[None],
) -> None:
    # Given
    app = app_with_text_prompt_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, TextPromptScreen)
        button_group = screen.query_one("#button-group")
        assert button_group is not None


async def test_compose_with_valid_prompt_contains_submit_button(
    app_with_text_prompt_screen: App[None],
) -> None:
    # Given
    app = app_with_text_prompt_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, TextPromptScreen)
        submit_button = screen.query_one("#submit", Button)
        assert submit_button is not None
        assert submit_button.variant == "primary"
        assert str(submit_button.label) == "Submit"


async def test_compose_with_valid_prompt_contains_cancel_button(
    app_with_text_prompt_screen: App[None],
) -> None:
    # Given
    app = app_with_text_prompt_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, TextPromptScreen)
        cancel_button = screen.query_one("#cancel", Button)
        assert cancel_button is not None
        assert cancel_button.variant == "warning"
        assert str(cancel_button.label) == "Cancel"


# --- Tests for on_mount ---


async def test_on_mount_focuses_prompt_input(
    app_with_text_prompt_screen: App[None],
) -> None:
    # Given
    app = app_with_text_prompt_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, TextPromptScreen)
        text_area = screen.query_one("#prompt-input", TextArea)
        assert screen.focused == text_area


# --- Tests for on_button_pressed ---


async def test_on_button_pressed_with_submit_button_dismisses_with_text(
    app_with_text_prompt_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_text_prompt_screen
    mock_dismiss = mocker.patch.object(TextPromptScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, TextPromptScreen)
        await pilot.pause()

        text_area = screen.query_one("#prompt-input", TextArea)
        text_area.text = "Hello, World!"

        submit_button = screen.query_one("#submit", Button)
        screen.post_message(Button.Pressed(submit_button))
        await pilot.pause()

        mock_dismiss.assert_called_once_with("Hello, World!")


async def test_on_button_pressed_with_submit_button_dismisses_with_empty_text_when_no_input(
    app_with_text_prompt_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_text_prompt_screen
    mock_dismiss = mocker.patch.object(TextPromptScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, TextPromptScreen)
        await pilot.pause()

        submit_button = screen.query_one("#submit", Button)
        screen.post_message(Button.Pressed(submit_button))
        await pilot.pause()

        mock_dismiss.assert_called_once_with("")


async def test_on_button_pressed_with_submit_button_dismisses_with_multiline_text(
    app_with_text_prompt_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_text_prompt_screen
    mock_dismiss = mocker.patch.object(TextPromptScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, TextPromptScreen)
        await pilot.pause()

        text_area = screen.query_one("#prompt-input", TextArea)
        text_area.text = "Line 1\nLine 2\nLine 3"

        submit_button = screen.query_one("#submit", Button)
        screen.post_message(Button.Pressed(submit_button))
        await pilot.pause()

        mock_dismiss.assert_called_once_with("Line 1\nLine 2\nLine 3")


async def test_on_button_pressed_with_cancel_button_dismisses_with_empty_string(
    app_with_text_prompt_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_text_prompt_screen
    mock_dismiss = mocker.patch.object(TextPromptScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, TextPromptScreen)
        await pilot.pause()

        # Even if there's text in the input, cancel should dismiss with empty string
        text_area = screen.query_one("#prompt-input", TextArea)
        text_area.text = "Some text that should be discarded"

        cancel_button = screen.query_one("#cancel", Button)
        screen.post_message(Button.Pressed(cancel_button))
        await pilot.pause()

        mock_dismiss.assert_called_once_with("")


async def test_on_button_pressed_with_unrecognized_button_dismisses_with_empty_string(
    app_with_text_prompt_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_text_prompt_screen
    mock_dismiss = mocker.patch.object(TextPromptScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, TextPromptScreen)
        await pilot.pause()

        fake_button = Button("Fake", id="fake")
        screen.post_message(Button.Pressed(fake_button))
        await pilot.pause()

        mock_dismiss.assert_called_once_with("")


async def test_on_button_pressed_with_submit_button_dismisses_with_whitespace_text(
    app_with_text_prompt_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_text_prompt_screen
    mock_dismiss = mocker.patch.object(TextPromptScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, TextPromptScreen)
        await pilot.pause()

        text_area = screen.query_one("#prompt-input", TextArea)
        text_area.text = "   "

        submit_button = screen.query_one("#submit", Button)
        screen.post_message(Button.Pressed(submit_button))
        await pilot.pause()

        mock_dismiss.assert_called_once_with("   ")
