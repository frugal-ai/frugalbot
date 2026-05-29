from frugalbot.events import BulkMessageEvent, MessageEvent, MessageType, QuestionResponse, StatusUpdateEvent, UserChoiceInteractionEvent, UserCompositeInteractionEvent, UserTextInteractionEvent, bus
from frugalbot.ui.screens.question import QuestionScreen
from frugalbot.ui.screens.text_prompt import TextPromptScreen
from frugalbot.ui.tui import tui


async def _handle_message(event: MessageEvent, batch: bool = False):
    if not hasattr(tui, "output"):
        return

    prefix = "[bold gray]FRUGALBOT[/]"
    style = None
    match event.message_type:
        case MessageType.INFO:
            prefix = "[bold green]INFO[/]"
        case MessageType.WARNING:
            prefix = "[bold yellow]WARNING[/]"
        case MessageType.ERROR:
            prefix = "[bold red]ERROR[/]"
        case MessageType.USER:
            prefix = "[bold rgb(215,95,0)]USER[/]"
        case MessageType.ASSISTANT:
            prefix = "[bold cyan]ASSISTANT[/]"
        case MessageType.THINKING:
            prefix = "[bold magenta]ASSISTANT THINKING[/]"
            style = "dim"
        case MessageType.TOOL_CALL:
            prefix = "[bold rgb(135,175,255)]TOOL CALL[/]"
        case MessageType.TOOL_OUTPUT:
            prefix = "[bold rgb(215,135,215)]TOOL[/]"
        case MessageType.SYSTEM:
            prefix = "[bold purple]SYSTEM[/]"

    if event.is_stream:
        if not tui.md_stream:
            tui.start_streaming_block(prefix, style, event.message)
            tui.stream_type = event.message_type
        elif tui.stream_type != event.message_type:
            await tui.md_stream.stop()
            tui.append_rule()
            tui.start_streaming_block(prefix, style, event.message)
            tui.stream_type = event.message_type
        else:
            await tui.append_to_streaming_block(event.message)
    else:
        if tui.md_stream:
            await tui.md_stream.stop()
            tui.append_rule(batch=True)
            tui.md_stream = None
        tui.append_block(prefix, style, event.message, event.message_markup, batch=True)
        tui.append_rule(batch=batch)
        if event.message_type == MessageType.USER and not batch:
            tui.call_after_refresh(lambda: tui.output.scroll_end(animate=False))


@bus.subscribe(MessageEvent)
async def handle_message(event: MessageEvent):
    await _handle_message(event)


@bus.subscribe(BulkMessageEvent)
async def handle_bulk_message(event: BulkMessageEvent):
    for msg_index, msg in enumerate(event.messages):
        batch = msg_index != len(event.messages) - 1
        await _handle_message(msg, batch=batch)


@bus.subscribe(UserChoiceInteractionEvent)
async def handle_user_choice_interation(event: UserChoiceInteractionEvent):
    event.future.set_result(await tui.push_screen_wait(QuestionScreen(event.prompt, event.question_type)))


@bus.subscribe(UserTextInteractionEvent)
async def handle_user_text_interaction(event: UserTextInteractionEvent):
    event.future.set_result(await tui.push_screen_wait(TextPromptScreen(event.prompt)))


@bus.subscribe(UserCompositeInteractionEvent)
async def handle_user_composite_interaction(event: UserCompositeInteractionEvent):
    response = await tui.push_screen_wait(QuestionScreen(event.prompt, event.question_type))
    text_input = ""
    if response == QuestionResponse.YES:
        text_input = await tui.push_screen_wait(TextPromptScreen(event.follow_up_prompt))
    event.future.set_result((response, text_input))


@bus.subscribe(StatusUpdateEvent)
def handle_status_update(event: StatusUpdateEvent):
    if hasattr(tui, "status"):
        context_size_str = f"{event.context_size:,d}" if event.context_size else "?"
        percent_usage_str = f" = {event.total_tokens / event.context_size * 100:.1f}%" if event.context_size else ""
        tui.status.update(f"{event.agent_name} - {event.provider}/{event.model_id} ({event.thinking_level.lower()}) - {event.total_tokens:,d} / {context_size_str}{percent_usage_str} - {event.cost:.2f}$")
