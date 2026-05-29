from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, TextArea


class TextPromptScreen(ModalScreen[str]):
    """A modal dialog for multiline text input."""

    DEFAULT_CSS = """
    TextPromptScreen {
        align: center middle;
    }

    #dialog {
        width: 80;
        height: 20;
        background: $surface;
        border: round $primary;
        padding: 1 2;
    }

    #prompt-label {
        width: 100%;
        text-style: bold;
        margin-bottom: 1;
    }

    #prompt-input {
        height: 1fr;
        margin-bottom: 1;
        border: tall $background;
    }

    #button-group {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #button-group Button {
        width: 16;
        margin: 0 1;
    }
    """

    def __init__(self, prompt: str):
        super().__init__()
        self.prompt = prompt

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.prompt, id="prompt-label")
            yield TextArea(id="prompt-input")
            with Horizontal(id="button-group"):
                yield Button("Submit", variant="primary", id="submit")
                yield Button("Cancel", variant="warning", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#prompt-input").focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "submit":
            text = self.query_one("#prompt-input", TextArea).text
            self.dismiss(text)
        else:
            self.dismiss("")
