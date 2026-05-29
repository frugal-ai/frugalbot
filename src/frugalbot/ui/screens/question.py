from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown

from frugalbot.events import (
    QuestionResponse,
    QuestionType,
)


class QuestionScreen(ModalScreen[QuestionResponse]):
    """A modal dialog for Yes/No questions."""

    DEFAULT_CSS = """
    QuestionScreen {
        align: center middle;
    }

    #dialog {
        width: 60;
        height: auto;
        background: $surface;
        border: round $primary;
        padding: 1 2;
    }

    #question {
        width: 100%;
        height: auto;
        max-height: 60vh;
        content-align: center middle;
        text-style: bold;
        margin-bottom: 1;
        text-overflow: fold;
        overflow: hidden scroll;
    }

    #button-group {
        align: center middle;
        width: 100%;
        height: auto;
    }

    #button-group Button {
        width: 16;
        margin: 0 1;
    }
    """

    def __init__(self, question: str, question_type: QuestionType):
        super().__init__()
        self.question = question
        self.question_type = question_type

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Markdown(self.question, id="question")
            with Horizontal(id="button-group"):
                if self.question_type == QuestionType.YES_NO or self.question_type == QuestionType.YES_NO_ALWAYS:
                    yield Button("(Y)es", variant="success", id="yes")
                    yield Button("(N)o", variant="error", id="no")
                    if self.question_type == QuestionType.YES_NO_ALWAYS:
                        yield Button("(A)lways", variant="primary", id="always")
                elif self.question_type == QuestionType.OK_ONLY:
                    yield Button("Ok", variant="primary", id="ok")

    def on_key(self, event: events.Key) -> None:
        key = event.key.lower()
        if key == "y" and self.question_type in (QuestionType.YES_NO, QuestionType.YES_NO_ALWAYS):
            self.dismiss(QuestionResponse.YES)
        elif key == "n" and self.question_type in (QuestionType.YES_NO, QuestionType.YES_NO_ALWAYS):
            self.dismiss(QuestionResponse.NO)
        elif key == "a" and self.question_type == QuestionType.YES_NO_ALWAYS:
            self.dismiss(QuestionResponse.ALWAYS)
        elif (key == "enter" or key == "space") and self.question_type == QuestionType.OK_ONLY:
            self.dismiss(QuestionResponse.OK)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            self.dismiss(QuestionResponse.YES)
        elif event.button.id == "no":
            self.dismiss(QuestionResponse.NO)
        elif event.button.id == "always":
            self.dismiss(QuestionResponse.ALWAYS)
        elif event.button.id == "ok":
            self.dismiss(QuestionResponse.OK)
