from datetime import datetime
from pathlib import Path
from typing import cast

import orjson as json
from any_llm.types.completion import ChatCompletionMessage, ChatCompletionMessageFunctionToolCall

from frugalbot.clients.base import LLMClients
from frugalbot.config import AgentConfig, GeneralConfig, ThinkingLevel
from frugalbot.conversation import Conversation
from frugalbot.events import (
    BulkMessageEvent,
    MessageEvent,
    MessageMarkup,
    MessageType,
    StatusUpdateEvent,
    bus,
)
from frugalbot.hooks.base import AgentFinishedHook, AgentStopHook, Hooks
from frugalbot.skills import Skills
from frugalbot.tool_caller import ToolCaller
from frugalbot.tools.base import Tools
from frugalbot.utils.cost import ConversationCostCalculator
from frugalbot.utils.json import json_to_readable_yaml
from frugalbot.utils.models_dev import ModelsDevClient
from frugalbot.utils.openrouter import OpenRouterClient
from frugalbot.utils.prompts import render_system_prompt, render_user_prompt

_SESSIONS_BASE_PATH = Path.home() / ".frugalbot/sessions"
_SESSION_FILE_NAME_DATETIME_FORMAT = "%Y-%m-%d_%H-%M-%S"


def _get_unique_conversation_file_path() -> Path:
    stem = datetime.now().strftime(_SESSION_FILE_NAME_DATETIME_FORMAT)
    conversation_file_path = _SESSIONS_BASE_PATH / f"{stem}.json"
    suffix_index = 2
    while conversation_file_path.exists():
        conversation_file_path = _SESSIONS_BASE_PATH / f"{stem}-{suffix_index}.json"
        suffix_index += 1
    return conversation_file_path


