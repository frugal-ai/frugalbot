from datetime import datetime

import orjson as json
import pyperclip
from any_llm.types.completion import ChatCompletion, ChatCompletionMessage, ChatCompletionMessageFunctionToolCall, Choice, Function
from openai.types.chat import ChatCompletionMessageToolCallUnion

from frugalbot.clients.base import LLMClient, LLMClientConfig
from frugalbot.conversation import Conversation
from frugalbot.events import (
    QuestionResponse,
    QuestionType,
    UserChoiceInteractionEvent,
    UserTextInteractionEvent,
    bus,
)
from frugalbot.tools.base import Tools


def parse_assistant_message(response: str) -> ChatCompletionMessage:
    tool_calls: list[ChatCompletionMessageToolCallUnion] = []
    lines = [line for line in response.splitlines() if line.strip()]
    if len(lines) > 1 and lines[1].lstrip()[0] == "{" and response.rstrip()[-1] == "}":
        tool_name = lines[0]
        args = "\n".join(lines[1:])
        tool_calls.append(ChatCompletionMessageFunctionToolCall(type="function", id="unused", function=Function(name=tool_name, arguments=args)))
        content = ""
    else:
        content = response
    return ChatCompletionMessage(role="assistant", content=content, tool_calls=tool_calls if tool_calls else None)


class ManualClientConfig(LLMClientConfig):
    pass


class ManualClient(LLMClient[ManualClientConfig]):
    def __init__(self, config: ManualClientConfig):
        super().__init__(config)
        self._initialized = False
        self.provider = "manual"
        self.model = "unknown"

    @property
    def base_url(self) -> str:
        return ""

    @property
    def supports_thinking(self) -> bool:
        return False

    async def _initialize_conversation(self, conversation: Conversation, tools: Tools):
        if len(conversation.messages) < 2:
            raise ValueError("Conversation must have at least 2 messages to initialize (system prompt + initial prompt)")
        system_message, initial_message = conversation.messages[0], conversation.messages[1]
        if not isinstance(system_message, dict) or not isinstance(initial_message, dict):
            raise ValueError("First two messages in conversation expected to be dicts")

        tools_schema_str = json.dumps([tool.get_schema()["function"] for tool in tools.get_all()], option=json.OPT_INDENT_2).decode("utf-8")
        event = UserChoiceInteractionEvent("Does the LLM chat UI support entering tools schema?", QuestionType.YES_NO)
        await bus.emit_and_handle(event)
        if event.future.result() == QuestionResponse.YES:
            pyperclip.copy(tools_schema_str)
            await bus.emit_and_handle(UserChoiceInteractionEvent("Tools schema copied to clipboard. Click OK once the tools schema has been pasted into the LLM chat UI.", QuestionType.OK_ONLY))

        include_system_prompt = True
        event = UserChoiceInteractionEvent("Does the LLM chat UI support entering a system prompt?", QuestionType.YES_NO)
        await bus.emit_and_handle(event)
        if event.future.result() == QuestionResponse.YES:
            include_system_prompt = False
            if system_message["content"] is None:
                raise ValueError("System prompt is None")
            pyperclip.copy(system_message["content"])
            await bus.emit_and_handle(UserChoiceInteractionEvent("System prompt copied to clipboard. Click OK once the system prompt has been pasted into the LLM chat UI.", QuestionType.OK_ONLY))

        initial_prompt = f"{system_message['content']}\n\n{initial_message['content']}" if include_system_prompt else initial_message["content"]
        if initial_prompt is None:
            raise ValueError("Initial prompt is None")
        pyperclip.copy(initial_prompt)
        await bus.emit_and_handle(UserChoiceInteractionEvent("Initial prompt copied to clipboard. Click OK once the initial prompt has been pasted into the LLM chat UI.", QuestionType.OK_ONLY))

    async def call(self, conversation: Conversation, tools: Tools, *args, **kwargs) -> ChatCompletion:
        if not self._initialized:
            await self._initialize_conversation(conversation, tools)
            self._initialized = True
        else:
            latest_message = conversation.messages[-1] if conversation.messages else None
            if isinstance(latest_message, dict):
                response = latest_message["content"]
                if response:
                    pyperclip.copy(response)
                    await bus.emit_and_handle(UserChoiceInteractionEvent("Tool response copied to clipboard. Click OK once the initial prompt has been pasted into the LLM chat UI.", QuestionType.OK_ONLY))
        while True:
            event = UserTextInteractionEvent("Please enter the assistant's response (cannot be empty):")
            await bus.emit_and_handle(event)
            if event.future.result().strip():
                break
        message = parse_assistant_message(event.future.result())
        return ChatCompletion(model="manual", choices=[Choice(index=0, message=message, finish_reason="stop")], id="none", object="chat.completion", created=int(datetime.now().timestamp()))
