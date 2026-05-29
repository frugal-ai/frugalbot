from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual import events
from textual.binding import BindingType
from textual.containers import VerticalScroll
from textual.widgets import OptionList, TextArea

from frugalbot.ui.autocomplete_mode import AutocompleteMode
from frugalbot.ui.commands.base import tui_typer
from frugalbot.utils.textual import get_text_area_document, get_word_location_at_cursor_location
from frugalbot.utils.typer import get_command_from_name

if TYPE_CHECKING:
    from frugalbot.ui.tui import Tui


class UserMessageTextArea(TextArea):
    BINDINGS: ClassVar[list[BindingType]] = [("ctrl+a", "none")]

    def on_mount(self):
        self.dropdown = self.app.query_one("#dropdown", OptionList)
        self.output = self.app.query_one("#output", VerticalScroll)
        self.tui: Tui = self.app  # type: ignore
        return super().on_mount()

    def action_cursor_up(self, select: bool = False) -> None:
        if self.dropdown.styles.display == "block":
            self.dropdown.action_cursor_up()
        else:
            super().action_cursor_up(select)

    def action_cursor_down(self, select: bool = False) -> None:
        if self.dropdown.styles.display == "block":
            self.dropdown.action_cursor_down()
        else:
            super().action_cursor_down(select)

    def action_cursor_page_up(self) -> None:
        if self.dropdown.styles.display == "block":
            self.dropdown.action_page_up()
        else:
            super().action_cursor_page_up()

    def action_cursor_page_down(self) -> None:
        if self.dropdown.styles.display == "block":
            self.dropdown.action_page_down()
        else:
            super().action_cursor_page_down()

    async def _on_key(self, event: events.Key) -> None:
        if not self.dropdown.styles.display == "block":
            return
        if event.key == "enter" or event.key == "tab" or event.key == "alt+enter":
            if self.dropdown.styles.display != "none" and self.dropdown.highlighted is not None:
                event.prevent_default()
                option = self.dropdown.get_option_at_index(self.dropdown.highlighted)
                if option.id is None:
                    self.tui.notify("ERROR: Option ID is None")
                    return

                replace_all_text = False
                command = None
                if self.tui.autocomplete_mode == AutocompleteMode.HISTORY:
                    option_text = str(option.prompt)
                    replace_all_text = True
                elif self.tui.autocomplete_mode == AutocompleteMode.COMMAND:
                    command = get_command_from_name(tui_typer, option.id)
                    option_text = option.id if command and not command.params else f"{option.id} "
                    replace_all_text = True
                elif self.tui.autocomplete_mode == AutocompleteMode.FILE_PATH:
                    option_text = f"@{option.id}"
                else:
                    raise ValueError(f"Unsupported autocomplete type {self.tui.autocomplete_mode}")

                if replace_all_text:
                    self.load_text(option_text)
                    last_row_index = self.document.line_count - 1 if self.document.line_count else 0
                    self.move_cursor(location=(last_row_index, len(self.document.get_line(last_row_index))))
                else:
                    word_start_index, word_end_index = get_word_location_at_cursor_location(self)
                    self.load_text(f"{self.document.text[:word_start_index]}{option_text}{self.document.text[word_end_index:]}")
                    self.move_cursor(get_text_area_document(self).get_location_from_index(word_start_index + len(option_text)))

                submit_now = False
                if self.tui.autocomplete_mode == AutocompleteMode.COMMAND:
                    if command and not command.params and command.name and not command.name.startswith("skill:"):
                        submit_now = True

                self.tui.autocomplete_mode = AutocompleteMode.NONE

                if submit_now:
                    await self.tui.action_submit()
        elif event.key == "escape":
            self.tui.autocomplete_mode = AutocompleteMode.NONE
