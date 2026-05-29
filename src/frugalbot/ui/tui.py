import functools
import inspect
import io
import shlex
import threading
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import ClassVar

import click
import rapidfuzz
import typer
from rich.syntax import Syntax
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalScroll
from textual.widget import Widget
from textual.widgets import Label, Markdown, OptionList, Rule, Static, TextArea
from textual.widgets._markdown import MarkdownFence
from textual.widgets.markdown import MarkdownStream
from textual.widgets.option_list import Option
from textual.worker import Worker, WorkerState, get_current_worker

from frugalbot.agents import Agents
from frugalbot.events import (
    MessageMarkup,
    MessageType,
)
from frugalbot.ui.autocomplete_mode import AutocompleteMode
from frugalbot.ui.commands.base import tui_typer
from frugalbot.ui.history import read_history, write_history
from frugalbot.ui.widgets.user_message_text_area import UserMessageTextArea
from frugalbot.utils.filesystem import list_files_with_cache
from frugalbot.utils.loader import load_dynamic_modules, load_or_reload_module
from frugalbot.utils.textual import get_word_at_cursor_location
from frugalbot.utils.typer import get_command_from_name


def _penalize_hidden_folders(query, choice, **kwargs) -> float:
    score = rapidfuzz.fuzz.WRatio(query, choice, **kwargs)
    if choice.startswith("."):
        score -= 20
    return max(0.0, score)


