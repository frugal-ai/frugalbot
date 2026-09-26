"""GitHub Copilot LLM client.

This client drives the official ``github-copilot-sdk`` as a *pure LLM transport*:
frugalbot keeps ownership of the agent loop, conversation, tools, hooks,
approvals, telemetry and session persistence.

Design A (see ``plans/github_copilot_client_plan.md``):

* Copilot's built-in tools are hidden via ``mode="empty"`` plus
  ``available_tools=ToolSet().add_custom("*")``.
* frugalbot tools are registered as *declaration-only* external tools; the
  runtime emits ``external_tool.requested`` events which are surfaced back as
  normalized ``tool_calls`` and later resolved through
  ``session.rpc.tools.handle_pending_tool_call``.
* The SDK is a stateful runtime that owns the conversation for a session and
  cannot ingest an arbitrary message array, so frugalbot's conversation is
  mirrored into one live session per ``Conversation`` (incrementally, with the
  frugalbot ``Conversation`` remaining canonical).
"""

import asyncio
import os
import shutil
import time
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import orjson as json
from any_llm.types.completion import (
    ChatCompletion,
    ChatCompletionMessage,
    ChatCompletionMessageFunctionToolCall,
    Choice,
    CompletionUsage,
    Function,
    Reasoning,
)
from copilot import CopilotClient as SdkCopilotClient
from copilot import CopilotSession, ModelInfo, PermissionHandler, RuntimeConnection, SessionEvent, Tool, ToolSet
from copilot.rpc import HandlePendingToolCallRequest, SendMessageItem, SendMessagesRequest
from copilot.session_events import (
    AssistantMessageData,
    AssistantMessageDeltaData,
    AssistantReasoningData,
    AssistantReasoningDeltaData,
    AssistantTurnEndData,
    AssistantTurnRetryData,
    AssistantTurnStartData,
    AssistantUsageData,
    ExternalToolRequestedData,
    SessionErrorData,
    SessionIdleData,
    SessionUsageInfoData,
)
from copilot.tools import ToolResult, tool_result_to_external_tool_text_result_for_llm
from openai.types.completion_usage import CompletionTokensDetails, PromptTokensDetails
from pydantic import Field
from tenacity import RetryCallState, retry, retry_if_exception, stop_after_attempt, wait_exponential

from frugalbot.clients.base import LLMClient, LLMClientConfig, LLMClientError, log_retry
from frugalbot.conversation import Conversation
from frugalbot.events import MessageEvent, MessageMarkup, MessageType, bus
from frugalbot.tools.base import Tools
from frugalbot.utils.json import json_to_readable_yaml

COPILOT_PROVIDER = "github-copilot"
COPILOT_BASE_URL = "https://api.githubcopilot.com"
DEFAULT_BASE_DIRECTORY = Path.home() / ".frugalbot" / "copilot"

_THINKING_LEVEL_TO_EFFORT: dict[str, str] = {"LOW": "low", "MEDIUM": "high", "HIGH": "max"}
_EFFORT_ORDER: list[str] = ["low", "medium", "high", "xhigh", "max"]
_MAX_RESTORED_TRANSCRIPT_CHARS = 40_000
_MAX_RETRY_ATTEMPTS = 3

_INSTALL_INSTRUCTIONS = "The GitHub Copilot runtime is not installed.\nInstall it with:  python -m copilot download-runtime\nor set COPILOT_CLI_PATH / clients.copilot.cli_path to an existing runtime."


class CopilotClientConfig(LLMClientConfig):
    model: str = Field(..., description="The Copilot model identifier", examples=["gpt-5", "auto"])
    api_key_env_var: str = Field(..., description="Name of the env variable holding a GitHub token/PAT", examples=["COPILOT_GITHUB_TOKEN"])
    output_traceback_on_error: bool = False
    cli_path: str | None = Field(default=None, description="Path to a pre-installed Copilot runtime. Falls back to COPILOT_CLI_PATH and the SDK cache.")
    base_directory: str | None = Field(default=None, description="Base directory for Copilot session state. Required by mode='empty'.")
    auto_tier: Literal["efficiency", "balance", "intelligence", "fast"] | None = Field(default=None, description="Auto routing preference. Only used when model='auto'.")
    reasoning_effort: str | None = Field(default=None, description="Explicit reasoning effort override; when unset the thinking-level mapping is used.")


