import asyncio
import os
from typing import Any, Literal, cast

from any_llm import AnyLLM, LLMProvider
from any_llm.types.completion import ChatCompletion, ChatCompletionMessage, ChatCompletionMessageFunctionToolCall, Choice, CompletionUsage, Function, Reasoning
from pydantic import BaseModel, Field
from tenacity import RetryCallState, retry, retry_if_exception, stop_after_attempt, wait_exponential

from frugalbot.clients.base import LLMClient, LLMClientConfig, log_retry
from frugalbot.conversation import Conversation
from frugalbot.events import MessageEvent, MessageMarkup, MessageType, bus
from frugalbot.tools.base import Tools


class ProviderModels(BaseModel):
    provider: str
    models: list[str]


class AnyLLMConfig(LLMClientConfig):
    provider: LLMProvider
    model: str
    api_key_env_var: str
    base_url: str | None = None
    extra_body: dict[str, Any] = Field(default_factory=dict)
    xhigh_provider_models: list[ProviderModels] = Field(default_factory=list)
    use_xhigh_not_high: bool = False
    output_traceback_on_error: bool = False


def _convert_any_llm_provider_to_models_dev_provider(provider: LLMProvider) -> str:
    """
    Converts an LLMProvider enum to a provider ID string from the target list.
    """
    mapping = {
        LLMProvider.BEDROCK: "amazon-bedrock",
        LLMProvider.FIREWORKS: "fireworks-ai",
        LLMProvider.GEMINI: "google",
        LLMProvider.MOONSHOT: "moonshotai",
        LLMProvider.MZAI: "302ai",  # Assuming MZAI maps to 302ai based on common naming
        LLMProvider.QINIU: "qiniu-ai",
        LLMProvider.TOGETHER: "togetherai",
        LLMProvider.VERTEXAI: "google-vertex",
        LLMProvider.VERTEXAIANTHROPIC: "google-vertex-anthropic",
        LLMProvider.AZUREANTHROPIC: "azure",
        LLMProvider.AZUREOPENAI: "azure",
        LLMProvider.DASHSCOPE: "alibaba",
        LLMProvider.GATEWAY: "cloudflare-ai-gateway",
        LLMProvider.OLLAMA: "ollama-cloud",
    }
    if provider in mapping:
        return mapping[provider]
    # others that don't have a mapping are an exact match
    return provider.value


async def _log_retry(retry_state: RetryCallState):
    client = cast(AnyLLMClient, retry_state.args[0])
    await log_retry(retry_state, client.output_traceback_on_error)


class AnyLLMClient(LLMClient[AnyLLMConfig]):
    def __init__(self, config: AnyLLMConfig):
        super().__init__(config)
        self.client = AnyLLM.create(provider=config.provider, api_key=os.getenv(config.api_key_env_var), api_base=config.base_url)
        self._base_url = config.base_url or ""
        self.provider = _convert_any_llm_provider_to_models_dev_provider(LLMProvider.from_string(config.provider))
        self.model = config.model
        self.extra_body = config.extra_body
        self.xhigh_provider_models = {entry.provider: set(entry.models) for entry in config.xhigh_provider_models}
        self.use_xhigh = config.use_xhigh_not_high
        self.output_traceback_on_error = config.output_traceback_on_error

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def supports_thinking(self) -> bool:
        return True

    @retry(
        retry=retry_if_exception(lambda e: not isinstance(e, asyncio.CancelledError)),
        stop=stop_after_attempt(20),
        wait=wait_exponential(multiplier=1, min=1, max=90),
        before_sleep=_log_retry,
    )
    async def call(self, conversation: Conversation, tools: Tools) -> ChatCompletion:
        reasoning_effort = None
        if self.thinking_level != "NONE":
            reasoning_effort = self.thinking_level.lower()

        # TODO: there's no way to tell which ones support xhigh, a manual list seems to be the only option (?)
        if self.use_xhigh and self.thinking_level == "HIGH" and self.provider in self.xhigh_provider_models and self.model in self.xhigh_provider_models[self.provider]:
            reasoning_effort = "xhigh"

        stream = await self.client.acompletion(
            model=self.model,
            messages=conversation.messages,
            tools=[tool.get_schema() for tool in tools.get_all()],
            stream=True,
            stream_options={"include_usage": True},
            reasoning_effort=reasoning_effort,
            extra_body=self.extra_body,
        )

        full_reasoning = ""
        full_content = ""
        tool_calls: dict[int, ChatCompletionMessageFunctionToolCall] = {}
        id: str = ""
        finish_reason: Literal["stop", "length", "tool_calls", "content_filter", "function_call"] = "stop"
        created: int = 0
        model: str = ""
        usage: CompletionUsage | None = None
        streaming_tool_args = False
        async for chunk in stream:
            if chunk.usage:
                usage = chunk.usage
            if not chunk.choices:
                continue

            id = chunk.id
            delta = chunk.choices[0].delta
            if chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason
            created = chunk.created
            model = chunk.model

            if delta.reasoning and delta.reasoning.content:
                full_reasoning += delta.reasoning.content
                await bus.emit_and_handle(MessageEvent(delta.reasoning.content, MessageType.THINKING, MessageMarkup.MARKDOWN, is_stream=True))

            if delta.content:
                full_content += delta.content
                await bus.emit_and_handle(MessageEvent(delta.content, MessageType.ASSISTANT, MessageMarkup.MARKDOWN, is_stream=True))

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls:
                        tool_calls[idx] = ChatCompletionMessageFunctionToolCall(
                            id=tc_delta.id if tc_delta.id else "",
                            function=Function(name=tc_delta.function.name if tc_delta.function and tc_delta.function.name else "", arguments=""),
                            type="function",
                        )
                        if streaming_tool_args:
                            await bus.emit_and_handle(MessageEvent("\n```\n", MessageType.TOOL_CALL, MessageMarkup.MARKDOWN, is_stream=True))
                            streaming_tool_args = False
                        await bus.emit_and_handle(MessageEvent(f"tool_name: {tool_calls[idx].function.name}\n", MessageType.TOOL_CALL, MessageMarkup.MARKDOWN, is_stream=True))
                    if tc_delta.function and tc_delta.function.arguments:
                        tool_calls[idx].function.arguments += tc_delta.function.arguments
                        if not streaming_tool_args:
                            await bus.emit_and_handle(MessageEvent("```json\n", MessageType.TOOL_CALL, MessageMarkup.MARKDOWN, is_stream=True))
                            streaming_tool_args = True
                        await bus.emit_and_handle(MessageEvent(tc_delta.function.arguments, MessageType.TOOL_CALL, MessageMarkup.MARKDOWN, is_stream=True))
        if streaming_tool_args:
            await bus.emit_and_handle(MessageEvent("\n```", MessageType.TOOL_CALL, MessageMarkup.MARKDOWN, is_stream=True))

        kwargs = {}
        tool_calls_final_list = [ChatCompletionMessageFunctionToolCall(id=tc.id, function=tc.function, type="function") for tc in tool_calls.values()]
        if tool_calls_final_list:
            kwargs["tool_calls"] = tool_calls_final_list
        return ChatCompletion(
            id=id,
            choices=[
                Choice(
                    finish_reason=finish_reason,
                    index=0,
                    message=ChatCompletionMessage(
                        role="assistant",
                        content=full_content if full_content else None,
                        reasoning=Reasoning(content=full_reasoning) if full_reasoning else None,
                        **kwargs,
                    ),
                )
            ],
            created=created,
            model=model,
            object="chat.completion",
            usage=usage,
        )
