import pytest
from textual.app import App
from textual.events import Key
from textual.widgets import Button, Markdown

from frugalbot.events import QuestionResponse, QuestionType
from frugalbot.ui.screens.question import QuestionScreen

# --- Fixtures ---


@pytest.fixture
def yes_no_screen() -> QuestionScreen:
    return QuestionScreen("Are you sure?", QuestionType.YES_NO)


@pytest.fixture
def yes_no_always_screen() -> QuestionScreen:
    return QuestionScreen("Proceed?", QuestionType.YES_NO_ALWAYS)


@pytest.fixture
def ok_only_screen() -> QuestionScreen:
    return QuestionScreen("Operation complete.", QuestionType.OK_ONLY)


@pytest.fixture
def app_with_yes_no_screen() -> App[None]:
    """Creates a minimal Textual app for testing YES_NO QuestionScreen."""

    class TestApp(App[None]):
        def on_mount(self) -> None:
            self.push_screen(QuestionScreen("Are you sure?", QuestionType.YES_NO))

    return TestApp()


@pytest.fixture
def app_with_yes_no_always_screen() -> App[None]:
    """Creates a minimal Textual app for testing YES_NO_ALWAYS QuestionScreen."""

    class TestApp(App[None]):
        def on_mount(self) -> None:
            self.push_screen(QuestionScreen("Proceed?", QuestionType.YES_NO_ALWAYS))

    return TestApp()


@pytest.fixture
def app_with_ok_only_screen() -> App[None]:
    """Creates a minimal Textual app for testing OK_ONLY QuestionScreen."""

    class TestApp(App[None]):
        def on_mount(self) -> None:
            self.push_screen(QuestionScreen("Operation complete.", QuestionType.OK_ONLY))

    return TestApp()


# --- Tests for __init__ ---


def test_init_with_yes_no_stores_question_and_type() -> None:
    # Given
    question = "Are you sure?"
    question_type = QuestionType.YES_NO

    # When
    screen = QuestionScreen(question, question_type)

    # Then
    assert screen.question == question
    assert screen.question_type == question_type


def test_init_with_yes_no_always_stores_question_and_type() -> None:
    # Given
    question = "Proceed?"
    question_type = QuestionType.YES_NO_ALWAYS

    # When
    screen = QuestionScreen(question, question_type)

    # Then
    assert screen.question == question
    assert screen.question_type == question_type


def test_init_with_ok_only_stores_question_and_type() -> None:
    # Given
    question = "Operation complete."
    question_type = QuestionType.OK_ONLY

    # When
    screen = QuestionScreen(question, question_type)

    # Then
    assert screen.question == question
    assert screen.question_type == question_type


# --- Tests for compose ---


async def test_compose_with_yes_no_contains_dialog(
    app_with_yes_no_screen: App[None],
) -> None:
    # Given
    app = app_with_yes_no_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        dialog = screen.query_one("#dialog")
        assert dialog is not None


async def test_compose_with_yes_no_contains_question_markdown(
    app_with_yes_no_screen: App[None],
) -> None:
    # Given
    app = app_with_yes_no_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        question_widget = screen.query_one("#question", Markdown)
        assert question_widget is not None


async def test_compose_with_yes_no_contains_yes_button(
    app_with_yes_no_screen: App[None],
) -> None:
    # Given
    app = app_with_yes_no_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        yes_button = screen.query_one("#yes", Button)
        assert yes_button is not None
        assert yes_button.variant == "success"


async def test_compose_with_yes_no_contains_no_button(
    app_with_yes_no_screen: App[None],
) -> None:
    # Given
    app = app_with_yes_no_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        no_button = screen.query_one("#no", Button)
        assert no_button is not None
        assert no_button.variant == "error"


async def test_compose_with_yes_no_does_not_contain_always_button(
    app_with_yes_no_screen: App[None],
) -> None:
    # Given
    app = app_with_yes_no_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        always_buttons = screen.query("#always")
        assert len(always_buttons) == 0