def _get_cached_runtime() -> str | None:
    """Return the SDK-cached runtime path without triggering a download, or None."""
    try:
        from copilot._cli_download import get_cached_cli_path
    except ImportError:  # pragma: no cover - the dependency is a hard requirement
        return None
    return get_cached_cli_path()


def _get_pinned_cli_version() -> str | None:
    """Return the pinned CLI version the SDK would download, or None if unknown."""
    try:
        from copilot._cli_version import CLI_VERSION
    except ImportError:  # pragma: no cover - the dependency is a hard requirement
        return None
    return CLI_VERSION


def ensure_copilot_runtime(config: CopilotClientConfig) -> str:
    """Resolve a pre-installed Copilot runtime path, preferring explicit config.

    Auto-download is intentionally never triggered. Raises ``LLMClientError``
    with install instructions when no runtime can be found.
    """
    os.environ.setdefault("COPILOT_SKIP_CLI_DOWNLOAD", "1")
    if config.cli_path:
        cli_path = Path(config.cli_path).expanduser()
        if cli_path.exists():
            return str(cli_path)
        raise LLMClientError(f"clients.copilot.cli_path does not exist: {cli_path}\n\n{_INSTALL_INSTRUCTIONS}")

    env_cli_path = os.environ.get("COPILOT_CLI_PATH")
    if env_cli_path:
        cli_path = Path(env_cli_path).expanduser()
        if cli_path.exists():
            return str(cli_path)
        raise LLMClientError(f"COPILOT_CLI_PATH does not exist: {cli_path}\n\n{_INSTALL_INSTRUCTIONS}")

    for executable in ("copilot-runtime", "copilot"):
        found = shutil.which(executable)
        if found:
            return found

    cached = _get_cached_runtime()
    if cached:
        return cached

    raise LLMClientError(_INSTALL_INSTRUCTIONS)


def _is_pinned_runtime(runtime_path: str) -> bool:
    """Return True when the runtime lives inside the SDK's pinned cache version."""
    pinned = _get_pinned_cli_version()
    if not pinned:
        return True
    parts = Path(runtime_path).parts
    return pinned in parts and "github-copilot-sdk" in parts


def _arguments_to_json_str(arguments: Any) -> str:
    if arguments is None:
        return "{}"
    if isinstance(arguments, str):
        return arguments
    return json.dumps(arguments).decode("utf-8")


def _map_usage(data: AssistantUsageData) -> CompletionUsage:
    prompt_tokens = data.input_tokens or 0
    completion_tokens = data.output_tokens or 0
    return CompletionUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        completion_tokens_details=CompletionTokensDetails(reasoning_tokens=data.reasoning_tokens),
        prompt_tokens_details=PromptTokensDetails(cached_tokens=data.cache_read_tokens),
    )


def _clamp_effort(desired: str, supported: list[str]) -> str | None:
    """Return the nearest supported effort level, or None when none are supported."""
    if not supported or desired in supported:
        return desired
    ordered_supported = [effort for effort in _EFFORT_ORDER if effort in supported]
    if not ordered_supported:
        return None
    target_index = _EFFORT_ORDER.index(desired) if desired in _EFFORT_ORDER else len(_EFFORT_ORDER) - 1
    return min(ordered_supported, key=lambda effort: (abs(_EFFORT_ORDER.index(effort) - target_index), _EFFORT_ORDER.index(effort)))


def _system_prompt(conversation: Conversation) -> str:
    for entry in conversation.entries:
        if isinstance(entry, dict) and entry.get("role") == "system":
            return entry.get("content") or ""
    return ""


def _restored_prefix_len(conversation: Conversation) -> int:
    """Number of leading entries that should be treated as restored history.

    When the conversation ends with a user message, that final message is the
    originating turn for the new session and is delivered through the normal
    ``send`` path rather than folded into the restored transcript.
    """
    entries = conversation.entries
    if entries and isinstance(entries[-1], dict) and entries[-1].get("role") == "user":
        return len(entries) - 1
    return len(entries)


