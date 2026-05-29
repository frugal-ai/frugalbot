from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown


class HelpScreen(ModalScreen[None]):
    """A modal dialog for displaying help information."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }

    #dialog {
        width: 80%;
        height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 1;
    }

    #content {
        height: 1fr;
        margin-bottom: 1;
        overflow-y: scroll;
    }

    #button-group {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #button-group Button {
        width: 16;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "app.pop_screen", "Close"),
        ("pagedown", "scroll_text_page_down"),
        ("pageup", "scroll_text_page_up"),
        ("down", "scroll_text_page_down"),
        ("up", "scroll_text_page_up"),
        ("home", "scroll_text_home"),
        ("end", "scroll_text_end"),
    ]

    def __init__(self, content: str) -> None:
        super().__init__()
        self.content = content

    def action_scroll_text_page_up(self) -> None:
        self.help_text_widget.scroll_page_up()

    def action_scroll_text_page_down(self) -> None:
        self.help_text_widget.scroll_page_down()

    def action_scroll_text_home(self) -> None:
        self.help_text_widget.scroll_home()

    def action_scroll_text_end(self) -> None:
        self.help_text_widget.scroll_end()

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Markdown(self.content, id="content")
            with Vertical(id="button-group"):
                yield Button("Close", variant="primary", id="close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss()

    def on_mount(self) -> None:
        self.help_text_widget = self.query_one("#content", Markdown)