class Agent:
    def __init__(self, name: str, general_config: GeneralConfig, agent_config: AgentConfig, clients: LLMClients, tools: Tools, hooks: Hooks, skills: Skills):
        self.name = name
        self.general_config = general_config
        self.config = agent_config
        self.clients = sorted([client for client in clients.get_all() if client.name in agent_config.clients], key=lambda c: agent_config.clients.index(c.name))
        if not self.clients:
            raise ValueError(f"Agent '{name}' has no matching clients configured.")
        self.tools = tools
        self.hooks = hooks
        self.skills = skills
        self.conversation_file_path = None

        self.client_index = 0
        self.client = self.clients[self.client_index]
        self.models_dev_client = ModelsDevClient()
        self.openrouter_client = OpenRouterClient()
        self.conversation = Conversation(self.hooks)
        self._initialized = False

    async def set_thinking_level(self, level: ThinkingLevel, emit_status_update: bool = False) -> None:
        for c in self.clients:
            c.thinking_level = level
        if emit_status_update:
            await self._emit_status_update()

    async def next_client(self) -> None:
        if not self.clients:
            raise ValueError("No clients configured")
        self.client_index = (self.client_index + 1) % len(self.clients)
        self.client = self.clients[self.client_index]
        await self._emit_status_update()

    async def new_conversation(self) -> None:
        self.conversation = Conversation(self.hooks)
        self.conversation_file_path = _get_unique_conversation_file_path()
        sys_msg = await render_system_prompt(self.general_config, self.tools, self.skills, self.hooks, self.config.prompts.system_prompt)
        await bus.emit_and_handle(
            MessageEvent(f"Tools schema:\n```json\n{json.dumps([tool.get_schema() for tool in self.tools.get_all()], option=json.OPT_INDENT_2).decode('utf-8')}\n```", MessageType.SYSTEM, MessageMarkup.MARKDOWN)
        )
        await self.conversation.append_system_message(sys_msg)
        await self._emit_status_update()
        self._initialized = True

    async def load_conversation_from_file(self, conversation_file_path: Path) -> None:
        self.conversation = Conversation(self.hooks)
        self.conversation_file_path = conversation_file_path

        try:
            await self.conversation.load_from_file(conversation_file_path)
        except Exception as e:
            await bus.emit_and_handle(MessageEvent(f"Error loading session file {conversation_file_path}: {e}. Creating new conversation.", MessageType.WARNING))
            await self.new_conversation()
            return

        bulk_message_event = BulkMessageEvent()
        for msg in self.conversation.messages:
            if isinstance(msg, dict):
                role = msg.get("role", "unknown")
                content = msg.get("content") or ""
                if role == "user":
                    bulk_message_event.messages.append(MessageEvent(content, MessageType.USER))
                elif role == "system":
                    bulk_message_event.messages.append(MessageEvent(content, MessageType.SYSTEM))
                elif role == "tool":
                    tool_name = msg.get("name", "unknown")
                    bulk_message_event.messages.append(
                        MessageEvent(
                            f"tool_name: {tool_name}\n{content}" if not content.lstrip().startswith("{") else f"tool_name: {tool_name}\n{json_to_readable_yaml(content)}\n",
                            MessageType.TOOL_OUTPUT,
                            MessageMarkup.YAML,
                        )
                    )
                else:
                    raise ValueError(f"Unsupported message role: {role}")
            elif isinstance(msg, ChatCompletionMessage):
                if msg.reasoning and msg.reasoning.content:
                    bulk_message_event.messages.append(MessageEvent(msg.reasoning.content, MessageType.THINKING, MessageMarkup.MARKDOWN))
                if msg.content:
                    bulk_message_event.messages.append(MessageEvent(msg.content, MessageType.ASSISTANT, MessageMarkup.MARKDOWN))
                if msg.tool_calls:
                    for untyped_tool_call in msg.tool_calls:
                        tool_call = cast(ChatCompletionMessageFunctionToolCall, untyped_tool_call)
                        bulk_message_event.messages.append(
                            MessageEvent(
                                f"tool_name: {tool_call.function.name}\n{json_to_readable_yaml(tool_call.function.arguments)}\n",
                                MessageType.TOOL_CALL,
                                MessageMarkup.YAML,
                            )
                        )
            else:
                raise ValueError(f"Unsupported message type: {type(msg)}")
        await bus.emit_and_handle(bulk_message_event)
        await self._emit_status_update()
        self._initialized = True

    async def _handle_tool_calls(self, assistant_message: ChatCompletionMessage) -> None:
        """Process and execute tool calls from the assistant."""
        if not assistant_message.tool_calls:
            return
        for untyped_tool_call in assistant_message.tool_calls:
            tool_caller = ToolCaller(self.conversation, self.hooks, self.tools, cast(ChatCompletionMessageFunctionToolCall, untyped_tool_call), self.general_config.tool_output_format)
            await tool_caller.call()

    async def _emit_status_update(self) -> None:
        calculator = ConversationCostCalculator(self.models_dev_client, self.openrouter_client)
        cost = await calculator.calculate_total_cost(self.conversation.serialize_to_dict()["messages"])
        context_size = None
        provider = None
        if self.client.provider == "openrouter":
            try:
                openrouter_model = await self.openrouter_client.get_model(self.client.model)
            except Exception:
                openrouter_model = None
            context_size = openrouter_model.context_length if openrouter_model and openrouter_model.context_length else None
        else:
            try:
                provider_obj = await self.models_dev_client.get_provider_by_url(self.client.base_url)
                provider = provider_obj.name if provider_obj else None
                model = await self.models_dev_client.get_model(self.client.provider, self.client.model)
            except Exception:
                model = None
            context_size = model.limit.context if model else None
        if not provider:
            provider = self.client.provider
        await bus.emit_and_handle(StatusUpdateEvent(self.name, provider.lower(), self.client.model, self.client.thinking_level, self.conversation.get_usage().total_tokens, context_size, cost))

    async def _run(self) -> None:
        try:
            while True:
                completion = await self.client.call(self.conversation, self.tools)
                if len(completion.choices) == 0:
                    error_msg = "LLM returned an empty completion.choices. Aborting run to prevent infinite loop."
                    await bus.emit_and_handle(MessageEvent(error_msg, MessageType.ERROR))
                    raise RuntimeError(error_msg)

                assistant_message = completion.choices[0].message
                if not assistant_message:
                    error_msg = "LLM returned an empty completion message. Aborting run to prevent infinite loop."
                    await bus.emit_and_handle(MessageEvent(error_msg, MessageType.ERROR))
                    raise RuntimeError(error_msg)

                self.conversation.append_assistant_message(self.client.provider, completion)
                await self._emit_status_update()

                if assistant_message.tool_calls:
                    await self._handle_tool_calls(assistant_message)
                else:
                    hook_data = AgentStopHook(self.conversation)
                    await self.hooks.run(hook_data)
                    if not hook_data.continue_conversation:
                        break
        finally:
            if self.conversation_file_path:
                await self.conversation.serialize_to_file(self.conversation_file_path)

    async def run(self, user_prompt: str | None) -> None:
        if not self._initialized:
            await self.new_conversation()
        if user_prompt is not None:
            rendered_user_prompt = await render_user_prompt(self.config, self.hooks, user_prompt)
            await self.conversation.append_user_message(rendered_user_prompt)
        while True:
            await self._run()
            hook_data = AgentFinishedHook(self)
            await self.hooks.run(hook_data)
            if not hook_data.run_again:
                break