async def test_compose_with_yes_no_contains_button_group(
    app_with_yes_no_screen: App[None],
) -> None:
    # Given
    app = app_with_yes_no_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        button_group = screen.query_one("#button-group")
        assert button_group is not None


async def test_compose_with_yes_no_always_contains_always_button(
    app_with_yes_no_always_screen: App[None],
) -> None:
    # Given
    app = app_with_yes_no_always_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        always_button = screen.query_one("#always", Button)
        assert always_button is not None
        assert always_button.variant == "primary"


async def test_compose_with_yes_no_always_contains_yes_button(
    app_with_yes_no_always_screen: App[None],
) -> None:
    # Given
    app = app_with_yes_no_always_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        yes_button = screen.query_one("#yes", Button)
        assert yes_button is not None


async def test_compose_with_yes_no_always_contains_no_button(
    app_with_yes_no_always_screen: App[None],
) -> None:
    # Given
    app = app_with_yes_no_always_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        no_button = screen.query_one("#no", Button)
        assert no_button is not None


async def test_compose_with_ok_only_contains_ok_button(
    app_with_ok_only_screen: App[None],
) -> None:
    # Given
    app = app_with_ok_only_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        ok_button = screen.query_one("#ok", Button)
        assert ok_button is not None
        assert ok_button.variant == "primary"


async def test_compose_with_ok_only_does_not_contain_yes_button(
    app_with_ok_only_screen: App[None],
) -> None:
    # Given
    app = app_with_ok_only_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        yes_buttons = screen.query("#yes")
        assert len(yes_buttons) == 0


async def test_compose_with_ok_only_does_not_contain_no_button(
    app_with_ok_only_screen: App[None],
) -> None:
    # Given
    app = app_with_ok_only_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        no_buttons = screen.query("#no")
        assert len(no_buttons) == 0


async def test_compose_with_ok_only_does_not_contain_always_button(
    app_with_ok_only_screen: App[None],
) -> None:
    # Given
    app = app_with_ok_only_screen

    # When / Then
    async with app.run_test() as pilot:
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        always_buttons = screen.query("#always")
        assert len(always_buttons) == 0


# --- Tests for on_key ---