def _render_assistant_message(message: ChatCompletionMessage) -> str:
    reasoning = message.reasoning.content if message.reasoning and message.reasoning.content else ""
    tool_call_lines: list[str] = []
    for untyped_tool_call in message.tool_calls or []:
        tool_call = cast(ChatCompletionMessageFunctionToolCall, untyped_tool_call)
        if tool_call.function and tool_call.function.name and tool_call.function.arguments:
            tool_call_lines.append(f"<tool_call>'{tool_call.function.name}' with arguments: {json_to_readable_yaml(tool_call.function.arguments)}</tool_call>")
    thoughts_block = f"<thoughts>{reasoning}</thoughts>\n" if reasoning else ""
    tool_calls_block = f"\n<tool_calls>\n{'\n'.join(tool_call_lines)}</tool_calls>" if tool_call_lines else ""
    return f"Assistant:\n{thoughts_block}{message.content or ''}{tool_calls_block}"


def _render_entries(entries: list[dict[str, Any] | tuple[str, ChatCompletion]]) -> str:
    """Render a slice of conversation entries as a plain transcript."""
    parts: list[str] = []
    for entry in entries:
        if isinstance(entry, tuple):
            parts.append(_render_assistant_message(entry[1].choices[0].message))
            continue
        role = entry.get("role", "unknown")
        if role == "system":
            continue
        content = entry.get("content") or ""
        if role == "user":
            parts.append(f"User: {content}")
        elif role == "assistant":
            parts.append(f"Assistant:\n{content}")
        elif role == "tool":
            name = entry.get("name", "unknown")
            rendered = json_to_readable_yaml(content) if content.lstrip().startswith("{") else content
            parts.append(f"Tool [{name}]: {rendered}")
        else:
            parts.append(f"{role.capitalize()}: {content}")
    return "\n\n".join(parts)


def _cap_transcript(transcript: str) -> str:
    if len(transcript) <= _MAX_RESTORED_TRANSCRIPT_CHARS:
        return transcript
    return "[... earlier conversation history truncated ...]\n\n" + transcript[-_MAX_RESTORED_TRANSCRIPT_CHARS:]


def _is_retryable(exc: BaseException) -> bool:
    return not isinstance(exc, (asyncio.CancelledError, LLMClientError))


def _finalize_session(state: _SessionState) -> None:
    """Best-effort disconnect of a session whose conversation was garbage-collected."""
    session = state.session
    state.session = None
    if session is None:
        return
    loop = state.loop
    if loop is None or loop.is_closed():
        return
    try:
        loop.call_soon_threadsafe(asyncio.ensure_future, session.disconnect())
    except RuntimeError:  # pragma: no cover - loop shut down between checks
        pass


async def _log_retry(retry_state: RetryCallState) -> None:
    client = cast(CopilotClient, retry_state.args[0])
    await log_retry(retry_state, client.output_traceback_on_error)


@dataclass
class _PendingToolRequest:
    request_id: str
    tool_name: str


@dataclass
class _SessionState:
    session: CopilotSession | None = None
    events: asyncio.Queue[SessionEvent] = field(default_factory=asyncio.Queue)
    unsubscribe: Any = None
    delivered_count: int = 0
    pending_tool_requests: dict[str, _PendingToolRequest] = field(default_factory=dict)
    applied_reasoning_effort: str | None = None
    applied_model: str = ""
    usage_info: SessionUsageInfoData | None = None
    loop: asyncio.AbstractEventLoop | None = None
    finalizer: weakref.finalize | None = None

    def enqueue(self, event: SessionEvent) -> None:
        self.events.put_nowait(event)


