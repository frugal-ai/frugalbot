import asyncio
import base64
import os
import time
from typing import Any, Literal, cast

import orjson as json
from any_llm.providers.gemini.utils import _convert_tool_spec
from any_llm.types.completion import (
    ChatCompletion,
    ChatCompletionMessage,
    ChatCompletionMessageFunctionToolCall,
    Choice,
    CompletionUsage,
    Function,
    Reasoning,
)
from google import genai
from openai.types.completion_usage import CompletionTokensDetails, PromptTokensDetails
from pydantic import Field
from tenacity import RetryCallState, retry, retry_if_exception, stop_after_attempt, wait_exponential

from frugalbot.clients.base import LLMClient, LLMClientConfig, log_retry
from frugalbot.conversation import Conversation
from frugalbot.events import MessageEvent, MessageMarkup, MessageType, bus
from frugalbot.tools.base import Tools
from frugalbot.utils.json import json_to_readable_yaml


class GoogleClientConfig(LLMClientConfig):
    model: str = Field(..., description="The model identifier", examples=["gemma-4-31b-it", "gemini-3-flash-preview"])
    api_key_env_var: str = Field(..., description="The name of the env variable that contains the API key", examples=["GEMINI_API_KEY"])
    output_traceback_on_error: bool = False


async def _log_retry(retry_state: RetryCallState):
    client = cast(GoogleClient, retry_state.args[0])
    await log_retry(retry_state, client.output_traceback_on_error)


def _to_dict(msg: dict[str, Any] | ChatCompletionMessage) -> dict[str, Any]:
    if isinstance(msg, dict):
        return msg
    if isinstance(msg, ChatCompletionMessage):
        msg_dict = msg.model_dump()
        if msg.tool_calls:
            for i, tc in enumerate(msg.tool_calls):
                if hasattr(tc, "extra_content"):
                    msg_dict["tool_calls"][i]["extra_content"] = tc.extra_content  # type: ignore
        return msg_dict
    raise ValueError(f"Unsupported message type: {type(msg)}")


# modified version of: https://github.com/mozilla-ai/any-llm/blob/5e3c4ed970ed21e6a53a24a1072c7692ae7b73c9/src/any_llm/providers/gemini/utils.py#L151
# apache license: https://github.com/mozilla-ai/any-llm/blob/5e3c4ed970ed21e6a53a24a1072c7692ae7b73c9/LICENSE
def _convert_messages_with_fixes(conversation: Conversation) -> tuple[list[genai.types.Content], str | None]:
    """Convert messages to Google GenAI format."""
    messages = [_to_dict(msg) for msg in conversation.messages]
    formatted_messages = []
    system_instruction = None

    for message in messages:
        if message["role"] == "system":
            if system_instruction is None:
                system_instruction = message["content"]
            else:
                system_instruction += f"\n{message['content']}"
        elif message["role"] == "user":
            if isinstance(message["content"], str):
                parts = [genai.types.Part.from_text(text=message["content"])]
            elif message["content"] is not None:
                parts = [genai.types.Part.from_text(text=content["text"]) for content in message["content"] if content["type"] == "text"]
            else:
                parts = []
            if parts:
                formatted_messages.append(genai.types.Content(role="user", parts=parts))
        elif message["role"] == "assistant":
            parts = []
            if "reasoning" in message and message["reasoning"] and "content" in message["reasoning"] and message["reasoning"]["content"]:
                parts.append(genai.types.Part(text=message["reasoning"]["content"], thought=True))
            if message.get("content"):
                parts.append(genai.types.Part.from_text(text=message["content"]))
            if message.get("tool_calls"):
                for i, tool_call in enumerate(message["tool_calls"]):
                    function_call = tool_call["function"]
                    args = json.loads(function_call["arguments"]) if function_call["arguments"] else {}

                    # Extract thought_signature if present (OpenAI compatibility format)
                    thought_signature = None
                    if extra_content := tool_call.get("extra_content"):
                        if google_extra := extra_content.get("google"):
                            ts = google_extra.get("thought_signature")
                            if ts:
                                thought_signature = base64.b64decode(ts)

                    # For the first function call in parallel calls, if no thought_signature is present,
                    # use the skip validator sentinel per Google's documentation:
                    # https://ai.google.dev/gemini-api/docs/thought-signatures#faqs
                    if i == 0 and thought_signature is None:
                        thought_signature = b"skip_thought_signature_validator"

                    parts.append(
                        genai.types.Part(
                            function_call=genai.types.FunctionCall(name=function_call["name"], args=args),
                            thought_signature=thought_signature,
                        )
                    )
            if parts:
                formatted_messages.append(genai.types.Content(role="model", parts=parts))

        elif message["role"] == "tool":
            content = message["content"]
            try:
                content_json = json.loads(content)
                part = genai.types.Part.from_function_response(name=message.get("name", "unknown"), response=content_json if isinstance(content_json, dict) else {"result": content_json})
                formatted_messages.append(genai.types.Content(role="user", parts=[part]))
            except json.JSONDecodeError:
                part = genai.types.Part.from_function_response(name=message.get("name", "unknown"), response={"result": content if content is not None else ""})
                formatted_messages.append(genai.types.Content(role="user", parts=[part]))

    return formatted_messages, system_instruction