async def test_on_key_with_y_key_yes_no_dismisses_yes(
    app_with_yes_no_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_yes_no_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        screen.post_message(Key("y", "y"))
        await pilot.pause()

        mock_dismiss.assert_called_once_with(QuestionResponse.YES)


async def test_on_key_with_n_key_yes_no_dismisses_no(
    app_with_yes_no_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_yes_no_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        screen.post_message(Key("n", "n"))
        await pilot.pause()

        mock_dismiss.assert_called_once_with(QuestionResponse.NO)


async def test_on_key_with_uppercase_y_key_yes_no_dismisses_yes(
    app_with_yes_no_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_yes_no_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        screen.post_message(Key("Y", "Y"))
        await pilot.pause()

        mock_dismiss.assert_called_once_with(QuestionResponse.YES)


async def test_on_key_with_uppercase_n_key_yes_no_dismisses_no(
    app_with_yes_no_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_yes_no_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        screen.post_message(Key("N", "N"))
        await pilot.pause()

        mock_dismiss.assert_called_once_with(QuestionResponse.NO)


async def test_on_key_with_a_key_yes_no_does_not_dismiss(
    app_with_yes_no_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_yes_no_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        screen.post_message(Key("a", "a"))
        await pilot.pause()

        mock_dismiss.assert_not_called()


async def test_on_key_with_y_key_yes_no_always_dismisses_yes(
    app_with_yes_no_always_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_yes_no_always_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        screen.post_message(Key("y", "y"))
        await pilot.pause()

        mock_dismiss.assert_called_once_with(QuestionResponse.YES)


async def test_on_key_with_n_key_yes_no_always_dismisses_no(
    app_with_yes_no_always_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_yes_no_always_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        screen.post_message(Key("n", "n"))
        await pilot.pause()

        mock_dismiss.assert_called_once_with(QuestionResponse.NO)


async def test_on_key_with_a_key_yes_no_always_dismisses_always(
    app_with_yes_no_always_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_yes_no_always_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        screen.post_message(Key("a", "a"))
        await pilot.pause()

        mock_dismiss.assert_called_once_with(QuestionResponse.ALWAYS)


async def test_on_key_with_enter_key_ok_only_dismisses_ok(
    app_with_ok_only_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_ok_only_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        screen.post_message(Key("enter", "enter"))
        await pilot.pause()

        mock_dismiss.assert_called_once_with(QuestionResponse.OK)


async def test_on_key_with_space_key_ok_only_dismisses_ok(
    app_with_ok_only_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_ok_only_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        screen.post_message(Key("space", " "))
        await pilot.pause()

        mock_dismiss.assert_called_once_with(QuestionResponse.OK)


async def test_on_key_with_y_key_ok_only_does_not_dismiss(
    app_with_ok_only_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_ok_only_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        screen.post_message(Key("y", "y"))
        await pilot.pause()

        mock_dismiss.assert_not_called()


async def test_on_key_with_n_key_ok_only_does_not_dismiss(
    app_with_ok_only_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_ok_only_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        screen.post_message(Key("n", "n"))
        await pilot.pause()

        mock_dismiss.assert_not_called()


async def test_on_key_with_enter_key_yes_no_does_not_dismiss(
    app_with_yes_no_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_yes_no_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        screen.post_message(Key("enter", "enter"))
        await pilot.pause()

        mock_dismiss.assert_not_called()


async def test_on_key_with_unrelated_key_does_not_dismiss(
    app_with_yes_no_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_yes_no_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        screen.post_message(Key("x", "x"))
        await pilot.pause()

        mock_dismiss.assert_not_called()


# --- Tests for on_button_pressed ---


async def test_on_button_pressed_with_yes_button_dismisses_yes(
    app_with_yes_no_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_yes_no_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        yes_button = screen.query_one("#yes", Button)
        screen.post_message(Button.Pressed(yes_button))
        await pilot.pause()

        mock_dismiss.assert_called_once_with(QuestionResponse.YES)


async def test_on_button_pressed_with_no_button_dismisses_no(
    app_with_yes_no_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_yes_no_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        no_button = screen.query_one("#no", Button)
        screen.post_message(Button.Pressed(no_button))
        await pilot.pause()

        mock_dismiss.assert_called_once_with(QuestionResponse.NO)


async def test_on_button_pressed_with_always_button_dismisses_always(
    app_with_yes_no_always_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_yes_no_always_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        always_button = screen.query_one("#always", Button)
        screen.post_message(Button.Pressed(always_button))
        await pilot.pause()

        mock_dismiss.assert_called_once_with(QuestionResponse.ALWAYS)


async def test_on_button_pressed_with_ok_button_dismisses_ok(
    app_with_ok_only_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_ok_only_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        ok_button = screen.query_one("#ok", Button)
        screen.post_message(Button.Pressed(ok_button))
        await pilot.pause()

        mock_dismiss.assert_called_once_with(QuestionResponse.OK)


async def test_on_button_pressed_with_unrecognized_button_does_not_dismiss(
    app_with_yes_no_screen: App[None],
    mocker,
) -> None:
    # Given
    app = app_with_yes_no_screen
    mock_dismiss = mocker.patch.object(QuestionScreen, "dismiss", return_value=None)

    # When / Then
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, QuestionScreen)
        await pilot.pause()

        fake_button = Button("Fake", id="fake")
        screen.post_message(Button.Pressed(fake_button))
        await pilot.pause()

        mock_dismiss.assert_not_called()
