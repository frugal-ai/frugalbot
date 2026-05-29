import asyncio
import os
from pathlib import Path
from typing import Any, Literal, cast

import aiofiles
import orjson as json
from any_llm.types.completion import ChatCompletion, ChatCompletionMessage, ChatCompletionMessageFunctionToolCall

from frugalbot.events import MessageEvent, MessageMarkup, MessageType, bus
from frugalbot.hooks.base import Hooks, PreSystemMessageHook, PreUserMessageHook
from frugalbot.token_usage import TokenUsage
from frugalbot.utils.json import json_to_readable_yaml


class Conversation:
    def __init__(self, hooks: Hooks):
        self.hooks = hooks
        self._messages: list[dict[str, Any] | tuple[str, ChatCompletion]] = []

    @property
    def messages(self) -> list[dict[str, Any] | ChatCompletionMessage]:
        return [m[1].choices[0].message if isinstance(m, tuple) else m for m in self._messages]

    @property
    def entries(self) -> list[dict[str, Any] | tuple[str, ChatCompletion]]:
        return self._messages

    def _append_message(self, role: str, content: str | None, tool_call_id: str | None = None, extra_content: dict[str, Any] | None = None, name: str | None = None) -> None:
        message: dict[str, Any] = {"role": role, "content": content}
        if tool_call_id:
            message["tool_call_id"] = tool_call_id
        if extra_content:
            message["extra_content"] = extra_content
        if name:
            message["name"] = name
        self._messages.append(message)

    async def append_system_message(self, content: str) -> None:
        if len(self._messages) > 0:
            raise ValueError("System message must be the first message in the conversation")
        hook_data = PreSystemMessageHook(content=content)
        await self.hooks.run(hook_data)
        self._append_message(role="system", content=hook_data.content)
        await bus.emit_and_handle(MessageEvent(hook_data.content, MessageType.SYSTEM, MessageMarkup.MARKDOWN))

    async def append_user_message(self, content: str) -> None:
        hook_data = PreUserMessageHook(content=content)
        await self.hooks.run(hook_data)
        self._append_message(role="user", content=hook_data.content)
        await bus.emit_and_handle(MessageEvent(hook_data.content, MessageType.USER))

    async def append_tool_message(self, name: str, content: str, content_format: Literal["text", "yaml", "json"], tool_call_id: str, extra_content: dict[str, Any] | None) -> None:
        self._append_message(role="tool", content=content, tool_call_id=tool_call_id, extra_content=extra_content, name=name)
        # displayed_content = content if content_format != "json" else json_to_readable_yaml(content)
        # markup = MessageMarkup.YAML if content_format != "text" else MessageMarkup.NONE
        # each tool outputs its own results, disable for now but centralize at some point
        # await bus.emit_and_handle(MessageEvent(f"tool_name: {name}\n{displayed_content}\n", MessageType.TOOL_OUTPUT, markup))

    def append_assistant_message(self, provider: str, completion: ChatCompletion) -> None:
        self._messages.append((provider, completion))

    def latest_assistant_message(self) -> ChatCompletionMessage:
        if not self._messages:
            raise ValueError("No assistant message found in conversation")
        for m in reversed(self._messages):
            if isinstance(m, tuple):
                return m[1].choices[0].message
        raise ValueError("No assistant message found in conversation")

    def get_usage(self) -> TokenUsage:
        """Calculate aggregated token usage from the conversation history."""
        token_usage = TokenUsage()
        last_chat_completion = None
        for provider_and_completion in reversed(self._messages):
            if isinstance(provider_and_completion, tuple):
                last_chat_completion = provider_and_completion[1]
                break
        if last_chat_completion and last_chat_completion.usage:
            token_usage.total_prompt_tokens = last_chat_completion.usage.prompt_tokens
            token_usage.total_tokens = last_chat_completion.usage.total_tokens
            details = last_chat_completion.usage.prompt_tokens_details
            token_usage.total_cached_tokens = details.cached_tokens if details and details.cached_tokens else 0
        return token_usage

    def serialize_to_dict(self) -> dict[str, Any]:
        serialized_messages = []
        for tuple_or_dict in self._messages:
            if isinstance(tuple_or_dict, tuple):
                completion = tuple_or_dict[1]
                serialized_message = {"type": "completion", "provider": tuple_or_dict[0], "data": completion.model_dump()}
                for choice_idx, choice in enumerate(completion.choices):
                    if not choice.message or not choice.message.tool_calls:
                        continue
                    for tool_call_idx, tool_call in enumerate(choice.message.tool_calls):
                        if hasattr(tool_call, "extra_content"):
                            serialized_message["data"]["choices"][choice_idx]["message"]["tool_calls"][tool_call_idx]["extra_content"] = tool_call.extra_content  # pyright: ignore[reportAttributeAccessIssue]
                serialized_messages.append(serialized_message)
            else:
                serialized_messages.append({"type": "message", "data": tuple_or_dict})
        return {"messages": serialized_messages}

    def serialize_to_string(self) -> str:
        return json.dumps(self.serialize_to_dict(), option=json.OPT_INDENT_2).decode("utf-8")

    async def serialize_to_file(self, file_path: Path) -> None:
        await asyncio.to_thread(os.makedirs, file_path.parent, exist_ok=True)
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(self.serialize_to_string())

    async def load_from_file(self, file_path: Path) -> None:
        async with aiofiles.open(file_path, "rb") as f:
            content = await f.read()
        data = json.loads(content)
        serialized_messages = data.get("messages", [])

        for item in serialized_messages:
            if item["type"] == "completion":
                # Pydantic's model_validate is synchronous as of V2/V3
                # unless you have custom async validators.
                provider = item.get("provider", "unknown")
                validated_data = ChatCompletion.model_validate(item["data"])
                self._messages.append((provider, validated_data))

            elif item["type"] == "message":
                self._messages.append(item["data"])

            else:
                raise ValueError(f"Unknown message type '{item['type']}' in conversation file")

    def convert_into_web_chat_prompt(self) -> str:
        prompt_parts = []
        for message in self.messages:
            reasoning_content = ""
            tool_calls = []
            if isinstance(message, dict):
                role = message.get("role", "unknown")
                content = message.get("content") or ""
                name = message.get("name", "Unknown Tool")
            else:
                role = message.role
                content = message.content or ""
                if message.reasoning and message.reasoning.content:
                    reasoning_content = message.reasoning.content
                if message.tool_calls:
                    tool_calls = message.tool_calls
                name = "unknown"

            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                tool_call_lines = []
                for untyped_tool_call in tool_calls:
                    tool_call = cast(ChatCompletionMessageFunctionToolCall, untyped_tool_call)
                    if tool_call.function and tool_call.function.name and tool_call.function.arguments:
                        tool_call_lines.append(f"<tool_call>'{tool_call.function.name}' with arguments: {json_to_readable_yaml(tool_call.function.arguments)}</tool_call>")
                thoughts_block = f"<thoughts>{reasoning_content}</thoughts>\n" if reasoning_content else ""
                tool_calls_block = f"\n<tool_calls>\n{'\n'.join(tool_call_lines)}</tool_calls>" if tool_call_lines else ""
                prompt_parts.append(f"Assistant:\n{thoughts_block}{content}{tool_calls_block}")
            elif role == "tool":
                prompt_parts.append(f"Tool [{name}]: {json_to_readable_yaml(content) if content.lstrip().startswith('{') else content}")
            else:
                prompt_parts.append(f"{role.capitalize()}: {content}")

        return "\n\n".join(prompt_parts)