class GoogleClient(LLMClient[GoogleClientConfig]):
    def __init__(self, config: GoogleClientConfig):
        super().__init__(config)
        api_key = os.getenv(config.api_key_env_var)
        self.client = genai.Client(api_key=api_key)
        self.provider = "google"
        self.model = config.model
        self.output_traceback_on_error = config.output_traceback_on_error

    @property
    def supports_thinking(self) -> bool:
        return True

    @property
    def base_url(self) -> str:
        return ""

    @retry(
        retry=retry_if_exception(lambda e: not isinstance(e, asyncio.CancelledError)),
        stop=stop_after_attempt(20),
        wait=wait_exponential(multiplier=1, min=1, max=90),
        before_sleep=_log_retry,
    )
    async def call(self, conversation: Conversation, tools: Tools) -> ChatCompletion:
        contents, system_instruction = _convert_messages_with_fixes(conversation)
        config: dict[str, Any] = {
            "system_instruction": system_instruction,
            "tools": _convert_tool_spec([tool.get_schema() for tool in tools.get_all()]),
            "automatic_function_calling": {"disable": True},
        }
        if self.thinking_level != "NONE":
            config["thinking_config"] = {"include_thoughts": True, "thinking_level": self.thinking_level}

        stream = await self.client.aio.models.generate_content_stream(model=self.model, contents=cast(genai.types.ContentListUnion, contents), config=genai.types.GenerateContentConfig(**config))

        full_reasoning = ""
        full_content = ""
        parsed_tool_calls: list[ChatCompletionMessageFunctionToolCall] = []
        completion_id: str = f"chatcmpl-{int(time.time() * 1000)}"
        finish_reason: Literal["stop", "length", "tool_calls", "content_filter", "function_call"] = "stop"
        created: int = int(time.time())
        usage: CompletionUsage | None = None
        async for chunk in stream:
            if chunk.usage_metadata:
                cached_tokens = 0
                for c in chunk.usage_metadata.cache_tokens_details or []:
                    cached_tokens += c.token_count if c.token_count else 0
                usage = CompletionUsage(
                    completion_tokens=chunk.usage_metadata.candidates_token_count or 0,
                    prompt_tokens=chunk.usage_metadata.prompt_token_count or 0,
                    total_tokens=chunk.usage_metadata.total_token_count or 0,
                    completion_tokens_details=CompletionTokensDetails(reasoning_tokens=chunk.usage_metadata.thoughts_token_count),
                    prompt_tokens_details=PromptTokensDetails(cached_tokens=cached_tokens),
                )

            if not chunk.candidates:
                continue

            candidate = chunk.candidates[0]

            if candidate.finish_reason:
                fr = str(candidate.finish_reason).lower()
                if "max" in fr or "length" in fr:
                    finish_reason = "length"
                elif "stop" in fr:
                    finish_reason = "stop"
                elif "content_filter" in fr or "safety" in fr:
                    finish_reason = "content_filter"

            if not candidate.content or not candidate.content.parts:
                continue

            for part in candidate.content.parts:
                if part.thought and part.text:
                    full_reasoning += part.text
                    await bus.emit_and_handle(MessageEvent(part.text, MessageType.THINKING, MessageMarkup.MARKDOWN, is_stream=True))

                elif part.function_call:
                    fc = part.function_call
                    args_dict = getattr(fc, "args", {})
                    args_str = json.dumps(args_dict).decode("utf-8") if args_dict else "{}"
                    tc_id = getattr(fc, "id", "")

                    thought_signature = part.thought_signature
                    tool_call = ChatCompletionMessageFunctionToolCall(
                        id=tc_id,
                        function=Function(name=getattr(fc, "name", ""), arguments=args_str),
                        type="function",
                        extra_content={"google": {"thought_signature": base64.b64encode(thought_signature).decode("utf-8")}} if thought_signature else None,
                    )
                    parsed_tool_calls.append(tool_call)
                    await bus.emit_and_handle(MessageEvent(f"tool_name: {tool_call.function.name}\n{json_to_readable_yaml(tool_call.function.arguments)}\n", MessageType.TOOL_CALL, MessageMarkup.YAML))

                elif part.text:
                    full_content += part.text
                    await bus.emit_and_handle(MessageEvent(part.text, MessageType.ASSISTANT, MessageMarkup.MARKDOWN, is_stream=True))

        if parsed_tool_calls:
            finish_reason = "tool_calls"

        return ChatCompletion(
            id=completion_id,
            choices=[
                Choice(
                    finish_reason=finish_reason,
                    index=0,
                    message=ChatCompletionMessage(
                        role="assistant",
                        content=full_content if full_content else None,
                        reasoning=Reasoning(content=full_reasoning) if full_reasoning else None,
                        tool_calls=parsed_tool_calls,  # type: ignore
                    ),
                )
            ],
            created=created,
            model=self.model,
            object="chat.completion",
            usage=usage,
        )