def catch_unhandled_exceptions(func):
    is_async = inspect.iscoroutinefunction(func)
    if is_async:

        @functools.wraps(func)
        async def async_wrapper(self: Tui, *args, **kwargs):
            try:
                # Custom logic using 'self'
                self.log(f"Calling async {func.__name__}")
                return await func(self, *args, **kwargs)
            except Exception as e:
                self._output_unhandled_exception(e)

        return async_wrapper
    else:

        @functools.wraps(func)
        def sync_wrapper(self: Tui, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                self._output_unhandled_exception(e)

        return sync_wrapper


MarkdownFence.DEFAULT_CSS.replace("width: 1fr;", "width: 100%;")
MarkdownFence.DEFAULT_CSS += """
    MarkdownFence > #code-content {
        width: 100%;
        height: auto;
        text-wrap: wrap;
    }
    """


class Tui(App):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("alt+enter", "submit", "Submit"),
        Binding("alt+u,alt+up", "scroll_output_up", "Scroll Output Up", priority=True),
        Binding("alt+d,alt+down", "scroll_output_down", "Scroll Output Down", priority=True),
        Binding("alt+h,alt+home", "scroll_output_home", "Scroll Output Home", priority=True),
        Binding("alt+e,alt+end", "scroll_output_end", "Scroll Output End", priority=True),
        Binding("alt+s", "toggle_auto_scroll", "Enable / Disable Auto-Scrolling", priority=True),
        Binding("ctrl+r", "search_history", "Search History"),
        Binding("ctrl+a", "cancel_agent", "Cancel Agent"),
        Binding("ctrl+n", "cycle_agent", "Cycle Between Configured Agents"),
        Binding("alt+p,ctrl+p", "cycle_model", "Cycle Between Configured Providers / Models", priority=True),
    ]

    CSS = """
    #bottom-bar {
        height: 1;
    }
    #working-indicator {
        width: 24;
        color: yellow;
    }
    #status {
        content-align: right middle;
        width: 1fr;
    }
    MarkdownH1 {
        content-align: left middle;
        text-style: bold underline;
    }
    """

    def __init__(self, *args, **kwargs):
        self.initialized = False
        self.one_shot_mode = False
        self.startup_prompt: str | None = None
        self._autocomplete_mode = AutocompleteMode.NONE
        super().__init__(*args, **kwargs)

    @property
    def autocomplete_mode(self) -> AutocompleteMode:
        return self._autocomplete_mode

    @autocomplete_mode.setter
    def autocomplete_mode(self, mode: AutocompleteMode) -> None:
        if self._autocomplete_mode == mode:
            return

        self._autocomplete_mode = mode

        if mode == AutocompleteMode.FILE_PATH:
            self.dropdown.styles.text_wrap = "nowrap"
            self.dropdown.styles.text_overflow = "ellipsis"
            self.dropdown.styles.overflow_x = "hidden"
            self.dropdown.styles.display = "block"
            self.dropdown.highlighted = 0
        elif mode == AutocompleteMode.NONE:
            self.dropdown.styles.display = "none"
        elif mode == AutocompleteMode.COMMAND:
            self.dropdown.styles.text_wrap = "nowrap"
            self.dropdown.styles.text_overflow = "ellipsis"
            self.dropdown.styles.overflow_x = "hidden"
            self.dropdown.styles.display = "block"
            self.dropdown.highlighted = 0
        elif mode == AutocompleteMode.HISTORY:
            self.dropdown.styles.text_wrap = "wrap"
            self.dropdown.styles.text_overflow = "fold"
            self.dropdown.styles.overflow_x = "auto"
            self.dropdown.styles.display = "block"
            self.dropdown.highlighted = 0

        if mode != AutocompleteMode.FILE_PATH:
            self.autocomplete_path_debounce_timer.stop()

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="output")
        yield OptionList(id="dropdown")
        yield UserMessageTextArea(id="user-input", show_line_numbers=False, placeholder="Type / for commands or type your message then submit with ALT+ENTER...")
        with Horizontal(id="bottom-bar"):
            yield Static("", id="working-indicator")
            yield Static("", id="status")

    @catch_unhandled_exceptions
    def execute_command(self, user_input: str) -> None:
        output_buffer = io.StringIO()
        clean_input = user_input.removeprefix("/")
        try:
            args = shlex.split(clean_input)
        except ValueError:
            # If shlex fails, fallback to splitting only the command name
            # and treating the rest as one big string.
            args = clean_input.split(maxsplit=1)
            command = get_command_from_name(tui_typer, args[0])
            if command is None or len(command.params) != 1 or command.params[0].nargs != -1:
                raise
        with redirect_stdout(output_buffer), redirect_stderr(output_buffer):
            try:
                tui_typer(args, standalone_mode=False, obj={"app": self})
            except Exception as e:
                ctx: click.Context | None = getattr(e, "ctx", None)
                if ctx is not None and ctx.command.name is not None:
                    help_str = ctx.get_help()
                    prefix_end_index = help_str.find(": ") + 2
                    command_index = help_str.find(ctx.command.name, prefix_end_index)
                    print(f"{e!s}\n\n{help_str[:prefix_end_index]}/{help_str[command_index:]}")
                else:
                    print(f"{e!s}")

        output = output_buffer.getvalue()
        if output:
            self.append_block("[bold red]COMMAND ERROR[/]", None, output, MessageMarkup.NONE)

    def action_toggle_auto_scroll(self) -> None:
        self.is_auto_scroll_enabled = not self.is_auto_scroll_enabled

    def action_scroll_output_up(self) -> None:
        self.output.scroll_page_up()

    def action_scroll_output_down(self) -> None:
        self.output.scroll_page_down()

    def action_scroll_output_home(self) -> None:
        self.output.scroll_home()

    def action_scroll_output_end(self) -> None:
        self.output.scroll_end()

    def _is_agent_running(self) -> bool:
        if self.agent_worker and self.agent_worker.state in (WorkerState.RUNNING, WorkerState.PENDING):
            return True
        return False

    def launch_agent(self, prompt: str | None):
        self.agent_worker = self.run_worker(self.agent.run(prompt), name="agent")

    async def action_submit(self) -> None:
        user_prompt = self.input.text.strip()
        self.dropdown.styles.display = "none"

        if user_prompt.startswith("/"):
            self.input.load_text("")
            self.execute_command(user_prompt)
        else:
            if not self._is_agent_running():
                self.input.load_text("")
                self.history.append(user_prompt)
                self.launch_agent(user_prompt)
                await write_history(self.history)
            else:
                self.notify("Agent is running. Wait for it to finish or cancel with ctrl+a")

    def action_cancel_agent(self) -> None:
        if self.agent_worker is not None and self._is_agent_running():
            self.agent_worker.cancel()
            self.notify("Agent operation cancelled")

    async def action_search_history(self) -> None:
        if not self.history:
            self.notify("No command in history")
            return
        self.autocomplete_mode = AutocompleteMode.HISTORY
        await self.on_text_area_changed(TextArea.Changed(self.input))

    async def action_cycle_model(self) -> None:
        if self.agent:
            await self.agent.next_client()

    async def action_cycle_agent(self) -> None:
        if self._is_agent_running():
            self.notify("Cannot switch agent while it's running. Wait for it to finish or use ctrl+a to stop agent.")
            return
        self.agent = self.agents.next(self.agent.name)
        await self.agent.new_conversation()

    @on(TextArea.SelectionChanged)
    @catch_unhandled_exceptions
    async def on_text_area_cursor_moved(self, event: TextArea.SelectionChanged) -> None:
        if event.text_area is not self.input:
            return
        if self.autocomplete_mode not in (AutocompleteMode.FILE_PATH, AutocompleteMode.NONE):
            return
        word = get_word_at_cursor_location(event.text_area)
        if word.startswith("@"):
            self.autocomplete_mode = AutocompleteMode.FILE_PATH
            self.autocomplete_path_debounce_timer.stop()
            self.autocomplete_path_debounce_timer = self.set_timer(0.2, functools.partial(self.update_file_autocomplete, word[1:]))
        else:
            self.autocomplete_mode = AutocompleteMode.NONE

    @catch_unhandled_exceptions
    async def on_text_area_changed(self, event: TextArea.Changed) -> None:
        word = get_word_at_cursor_location(event.text_area)
        if self.autocomplete_mode == AutocompleteMode.HISTORY:
            query = event.text_area.text.lower()
            matches = [entry for entry in self.history if query in entry.lower()]
            options = [Option(entry, id=str(idx)) for idx, entry in enumerate(reversed(matches))]
            self._update_dropdown_options(options)
        elif word.startswith("@"):
            pass  # handled in on_text_area_cursor_moved
        elif event.text_area.text.startswith("/") and word.startswith("/"):
            self.autocomplete_mode = AutocompleteMode.COMMAND
            options = []
            for command_info in tui_typer.registered_commands:
                if command_info.name is None:
                    continue
                full_command_name = f"/{command_info.name}"
                if full_command_name.startswith(event.text_area.text):
                    command = typer.main.get_command_from_info(command_info, pretty_exceptions_short=True, rich_markup_mode=None)
                    help_text = command.short_help or command.help
                    if help_text:
                        lf_index = help_text.find("\n")
                        help_text = help_text if lf_index < 0 else help_text[:lf_index]
                    else:
                        help_text = "No description available"
                    options.append(Option(f"{full_command_name} - {help_text}", id=full_command_name))
                    options.sort(key=lambda o: o.id)
            self._update_dropdown_options(options)
        else:
            self.autocomplete_mode = AutocompleteMode.NONE

    def update_file_autocomplete(self, query: str) -> None:
        with self.autocomplete_path_query_lock:
            self.autocomplete_path_query = query
            self.autocomplete_path_query_event.set()

    @work(thread=True, name="autocomplete_path", group="autocomplete")
    def _autocomplete_worker_loop(self) -> None:
        while True:
            try:
                self.autocomplete_path_query_event.wait()
                if get_current_worker().is_cancelled:
                    break
                with self.autocomplete_path_query_lock:
                    self.autocomplete_path_query_event.clear()
                    query = self.autocomplete_path_query
                file_paths = [p.as_posix() for p in list_files_with_cache(Path.cwd())]
                matches = rapidfuzz.process.extract(query, file_paths, scorer=_penalize_hidden_folders, limit=10)
                options = [Option(entry[0], id=entry[0]) for entry in matches]
                if self.autocomplete_path_query_event.is_set():
                    continue
                self.call_from_thread(self._update_dropdown_options, options)
            except Exception as e:
                self._output_unhandled_exception(e)
                break

    def _update_dropdown_options(self, options: list[Option]) -> None:
        if self.dropdown.styles.display == "block" and options:
            self.dropdown.set_options(options)
            if self.dropdown.highlighted is None:
                self.dropdown.highlighted = 0

    def _output_unhandled_exception(self, exception: BaseException):
        tb_lines = traceback.format_exception(type(exception), exception, exception.__traceback__)
        tb_text = "".join(tb_lines)
        error_msg = str(exception)
        if threading.current_thread() is threading.main_thread():
            self.append_block("[bold red]UNEXPECTED ERROR[/]", None, f"{error_msg}\n\n{tb_text}", MessageMarkup.NONE)
        else:
            self.call_from_thread(self.append_block, "[bold red]UNEXPECTED ERROR[/]", None, f"{error_msg}\n\n{tb_text}", MessageMarkup.NONE)

    async def on_mount(self) -> None:
        if not self.initialized:
            raise RuntimeError("Must call Tui.init() before Tui.run()")
        self.output = self.query_one("#output", VerticalScroll)
        self.input = self.query_one("#user-input", TextArea)
        self.dropdown = self.query_one("#dropdown", OptionList)
        self.status = self.query_one("#status", Static)
        self.working_indicator = self.query_one("#working-indicator", Static)

        self.output.styles.height = "1fr"
        self.output.styles.border = ("none", "transparent")
        self.output.styles.background = self.input.styles.background
        self.output.styles.background_tint = self.input.styles.background_tint
        self.output.can_focus = False

        self.dropdown.styles.border = ("round", "gray")
        self.dropdown.styles.display = "none"
        self.dropdown.styles.height = 8
        self.dropdown.styles.padding = 0
        self.dropdown.styles.margin = 0
        self.dropdown.can_focus = False

        self.status.styles.color = "#333"

        self.input.styles.height = 5
        self.input.styles.border = ("round", "gray")
        self.input.focus()

        self.autocomplete_mode = AutocompleteMode.NONE
        self.md_stream: MarkdownStream | None = None
        self.stream_type: MessageType = MessageType.INFO
        self.agent_worker: Worker | None = None
        self.autocomplete_path_query_event = threading.Event()
        self.autocomplete_path_query_lock = threading.Lock()  # Protects autocomplete_path_query
        self.autocomplete_path_query = ""
        self.autocomplete_path_worker = self._autocomplete_worker_loop()
        self.is_auto_scroll_enabled = True
        self.widget_batch: list[Widget] = []
        self.history = await read_history()
        self.autocomplete_path_debounce_timer = self.set_timer(0.2, functools.partial(self.update_file_autocomplete, ""), pause=True)

        # Spinner setup
        self.spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_index = 0
        self.spinner_start_time: float = 0.0
        self.spinner_timer = self.set_interval(0.1, self.update_spinner, pause=True)

    @catch_unhandled_exceptions
    async def on_ready(self):
        if self.initial_session_file:
            await self.agent.load_conversation_from_file(self.initial_session_file)
        else:
            await self.agent.new_conversation()
        if self.startup_prompt:
            self.input.load_text(self.startup_prompt)
            await self.action_submit()

    def get_elapsed_work_time_str(self) -> str:
        elapsed = time.time() - self.spinner_start_time
        minutes, seconds = divmod(int(elapsed), 60)
        return f"{minutes}m{seconds:02d}s" if minutes > 0 else f"{seconds}s"

    async def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.name == "agent":
            if event.state in (WorkerState.RUNNING, WorkerState.PENDING):
                self.spinner_index = 0
                self.spinner_start_time = time.time()
                self.working_indicator.update(f"{self.spinner_frames[0]} Working... 0s")
                self.spinner_timer.resume()
            elif event.state in (WorkerState.SUCCESS, WorkerState.ERROR, WorkerState.CANCELLED):
                self.spinner_timer.pause()
                self.working_indicator.update(f"Worked for {self.get_elapsed_work_time_str()}")
                if self.one_shot_mode:
                    self.input.load_text("/quit")
                    await self.action_submit()

    def update_spinner(self) -> None:
        self.spinner_index = (self.spinner_index + 1) % len(self.spinner_frames)
        self.working_indicator.update(f"{self.spinner_frames[self.spinner_index]} Working... {self.get_elapsed_work_time_str()}")

    def commit_batch_append(self) -> None:
        with self.batch_update():
            self.output.mount_all(self.widget_batch)
        self.widget_batch.clear()
        if self.is_auto_scroll_enabled:
            self.call_after_refresh(lambda: self.output.scroll_end(animate=False))

    def append_rule(self, batch: bool = False):
        rule = Rule()
        rule.styles.padding = (0, 0)
        rule.styles.margin = (0, 0)
        rule.styles.color = "#5f5f5f"
        if batch:
            self.widget_batch.append(rule)
        else:
            if self.widget_batch:
                self.widget_batch.append(rule)
                self.commit_batch_append()
            else:
                self.output.mount(rule)
            if self.is_auto_scroll_enabled:
                self.call_after_refresh(lambda: self.output.scroll_end(animate=False))

    def append_block(self, title: str, style: str | None, contents, markup: MessageMarkup, batch: bool = False):
        label = Label(title)
        label.styles.padding = (0, 0)
        label.styles.margin = (0, 0, 1, 0)
        label.styles.text_style = "underline"
        if batch or self.widget_batch:
            self.widget_batch.append(label)
        else:
            self.output.mount(label)
        if markup == MessageMarkup.MARKDOWN:
            block = Markdown(contents)
            block.styles.text_overflow = "fold"
            if style:
                block.styles.text_style = style
        elif markup == MessageMarkup.YAML or markup == MessageMarkup.JSON:
            rich_syntax = Syntax(contents, "yaml" if markup == MessageMarkup.YAML else "json", word_wrap=True)
            block = Static(rich_syntax)
        else:
            block = Static(contents, markup=False)
        block.styles.padding = (0, 0)
        block.styles.margin = (0, 0)
        if batch:
            self.widget_batch.append(block)
        else:
            if self.widget_batch:
                self.widget_batch.append(block)
                self.commit_batch_append()
            else:
                self.output.mount(block)
            if self.is_auto_scroll_enabled:
                self.call_after_refresh(lambda: self.output.scroll_end(animate=False))

    async def append_to_streaming_block(self, contents: str):
        if self.md_stream:
            await self.md_stream.write(contents)
            if self.is_auto_scroll_enabled:
                self.call_after_refresh(lambda: self.output.scroll_end(animate=False))

    def start_streaming_block(self, label, style: str | None, contents: str):
        if self.widget_batch:
            self.commit_batch_append()
        label = Label(label)
        label.styles.padding = (0, 0)
        label.styles.margin = (0, 0, 1, 0)
        label.styles.text_style = "underline"
        self.output.mount(label)
        block = Markdown(contents)
        if style:
            block.styles.text_style = style
        block.styles.padding = (0, 0)
        block.styles.margin = (0, 0)
        self.md_stream = Markdown.get_stream(block)
        at_bottom = self.is_auto_scroll_enabled
        self.output.mount(block)
        if at_bottom:
            self.call_after_refresh(lambda: self.output.scroll_end(animate=False))

    def init(self, agents: Agents, session_file: Path | None = None, one_shot_mode: bool = False, startup_prompt: str | None = None):
        if self.initialized:
            return
        list_files_with_cache(Path.cwd())  # make sure we have a pre-populated cached entry
        self.agents = agents
        self.agent = self.agents.next()
        load_or_reload_module("frugalbot.ui.event_handlers")
        load_dynamic_modules("frugalbot.ui.commands", "command")
        if one_shot_mode and not startup_prompt:
            raise RuntimeError("Must provide a prompt in one-shot mode")
        self.initial_session_file = session_file
        self.one_shot_mode = one_shot_mode
        self.startup_prompt = startup_prompt
        self.initialized = True


tui = Tui()