class CopilotClient(LLMClient[CopilotClientConfig]):
    def __init__(self, config: CopilotClientConfig) -> None:
        super().__init__(config)
        self._runtime_path = ensure_copilot_runtime(config)
        self._sdk_client: SdkCopilotClient | None = None
        self._started = False
        self._states: weakref.WeakKeyDictionary[Conversation, _SessionState] = weakref.WeakKeyDictionary()
        self._model_infos: list[ModelInfo] | None = None
        self._supports_thinking = True
        self._warned_unpinned_runtime = False
        self.output_traceback_on_error = config.output_traceback_on_error
        self.provider = COPILOT_PROVIDER
        self.model = config.model

    @property
    def base_url(self) -> str:
        return COPILOT_BASE_URL

    @property
    def supports_thinking(self) -> bool:
        return self._supports_thinking

    # ------------------------------------------------------------------
    # SDK boundary
    # ------------------------------------------------------------------

    def _create_sdk_client(self) -> SdkCopilotClient:
        base_directory = Path(self.config.base_directory).expanduser() if self.config.base_directory else DEFAULT_BASE_DIRECTORY
        return SdkCopilotClient(
            mode="empty",
            base_directory=str(base_directory),
            github_token=os.getenv(self.config.api_key_env_var),
            working_directory=str(Path.cwd()),
            connection=RuntimeConnection.for_stdio(path=self._runtime_path),
        )

    async def _ensure_sdk_started(self) -> SdkCopilotClient:
        if self._sdk_client is None:
            self._sdk_client = self._create_sdk_client()
        if not self._started:
            await self._sdk_client.start()
            self._started = True
            await self._maybe_warn_unpinned_runtime()
        return self._sdk_client

    async def _maybe_warn_unpinned_runtime(self) -> None:
        if self._warned_unpinned_runtime or _is_pinned_runtime(self._runtime_path):
            return
        self._warned_unpinned_runtime = True
        await bus.emit_and_handle(
            MessageEvent(
                f"The configured GitHub Copilot runtime ('{self._runtime_path}') is outside the SDK's pinned cache version. Protocol drift is possible.",
                MessageType.WARNING,
            )
        )

    async def _get_model_infos(self) -> list[ModelInfo]:
        if self._model_infos is None:
            sdk_client = await self._ensure_sdk_started()
            self._model_infos = await sdk_client.list_models()
        return self._model_infos

    # ------------------------------------------------------------------
    # Thinking / model reconciliation
    # ------------------------------------------------------------------

    def _desired_effort(self) -> str | None:
        if self.config.reasoning_effort:
            return self.config.reasoning_effort
        if self.thinking_level == "NONE":
            return None
        return _THINKING_LEVEL_TO_EFFORT[self.thinking_level]

    async def _resolve_effort(self, model_infos: list[ModelInfo]) -> str | None:
        if self.model == "auto":
            self._supports_thinking = any(info.capabilities.supports.reasoning_effort for info in model_infos)
            return None

        model_info = next((info for info in model_infos if info.id == self.model), None)
        if model_info is None:
            available = ", ".join(sorted(info.id for info in model_infos)) or "(none reported)"
            raise LLMClientError(f"Model '{self.model}' is not offered by GitHub Copilot. Available models: {available}")

        supports_reasoning = bool(model_info.capabilities.supports.reasoning_effort)
        self._supports_thinking = supports_reasoning
        desired = self._desired_effort()
        if desired is None:
            return None
        if not supports_reasoning:
            await bus.emit_and_handle(MessageEvent(f"Model '{self.model}' does not support reasoning, ignoring reasoning effort '{desired}'.", MessageType.WARNING))
            return None

        clamped = _clamp_effort(desired, list(model_info.supported_reasoning_efforts or []))
        if clamped != desired:
            if clamped is None:
                await bus.emit_and_handle(MessageEvent(f"Model '{self.model}' does not support any reasoning effort, ignoring '{desired}'.", MessageType.WARNING))
            else:
                await bus.emit_and_handle(MessageEvent(f"Reasoning effort '{desired}' is not supported by model '{self.model}', using '{clamped}' instead.", MessageType.WARNING))
        return clamped

    async def _reconcile_session(self, state: _SessionState) -> None:
        model_infos = await self._get_model_infos()
        effort = await self._resolve_effort(model_infos)
        if state.applied_reasoning_effort != effort or state.applied_model != self.model:
            session = state.session
            if session is not None:
                await session.set_model(self.model, reasoning_effort=effort)
            state.applied_reasoning_effort = effort
            state.applied_model = self.model

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def _get_state(self, conversation: Conversation) -> _SessionState:
        state = self._states.get(conversation)
        if state is None:
            state = _SessionState()
            self._states[conversation] = state
        return state

    def _copilot_tools(self, tools: Tools) -> list[Tool]:
        copilot_tools: list[Tool] = []
        for tool in tools.get_all():
            schema = tool.get_schema()["function"]
            copilot_tools.append(
                Tool(
                    name=schema["name"],
                    description=schema["description"],
                    parameters=schema["parameters"],
                    handler=None,
                    defer="never",
                    overrides_built_in_tool=True,
                )
            )
        return copilot_tools

    async def _create_sdk_session(self, system_prompt: str, copilot_tools: list[Tool], effort: str | None) -> CopilotSession:
        sdk_client = await self._ensure_sdk_started()
        capi = {"auto_tier": self.config.auto_tier} if self.model == "auto" and self.config.auto_tier else None
        return await sdk_client.create_session(
            model=self.model,
            reasoning_effort=cast(Any, effort),
            reasoning_summary="none" if self.thinking_level == "NONE" else None,
            tools=copilot_tools,
            system_message={"mode": "replace", "content": system_prompt},
            available_tools=ToolSet().add_custom("*"),
            streaming=True,
            infinite_sessions={"enabled": False},
            capi=cast(Any, capi),
            on_permission_request=PermissionHandler.approve_all,
        )

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(_MAX_RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=_log_retry,
        reraise=True,
    )
    async def _initialize_state(self, state: _SessionState, conversation: Conversation, tools: Tools) -> None:
        model_infos = await self._get_model_infos()
        effort = await self._resolve_effort(model_infos)

        system_prompt = _system_prompt(conversation)
        restored_transcript = _cap_transcript(_render_entries(conversation.entries[: _restored_prefix_len(conversation)]))
        if restored_transcript:
            system_prompt = f"{system_prompt}\n\n## Restored Conversation Context\n(Prior turns restored from a frugalbot session; treat as conversation history.)\n{restored_transcript}"

        session = await self._create_sdk_session(system_prompt, self._copilot_tools(tools), effort)
        state.session = session
        state.applied_model = self.model
        state.applied_reasoning_effort = effort
        state.delivered_count = _restored_prefix_len(conversation)
        state.unsubscribe = session.on(state.enqueue)
        state.loop = asyncio.get_running_loop()
        state.finalizer = weakref.finalize(conversation, _finalize_session, state)

    def _drain(self, state: _SessionState) -> None:
        while not state.events.empty():
            try:
                state.events.get_nowait()
            except asyncio.QueueEmpty:  # pragma: no cover - race between empty() and get_nowait()
                return

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(_MAX_RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=_log_retry,
        reraise=True,
    )
    async def _deliver(self, state: _SessionState, new_entries: list[dict[str, Any] | tuple[str, ChatCompletion]]) -> None:
        session = state.session
        if session is None:  # pragma: no cover - session is always created before delivery
            raise LLMClientError("Cannot deliver messages without an active Copilot session.")

        tool_entries: list[dict[str, Any]] = []
        user_prompts: list[str] = []
        for entry in new_entries:
            if not isinstance(entry, dict):
                continue
            role = entry.get("role")
            if role == "tool":
                tool_call_id = entry.get("tool_call_id")
                if tool_call_id and tool_call_id in state.pending_tool_requests:
                    tool_entries.append(entry)
            elif role == "user":
                content = entry.get("content")
                if content:
                    user_prompts.append(content)

        for entry in tool_entries:
            tool_call_id = entry["tool_call_id"]
            pending = state.pending_tool_requests.pop(tool_call_id)
            await self._resolve_pending_tool_call(session, pending, entry.get("content") or "")

        if tool_entries:
            return
        if user_prompts:
            await self._send_prompts(session, user_prompts)
            return
        await session.rpc.send_messages(SendMessagesRequest(messages=[]))

    async def _resolve_pending_tool_call(self, session: CopilotSession, pending: _PendingToolRequest, content: str) -> None:
        result = tool_result_to_external_tool_text_result_for_llm(ToolResult(text_result_for_llm=content, result_type="success"))
        await session.rpc.tools.handle_pending_tool_call(HandlePendingToolCallRequest(request_id=pending.request_id, result=result))

    async def _send_prompts(self, session: CopilotSession, prompts: list[str]) -> None:
        if len(prompts) == 1:
            await session.send(prompts[0])
        else:
            await session.rpc.send_messages(SendMessagesRequest(messages=[SendMessageItem(prompt=prompt) for prompt in prompts]))

    # ------------------------------------------------------------------
    # Event collection
    # ------------------------------------------------------------------

    async def _on_external_tool_requested(self, state: _SessionState, data: ExternalToolRequestedData, tool_calls: dict[str, ChatCompletionMessageFunctionToolCall]) -> None:
        arguments = _arguments_to_json_str(data.arguments)
        state.pending_tool_requests[data.tool_call_id] = _PendingToolRequest(request_id=data.request_id, tool_name=data.tool_name)
        tool_calls[data.tool_call_id] = ChatCompletionMessageFunctionToolCall(
            id=data.tool_call_id,
            function=Function(name=data.tool_name, arguments=arguments),
            type="function",
        )
        await bus.emit_and_handle(MessageEvent(f"tool_name: {data.tool_name}\n{json_to_readable_yaml(arguments)}\n", MessageType.TOOL_CALL, MessageMarkup.YAML))

    def _fallback_usage(self, state: _SessionState, output_tokens: int | None) -> CompletionUsage | None:
        if output_tokens is None and state.usage_info is None:
            return None
        prompt_tokens = state.usage_info.current_tokens if state.usage_info else 0
        completion_tokens = output_tokens or 0
        return CompletionUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=prompt_tokens + completion_tokens)

    async def _collect(self, state: _SessionState) -> ChatCompletion:
        full_content = ""
        full_reasoning = ""
        streamed_content = False
        streamed_reasoning = False
        tool_calls: dict[str, ChatCompletionMessageFunctionToolCall] = {}
        expected_tool_ids: set[str] = set()
        received_tool_ids: set[str] = set()
        usage: CompletionUsage | None = None
        output_tokens_fallback: int | None = None
        message_id = ""
        finish_reason: Literal["stop", "length", "tool_calls", "content_filter", "function_call"] = "stop"
        # The runtime emits the `assistant.turn_end` of a tool-request turn only
        # *after* its pending tool call is resolved (see `handle_pending_tool_call`).
        # That stale turn_end arrives before the new turn's `assistant.turn_start`
        # and would otherwise be mistaken for the end of the resumed turn, yielding
        # an empty completion. Track the turn's start/output so only events
        # belonging to the turn we are collecting can terminate it.
        turn_started = False
        turn_has_output = False

        while True:
            event = await state.events.get()
            data = event.data

            if isinstance(data, AssistantTurnStartData):
                turn_started = True
            elif isinstance(data, AssistantMessageDeltaData):
                turn_has_output = True
                if data.delta_content:
                    full_content += data.delta_content
                    streamed_content = True
                    await bus.emit_and_handle(MessageEvent(data.delta_content, MessageType.ASSISTANT, MessageMarkup.MARKDOWN, is_stream=True))
            elif isinstance(data, AssistantReasoningDeltaData):
                turn_has_output = True
                if data.delta_content:
                    full_reasoning += data.delta_content
                    streamed_reasoning = True
                    await bus.emit_and_handle(MessageEvent(data.delta_content, MessageType.THINKING, MessageMarkup.MARKDOWN, is_stream=True))
            elif isinstance(data, AssistantMessageData):
                turn_has_output = True
                message_id = data.message_id
                if data.output_tokens is not None:
                    output_tokens_fallback = data.output_tokens
                if data.tool_requests:
                    expected_tool_ids.update(request.tool_call_id for request in data.tool_requests)
                if not streamed_content and data.content:
                    full_content = data.content
                    await bus.emit_and_handle(MessageEvent(data.content, MessageType.ASSISTANT, MessageMarkup.MARKDOWN))
            elif isinstance(data, AssistantReasoningData):
                turn_has_output = True
                if not streamed_reasoning and data.content:
                    full_reasoning = data.content
                    await bus.emit_and_handle(MessageEvent(data.content, MessageType.THINKING, MessageMarkup.MARKDOWN))
            elif isinstance(data, ExternalToolRequestedData):
                await self._on_external_tool_requested(state, data, tool_calls)
                received_tool_ids.add(data.tool_call_id)
            elif isinstance(data, AssistantUsageData):
                usage = _map_usage(data)
                if data.finish_reason == "length":
                    finish_reason = "length"
                elif data.content_filter_triggered:
                    finish_reason = "content_filter"
            elif isinstance(data, SessionUsageInfoData):
                state.usage_info = data
            elif isinstance(data, SessionErrorData):
                raise LLMClientError(f"Copilot session error ({data.error_type}): {data.message}")
            elif isinstance(data, SessionIdleData):
                if data.aborted:
                    raise asyncio.CancelledError()
                if not expected_tool_ids and (turn_started or turn_has_output):
                    break
            elif isinstance(data, AssistantTurnEndData):
                if not (expected_tool_ids - received_tool_ids) and (turn_started or turn_has_output):
                    break
            elif isinstance(data, AssistantTurnRetryData):
                await bus.emit_and_handle(MessageEvent("Copilot runtime is retrying the turn...", MessageType.WARNING))

            # Turn exit on external tool calls: the runtime suspends the turn
            # awaiting handle_pending_tool_call and defers the suspended turn's
            # turn_end/idle until the pending call is resolved, so we return the
            # tool calls as soon as all of them have been surfaced.
            if expected_tool_ids and expected_tool_ids <= received_tool_ids:
                break

        if tool_calls:
            finish_reason = "tool_calls"
        if usage is None:
            usage = self._fallback_usage(state, output_tokens_fallback)

        return ChatCompletion(
            id=message_id or f"copilot-{int(time.time() * 1000)}",
            choices=[
                Choice(
                    index=0,
                    finish_reason=finish_reason,
                    message=ChatCompletionMessage(
                        role="assistant",
                        content=full_content if full_content else None,
                        reasoning=Reasoning(content=full_reasoning) if full_reasoning else None,
                        tool_calls=list(tool_calls.values()) or None,  # type: ignore
                    ),
                )
            ],
            created=int(time.time()),
            model=self.model,
            object="chat.completion",
            usage=usage,
        )

    async def _handle_cancellation(self, state: _SessionState, conversation: Conversation) -> None:
        session = state.session
        if session is not None:
            try:
                await session.abort()
            except Exception:
                pass
        state.pending_tool_requests.clear()
        state.delivered_count = len(conversation.entries)
        self._drain(state)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def call(self, conversation: Conversation, tools: Tools) -> ChatCompletion:
        state = self._get_state(conversation)
        self._drain(state)

        if state.session is None:
            await self._initialize_state(state, conversation, tools)
        else:
            await self._reconcile_session(state)
        self._drain(state)

        new_entries = conversation.entries[state.delivered_count :]
        try:
            await self._deliver(state, new_entries)
            completion = await self._collect(state)
        except asyncio.CancelledError:
            await self._handle_cancellation(state, conversation)
            raise

        state.delivered_count = len(conversation.entries)
        return completion

    async def close(self) -> None:
        for state in list(self._states.values()):
            if state.finalizer is not None:
                state.finalizer.detach()
                state.finalizer = None
            session = state.session
            state.session = None
            if state.unsubscribe is not None:
                state.unsubscribe()
                state.unsubscribe = None
            if session is not None:
                try:
                    await session.disconnect()
                except Exception:
                    pass
        self._states.clear()

        if self._sdk_client is not None:
            try:
                await self._sdk_client.stop()
            finally:
                self._sdk_client = None
                self._started = False
