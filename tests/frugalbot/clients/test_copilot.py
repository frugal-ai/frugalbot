from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from any_llm.types.completion import (
    ChatCompletion,
    ChatCompletionMessage,
    ChatCompletionMessageFunctionToolCall,
    Choice,
    Function,
)
from copilot import (
    ModelCapabilities,
    ModelInfo,
    ModelLimits,
    ModelSupports,
    SessionEvent,
    SessionEventType,
)
from copilot.session_events import (
    AssistantMessageData,
    AssistantMessageDeltaData,
    AssistantMessageToolRequest,
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
from pydantic import BaseModel
from pytest_mock import MockerFixture

from frugalbot.clients.base import LLMClientError
from frugalbot.clients.copilot import (
    COPILOT_BASE_URL,
    COPILOT_PROVIDER,
    DEFAULT_BASE_DIRECTORY,
    CopilotClient,
    CopilotClientConfig,
    _arguments_to_json_str,
    _cap_transcript,
    _clamp_effort,
    _finalize_session,
    _get_cached_runtime,
    _get_pinned_cli_version,
    _is_pinned_runtime,
    _is_retryable,
    _log_retry,
    _render_entries,
    _restored_prefix_len,
    _SessionState,
    _system_prompt,
    ensure_copilot_runtime,
)
from frugalbot.conversation import Conversation
from frugalbot.events import MessageEvent, MessageType
from frugalbot.hooks.base import Hooks
from frugalbot.tools.base import ToolBase, ToolConfig, Tools

# =============================================================================
# Test doubles
# =============================================================================


class _EchoResult(BaseModel):
    echoed: str


class _EchoConfig(ToolConfig):
    pass


class _EchoTool(ToolBase[_EchoResult, _EchoConfig]):
    """Echoes the provided text."""

    _skip_registry = True

    async def run(self, text: Annotated[str, "The text to echo"]) -> _EchoResult:
        return _EchoResult(echoed=text)


def _model_info(
    model_id: str = "gpt-5",
    *,
    supports_reasoning: bool = True,
    supported_efforts: list[str] | None = None,
    default_effort: str | None = None,
) -> ModelInfo:
    return ModelInfo(
        id=model_id,
        name=model_id,
        capabilities=ModelCapabilities(supports=ModelSupports(reasoning_effort=supports_reasoning), limits=ModelLimits()),
        supported_reasoning_efforts=supported_efforts,
        default_reasoning_effort=default_effort,
    )


def _event(data: Any) -> SessionEvent:
    return SessionEvent(data=data, id=uuid4(), timestamp=datetime.now(), type=SessionEventType.ASSISTANT_MESSAGE)


def _completion(content: str) -> ChatCompletion:
    return ChatCompletion(
        id="c1",
        choices=[Choice(index=0, finish_reason="stop", message=ChatCompletionMessage(role="assistant", content=content))],
        created=0,
        model="gpt-5",
        object="chat.completion",
    )


class _FakeRpcTools:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session
        self.pending_calls: list[Any] = []

    async def handle_pending_tool_call(self, params: Any) -> None:
        self.pending_calls.append(params)
        self._session.emit_scripted()


class _FakeRpc:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session
        self.tools = _FakeRpcTools(session)
        self.sent_batches: list[Any] = []

    async def send_messages(self, params: Any) -> None:
        self.sent_batches.append(params)
        self._session.emit_scripted()


class _FakeSession:
    def __init__(self, scripted_events: list[SessionEvent] | None = None) -> None:
        self.handlers: list[Callable[[SessionEvent], None]] = []
        self.scripted_events: list[SessionEvent] = list(scripted_events or [])
        self.sent_prompts: list[str] = []
        self.aborted = False
        self.disconnected = False
        self.set_model_calls: list[dict[str, Any]] = []
        self.rpc = _FakeRpc(self)

    def on(self, handler: Callable[[SessionEvent], None]) -> Callable[[], None]:
        self.handlers.append(handler)

        def unsubscribe() -> None:
            if handler in self.handlers:
                self.handlers.remove(handler)

        return unsubscribe

    def emit_scripted(self) -> None:
        events, self.scripted_events = self.scripted_events, []
        for event in events:
            for handler in list(self.handlers):
                handler(event)

    async def send(self, prompt: str) -> str:
        self.sent_prompts.append(prompt)
        self.emit_scripted()
        return "msg-1"

    async def set_model(self, model: str, *, reasoning_effort: str | None = None) -> None:
        self.set_model_calls.append({"model": model, "reasoning_effort": reasoning_effort})

    async def abort(self) -> None:
        self.aborted = True

    async def disconnect(self) -> None:
        self.disconnected = True


class _FakeSdkClient:
    def __init__(self, model_infos: list[ModelInfo]) -> None:
        self.model_infos = model_infos
        self.sessions: list[_FakeSession] = []
        self.create_session_kwargs: list[dict[str, Any]] = []
        self.script_queue: list[list[SessionEvent]] = []
        self.started = False
        self.stopped = False
        self.list_models_calls = 0

    @property
    def session(self) -> _FakeSession:
        return self.sessions[-1]

    @property
    def last_create_kwargs(self) -> dict[str, Any]:
        return self.create_session_kwargs[-1]

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def list_models(self) -> list[ModelInfo]:
        self.list_models_calls += 1
        return self.model_infos

    async def create_session(self, **kwargs: Any) -> _FakeSession:
        scripted = self.script_queue.pop(0) if self.script_queue else []
        session = _FakeSession(scripted)
        self.sessions.append(session)
        self.create_session_kwargs.append(kwargs)
        return session


@dataclass
class _Harness:
    client: CopilotClient
    sdk: _FakeSdkClient


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def patch_runtime(mocker: MockerFixture) -> None:
    mocker.patch("frugalbot.clients.copilot._get_pinned_cli_version", return_value="9.9.9")
    mocker.patch("frugalbot.clients.copilot.ensure_copilot_runtime", return_value="/cache/github-copilot-sdk/cli/9.9.9/prebuilds/win32-x64/copilot-runtime")


@pytest.fixture
def harness(mocker: MockerFixture) -> _Harness:
    sdk = _FakeSdkClient([_model_info("gpt-5"), _model_info("auto")])
    client = CopilotClient(CopilotClientConfig(name="copilot", model="gpt-5", api_key_env_var="COPILOT_GITHUB_TOKEN"))
    mocker.patch.object(client, "_create_sdk_client", return_value=sdk)
    return _Harness(client=client, sdk=sdk)


@pytest.fixture
async def conversation() -> Conversation:
    hooks = Hooks()
    conv = Conversation(hooks)
    await conv.append_system_message("System Prompt")
    await conv.append_user_message("User Prompt")
    return conv


@pytest.fixture
def tools() -> Tools:
    tools = Tools()
    tools.add(_EchoTool(_EchoConfig()))
    return tools


@pytest.fixture
def mock_bus(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("frugalbot.clients.copilot.bus.emit_and_handle", new_callable=AsyncMock)


# =============================================================================
# Module helpers
# =============================================================================


def test_ensure_copilot_runtime_with_cli_path_returns_path(fs) -> None:
    # Given
    fs.create_file("/opt/copilot-runtime")
    config = CopilotClientConfig(name="copilot", model="gpt-5", api_key_env_var="TOKEN", cli_path="/opt/copilot-runtime")

    # When
    result = ensure_copilot_runtime(config)

    # Then
    assert Path(result) == Path("/opt/copilot-runtime")


def test_ensure_copilot_runtime_disables_sdk_auto_download(fs, mocker: MockerFixture) -> None:
    # Given
    fs.create_file("/opt/copilot-runtime")
    mocker.patch.dict(os.environ, {}, clear=True)
    config = CopilotClientConfig(name="copilot", model="gpt-5", api_key_env_var="TOKEN", cli_path="/opt/copilot-runtime")

    # When
    ensure_copilot_runtime(config)

    # Then
    assert os.environ["COPILOT_SKIP_CLI_DOWNLOAD"] == "1"


def test_ensure_copilot_runtime_with_missing_cli_path_raises(fs) -> None:
    # Given
    config = CopilotClientConfig(name="copilot", model="gpt-5", api_key_env_var="TOKEN", cli_path="/opt/missing")

    # When / Then
    with pytest.raises(LLMClientError, match="cli_path does not exist"):
        ensure_copilot_runtime(config)


def test_ensure_copilot_runtime_with_env_var_returns_path(fs, mocker: MockerFixture) -> None:
    # Given
    fs.create_file("/opt/env-copilot")
    mocker.patch.dict(os.environ, {"COPILOT_CLI_PATH": "/opt/env-copilot"})
    config = CopilotClientConfig(name="copilot", model="gpt-5", api_key_env_var="TOKEN")

    # When
    result = ensure_copilot_runtime(config)

    # Then
    assert Path(result) == Path("/opt/env-copilot")


def test_ensure_copilot_runtime_with_missing_env_var_path_raises(fs, mocker: MockerFixture) -> None:
    # Given
    mocker.patch.dict(os.environ, {"COPILOT_CLI_PATH": "/opt/missing"})
    config = CopilotClientConfig(name="copilot", model="gpt-5", api_key_env_var="TOKEN")

    # When / Then
    with pytest.raises(LLMClientError, match="COPILOT_CLI_PATH does not exist"):
        ensure_copilot_runtime(config)


def test_ensure_copilot_runtime_when_on_path_returns_path(mocker: MockerFixture) -> None:
    # Given
    mocker.patch.dict(os.environ, {}, clear=True)
    mocker.patch("frugalbot.clients.copilot.shutil.which", side_effect=lambda name: "/usr/bin/copilot-runtime" if name == "copilot-runtime" else None)
    config = CopilotClientConfig(name="copilot", model="gpt-5", api_key_env_var="TOKEN")

    # When
    result = ensure_copilot_runtime(config)

    # Then
    assert result == "/usr/bin/copilot-runtime"


def test_ensure_copilot_runtime_when_cached_returns_path(mocker: MockerFixture) -> None:
    # Given
    mocker.patch.dict(os.environ, {}, clear=True)
    mocker.patch("frugalbot.clients.copilot.shutil.which", return_value=None)
    mocker.patch("frugalbot.clients.copilot._get_cached_runtime", return_value="/cache/copilot")
    config = CopilotClientConfig(name="copilot", model="gpt-5", api_key_env_var="TOKEN")

    # When
    result = ensure_copilot_runtime(config)

    # Then
    assert result == "/cache/copilot"


def test_ensure_copilot_runtime_with_no_runtime_raises_with_instructions(mocker: MockerFixture) -> None:
    # Given
    mocker.patch.dict(os.environ, {}, clear=True)
    mocker.patch("frugalbot.clients.copilot.shutil.which", return_value=None)
    mocker.patch("frugalbot.clients.copilot._get_cached_runtime", return_value=None)
    config = CopilotClientConfig(name="copilot", model="gpt-5", api_key_env_var="TOKEN")

    # When / Then
    with pytest.raises(LLMClientError, match="python -m copilot download-runtime"):
        ensure_copilot_runtime(config)


@pytest.mark.parametrize(
    ("runtime_path", "pinned_version", "expected"),
    [
        ("/home/u/.cache/github-copilot-sdk/cli/1.0.85/prebuilds/win32-x64/copilot.exe", "1.0.85", True),
        ("/custom/path/copilot", "1.0.85", False),
        ("/custom/path/copilot", None, True),
    ],
)
def test_is_pinned_runtime_checks_cache_location(runtime_path: str, pinned_version: str | None, expected: bool, mocker: MockerFixture) -> None:
    # Given
    mocker.patch("frugalbot.clients.copilot._get_pinned_cli_version", return_value=pinned_version)

    # When
    result = _is_pinned_runtime(runtime_path)

    # Then
    assert result is expected


def test_is_pinned_runtime_partial_cache_path_returns_false(mocker: MockerFixture) -> None:
    # Given
    mocker.patch("frugalbot.clients.copilot._get_pinned_cli_version", return_value="1.0.85")

    # When / Then
    assert _is_pinned_runtime("/cache/github-copilot-sdk/other/copilot") is False


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (None, "{}"),
        ('{"a": 1}', '{"a": 1}'),
        ({"a": 1}, '{"a":1}'),
    ],
)
def test_arguments_to_json_str_normalizes_values(arguments: Any, expected: str) -> None:
    # When
    result = _arguments_to_json_str(arguments)

    # Then
    assert result == expected


@pytest.mark.parametrize(
    ("desired", "supported", "expected"),
    [
        ("high", ["low", "high", "max"], "high"),
        ("max", ["low", "high"], "high"),
        ("low", ["medium", "high"], "medium"),
        ("high", ["weird"], None),
    ],
)
def test_clamp_effort_picks_nearest_supported(desired: str, supported: list[str], expected: str | None) -> None:
    # When
    result = _clamp_effort(desired, supported)

    # Then
    assert result == expected


def test_cap_transcript_with_short_text_returns_unchanged() -> None:
    # Given
    text = "short"

    # When
    result = _cap_transcript(text)

    # Then
    assert result == text


def test_cap_transcript_with_long_text_truncates_with_notice() -> None:
    # Given
    text = "a" * 50_000

    # When
    result = _cap_transcript(text)

    # Then
    assert result.startswith("[... earlier conversation history truncated ...]")
    assert len(result) < len(text)


def test_is_retryable_with_client_error_returns_false() -> None:
    # When / Then
    assert _is_retryable(LLMClientError("nope")) is False


def test_is_retryable_with_cancelled_error_returns_false() -> None:
    # When / Then
    assert _is_retryable(asyncio.CancelledError()) is False


def test_is_retryable_with_transport_error_returns_true() -> None:
    # When / Then
    assert _is_retryable(RuntimeError("boom")) is True


async def test_log_retry_emits_error_event(harness: _Harness, mock_bus: MagicMock) -> None:
    # Given
    retry_state = MagicMock()
    retry_state.args = (harness.client,)
    retry_state.outcome = None
    retry_state.next_action = None
    retry_state.attempt_number = 1

    # When
    await _log_retry(retry_state)

    # Then
    mock_bus.assert_called_once()
    assert mock_bus.call_args[0][0].message_type == MessageType.ERROR


async def test_finalize_session_with_session_schedules_disconnect() -> None:
    # Given
    session = _FakeSession()
    state = _SessionState(session=cast(Any, session), loop=asyncio.get_running_loop())

    # When
    _finalize_session(state)
    await asyncio.sleep(0.01)

    # Then
    assert session.disconnected is True


def test_finalize_session_without_session_does_nothing() -> None:
    # Given
    state = _SessionState(session=None)

    # When / Then
    _finalize_session(state)


def test_finalize_session_without_loop_does_nothing() -> None:
    # Given
    session = _FakeSession()
    state = _SessionState(session=cast(Any, session), loop=None)

    # When
    _finalize_session(state)

    # Then
    assert session.disconnected is False


def test_finalize_session_with_closed_loop_does_nothing() -> None:
    # Given
    session = _FakeSession()
    loop = asyncio.new_event_loop()
    loop.close()
    state = _SessionState(session=cast(Any, session), loop=loop)

    # When
    _finalize_session(state)

    # Then
    assert session.disconnected is False


def test_system_prompt_without_system_message_returns_empty_string() -> None:
    # Given
    conversation = Conversation(Hooks())

    # When
    result = _system_prompt(conversation)

    # Then
    assert result == ""


def test_restored_prefix_len_with_trailing_user_message_excludes_it() -> None:
    # Given
    entries: list[Any] = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]

    # When
    result = _restored_prefix_len(MagicMock(entries=entries))

    # Then
    assert result == 1


def test_restored_prefix_len_with_trailing_assistant_message_returns_length() -> None:
    # Given
    entries: list[Any] = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}, _completion("reply")]

    # When
    result = _restored_prefix_len(MagicMock(entries=entries))

    # Then
    assert result == 3


def test_render_entries_with_mixed_roles_renders_transcript() -> None:
    # Given
    entries: list[Any] = [
        {"role": "system", "content": "ignored"},
        {"role": "user", "content": "hi"},
        ("provider", _completion("hello")),
        {"role": "tool", "content": "result", "name": "echo"},
        {"role": "mystery", "content": "?"},
    ]

    # When
    result = _render_entries(entries)

    # Then
    assert "System" not in result
    assert "User: hi" in result
    assert "Assistant:\nhello" in result
    assert "Tool [echo]: result" in result
    assert "Mystery: ?" in result


def test_render_entries_with_json_tool_content_renders_yaml() -> None:
    # Given
    entries: list[Any] = [{"role": "tool", "content": '{"key": "value"}', "name": "echo"}]

    # When
    result = _render_entries(entries)

    # Then
    assert "key: value" in result


def test_render_entries_with_dict_assistant_message_renders_content() -> None:
    # Given
    entries: list[Any] = [{"role": "assistant", "content": "dict reply"}]

    # When
    result = _render_entries(entries)

    # Then
    assert result == "Assistant:\ndict reply"


def test_render_entries_with_assistant_tool_call_renders_tool_call_block() -> None:
    # Given
    message = ChatCompletionMessage(role="assistant", content="", tool_calls=[ChatCompletionMessageFunctionToolCall(id="t1", function=Function(name="echo", arguments='{"a":1}'), type="function")])
    entries: list[Any] = [("provider", ChatCompletion(id="c1", choices=[Choice(index=0, finish_reason="stop", message=message)], created=0, model="m", object="chat.completion"))]

    # When
    result = _render_entries(entries)

    # Then
    assert "<tool_call>'echo'" in result


def test_get_cached_runtime_returns_sdk_cached_path(mocker: MockerFixture) -> None:
    # Given
    mocker.patch("copilot._cli_download.get_cached_cli_path", return_value="/cache/copilot")

    # When
    result = _get_cached_runtime()

    # Then
    assert result == "/cache/copilot"


def test_get_pinned_cli_version_returns_sdk_version(mocker: MockerFixture) -> None:
    # Given
    mocker.patch("copilot._cli_version.CLI_VERSION", "9.9.9")

    # When
    result = _get_pinned_cli_version()

    # Then
    assert result == "9.9.9"


# =============================================================================
# Initialization
# =============================================================================


def test_init_with_valid_config_sets_provider_model_and_base_url(harness: _Harness) -> None:
    # Given / When (harness constructs the client)

    # Then
    assert harness.client.provider == COPILOT_PROVIDER
    assert harness.client.model == "gpt-5"
    assert harness.client.base_url == COPILOT_BASE_URL


def test_init_with_missing_runtime_raises_client_error_with_instructions(mocker: MockerFixture) -> None:
    # Given
    mocker.patch("frugalbot.clients.copilot.ensure_copilot_runtime", side_effect=LLMClientError("python -m copilot download-runtime"))
    config = CopilotClientConfig(name="copilot", model="gpt-5", api_key_env_var="TOKEN")

    # When / Then
    with pytest.raises(LLMClientError, match="download-runtime"):
        CopilotClient(config)


def test_create_sdk_client_uses_empty_mode_and_configured_storage(mocker: MockerFixture) -> None:
    # Given
    client = CopilotClient(CopilotClientConfig(name="copilot", model="gpt-5", api_key_env_var="TOKEN", base_directory="~/copilot-state"))
    mock_sdk_class = mocker.patch("frugalbot.clients.copilot.SdkCopilotClient")
    mock_for_stdio = mocker.patch("frugalbot.clients.copilot.RuntimeConnection.for_stdio", return_value="stdio-connection")
    mocker.patch.dict(os.environ, {"TOKEN": "secret"})

    # When
    result = client._create_sdk_client()

    # Then
    assert result is mock_sdk_class.return_value
    mock_sdk_class.assert_called_once_with(
        mode="empty",
        base_directory=str(Path("~/copilot-state").expanduser()),
        github_token="secret",
        working_directory=str(Path.cwd()),
        connection="stdio-connection",
    )
    mock_for_stdio.assert_called_once_with(path=client._runtime_path)


def test_create_sdk_client_without_base_directory_uses_default(mocker: MockerFixture) -> None:
    # Given
    client = CopilotClient(CopilotClientConfig(name="copilot", model="gpt-5", api_key_env_var="TOKEN"))
    mock_sdk_class = mocker.patch("frugalbot.clients.copilot.SdkCopilotClient")
    mocker.patch("frugalbot.clients.copilot.RuntimeConnection.for_stdio")

    # When
    client._create_sdk_client()

    # Then
    assert mock_sdk_class.call_args.kwargs["base_directory"] == str(DEFAULT_BASE_DIRECTORY)


# =============================================================================
# Thinking / model mapping
# =============================================================================


@pytest.mark.parametrize(
    ("level", "expected_effort"),
    [("LOW", "low"), ("MEDIUM", "high"), ("HIGH", "max")],
)
async def test_call_maps_thinking_levels_to_reasoning_effort(harness: _Harness, conversation: Conversation, tools: Tools, level: Any, expected_effort: str) -> None:
    # Given
    harness.client.thinking_level = level
    harness.sdk.model_infos = [_model_info("gpt-5", supported_efforts=["low", "high", "max"])]
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert harness.sdk.last_create_kwargs["reasoning_effort"] == expected_effort


async def test_call_when_thinking_level_none_omits_reasoning_effort(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.client.thinking_level = "NONE"
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert harness.sdk.last_create_kwargs["reasoning_effort"] is None
    assert harness.sdk.last_create_kwargs["reasoning_summary"] == "none"


async def test_call_when_model_unsupported_raises_client_error(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.model_infos = [_model_info("gpt-5")]
    harness.client.model = "not-a-model"

    # When / Then
    with pytest.raises(LLMClientError, match="not offered by GitHub Copilot"):
        await harness.client.call(conversation, tools)


async def test_call_when_mapped_effort_unsupported_clamps_and_warns(harness: _Harness, conversation: Conversation, tools: Tools, mock_bus: MagicMock) -> None:
    # Given
    harness.sdk.model_infos = [_model_info("gpt-5", supported_efforts=["low", "high"])]
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]

    # When
    await harness.client.call(conversation, tools)

    # Then
    warning_types = [call.args[0].message_type for call in mock_bus.call_args_list]
    assert MessageType.WARNING in warning_types
    assert harness.sdk.last_create_kwargs["reasoning_effort"] == "high"


async def test_call_when_model_does_not_support_reasoning_omits_and_warns(harness: _Harness, conversation: Conversation, tools: Tools, mock_bus: MagicMock) -> None:
    # Given
    harness.sdk.model_infos = [_model_info("gpt-5", supports_reasoning=False)]
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert harness.sdk.last_create_kwargs["reasoning_effort"] is None
    assert any(call.args[0].message_type == MessageType.WARNING for call in mock_bus.call_args_list)


async def test_call_when_clamped_effort_has_no_known_levels_omits_and_warns(harness: _Harness, conversation: Conversation, tools: Tools, mock_bus: MagicMock) -> None:
    # Given
    harness.sdk.model_infos = [_model_info("gpt-5", supported_efforts=["weird"])]
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert harness.sdk.last_create_kwargs["reasoning_effort"] is None
    assert any(call.args[0].message_type == MessageType.WARNING for call in mock_bus.call_args_list)


async def test_call_when_model_is_auto_skips_effort_and_passes_auto_tier(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.client.model = "auto"
    harness.client.config.auto_tier = "balance"
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="auto"))]]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert harness.sdk.last_create_kwargs["reasoning_effort"] is None
    assert harness.sdk.last_create_kwargs["capi"] == {"auto_tier": "balance"}


async def test_call_when_model_is_auto_without_auto_tier_omits_capi(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.client.model = "auto"
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="auto"))]]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert harness.sdk.last_create_kwargs["capi"] is None


async def test_call_when_reasoning_effort_override_is_set_uses_override(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.client.config.reasoning_effort = "medium"
    harness.sdk.model_infos = [_model_info("gpt-5", supported_efforts=["low", "medium", "high"])]
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert harness.sdk.last_create_kwargs["reasoning_effort"] == "medium"


# =============================================================================
# Session construction
# =============================================================================


async def test_call_creates_session_with_replace_system_prompt(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert harness.sdk.last_create_kwargs["system_message"] == {"mode": "replace", "content": "System Prompt"}


async def test_call_converts_frugalbot_tools_to_declaration_only_copilot_tools(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]

    # When
    await harness.client.call(conversation, tools)

    # Then
    copilot_tools = harness.sdk.last_create_kwargs["tools"]
    assert len(copilot_tools) == 1
    assert copilot_tools[0].name == "_echotool"
    assert copilot_tools[0].handler is None
    assert copilot_tools[0].defer == "never"
    assert copilot_tools[0].overrides_built_in_tool is True


async def test_call_registers_long_lived_event_listener(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert len(harness.sdk.session.handlers) == 1


async def test_call_uses_empty_mode_tool_filter(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert harness.sdk.started is True
    assert list(harness.sdk.last_create_kwargs["available_tools"]) == ["custom:*"]
    assert harness.sdk.last_create_kwargs["streaming"] is True


async def test_call_registers_approve_all_permission_handler(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]

    # When
    await harness.client.call(conversation, tools)

    # Then
    from copilot import PermissionHandler

    assert harness.sdk.last_create_kwargs["on_permission_request"] is PermissionHandler.approve_all


# =============================================================================
# Streaming and event handling
# =============================================================================


async def test_call_with_text_stream_emits_assistant_events_and_returns_stop_completion(harness: _Harness, conversation: Conversation, tools: Tools, mock_bus: MagicMock) -> None:
    # Given
    harness.sdk.script_queue = [
        [
            _event(AssistantMessageDeltaData(delta_content="Hel", message_id="m1")),
            _event(AssistantMessageDeltaData(delta_content="lo", message_id="m1")),
            _event(AssistantMessageData(content="Hello", message_id="m1")),
            _event(AssistantTurnEndData(turn_id="t", model="gpt-5")),
        ]
    ]

    # When
    completion = await harness.client.call(conversation, tools)

    # Then
    assert completion.choices[0].finish_reason == "stop"
    assert completion.choices[0].message.content == "Hello"
    assert mock_bus.call_count == 2


async def test_call_with_delta_then_final_does_not_duplicate_content(harness: _Harness, conversation: Conversation, tools: Tools, mock_bus: MagicMock) -> None:
    # Given
    harness.sdk.script_queue = [
        [
            _event(AssistantMessageDeltaData(delta_content="Hello", message_id="m1")),
            _event(AssistantMessageData(content="Hello", message_id="m1")),
            _event(AssistantTurnEndData(turn_id="t", model="gpt-5")),
        ]
    ]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert mock_bus.call_count == 1


async def test_call_with_final_message_emits_content_once_when_not_streamed(harness: _Harness, conversation: Conversation, tools: Tools, mock_bus: MagicMock) -> None:
    # Given
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="Final", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert mock_bus.call_count == 1
    assert mock_bus.call_args[0][0].message == "Final"


async def test_call_with_reasoning_stream_emits_thinking_events(harness: _Harness, conversation: Conversation, tools: Tools, mock_bus: MagicMock) -> None:
    # Given
    harness.sdk.script_queue = [
        [
            _event(AssistantReasoningDeltaData(delta_content="think", reasoning_id="r1")),
            _event(AssistantReasoningData(content="think", reasoning_id="r1")),
            _event(AssistantMessageData(content="answer", message_id="m1")),
            _event(AssistantTurnEndData(turn_id="t", model="gpt-5")),
        ]
    ]

    # When
    completion = await harness.client.call(conversation, tools)

    # Then
    thinking_events = [call.args[0] for call in mock_bus.call_args_list if call.args[0].message_type == MessageType.THINKING]
    assert len(thinking_events) == 1
    assert completion.choices[0].message.reasoning is not None
    assert completion.choices[0].message.reasoning.content == "think"


async def test_call_with_non_streamed_reasoning_emits_thinking_once(harness: _Harness, conversation: Conversation, tools: Tools, mock_bus: MagicMock) -> None:
    # Given
    harness.sdk.script_queue = [
        [
            _event(AssistantReasoningData(content="ponder", reasoning_id="r1")),
            _event(AssistantMessageData(content="answer", message_id="m1")),
            _event(AssistantTurnEndData(turn_id="t", model="gpt-5")),
        ]
    ]

    # When
    await harness.client.call(conversation, tools)

    # Then
    thinking_events = [call.args[0] for call in mock_bus.call_args_list if call.args[0].message_type == MessageType.THINKING]
    assert len(thinking_events) == 1


async def test_call_with_session_idle_finishes_text_turn(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="idle", message_id="m1")), _event(SessionIdleData(aborted=False))]]

    # When
    completion = await harness.client.call(conversation, tools)

    # Then
    assert completion.choices[0].message.content == "idle"


async def test_call_with_turn_retry_emits_warning(harness: _Harness, conversation: Conversation, tools: Tools, mock_bus: MagicMock) -> None:
    # Given
    harness.sdk.script_queue = [
        [
            _event(AssistantTurnRetryData(turn_id="t", model="gpt-5")),
            _event(AssistantMessageData(content="ok", message_id="m1")),
            _event(AssistantTurnEndData(turn_id="t", model="gpt-5")),
        ]
    ]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert any(call.args[0].message_type == MessageType.WARNING for call in mock_bus.call_args_list)


# =============================================================================
# Tool calls
# =============================================================================


def _tool_request_events(tool_call_id: str = "tc1", request_id: str = "r1", name: str = "echo") -> list[SessionEvent]:
    return [
        _event(AssistantMessageData(content="", message_id="m1", tool_requests=[AssistantMessageToolRequest(name=name, tool_call_id=tool_call_id, arguments={"text": "hi"})])),
        _event(ExternalToolRequestedData(request_id=request_id, session_id="s", tool_call_id=tool_call_id, tool_name=name, arguments={"text": "hi"})),
    ]


async def test_call_with_tool_request_returns_tool_calls_without_waiting_for_turn_end(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [_tool_request_events()]

    # When
    completion = await harness.client.call(conversation, tools)

    # Then
    assert completion.choices[0].finish_reason == "tool_calls"
    tool_calls = completion.choices[0].message.tool_calls
    assert tool_calls is not None
    assert isinstance(tool_calls[0], ChatCompletionMessageFunctionToolCall)
    assert tool_calls[0].id == "tc1"
    assert tool_calls[0].function.name == "echo"


async def test_call_with_parallel_tool_requests_surfaces_all_of_them(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [
        [
            _event(
                AssistantMessageData(
                    content="",
                    message_id="m1",
                    tool_requests=[
                        AssistantMessageToolRequest(name="echo", tool_call_id="tc1", arguments={"text": "a"}),
                        AssistantMessageToolRequest(name="echo", tool_call_id="tc2", arguments={"text": "b"}),
                    ],
                )
            ),
            _event(ExternalToolRequestedData(request_id="r1", session_id="s", tool_call_id="tc1", tool_name="echo", arguments={"text": "a"})),
            _event(ExternalToolRequestedData(request_id="r2", session_id="s", tool_call_id="tc2", tool_name="echo", arguments={"text": "b"})),
        ]
    ]

    # When
    completion = await harness.client.call(conversation, tools)

    # Then
    tool_calls = completion.choices[0].message.tool_calls
    assert tool_calls is not None
    assert sorted(tool_call.id for tool_call in tool_calls) == ["tc1", "tc2"]


async def test_call_with_external_tool_requested_before_message_surfaces_tool_call(harness: _Harness, conversation: Conversation, tools: Tools, mock_bus: MagicMock) -> None:
    # Given
    harness.sdk.script_queue = [
        [
            _event(ExternalToolRequestedData(request_id="r1", session_id="s", tool_call_id="tc1", tool_name="echo", arguments={"text": "hi"})),
            _event(AssistantMessageData(content="", message_id="m1", tool_requests=[AssistantMessageToolRequest(name="echo", tool_call_id="tc1", arguments={"text": "hi"})])),
        ]
    ]

    # When
    completion = await harness.client.call(conversation, tools)

    # Then
    assert completion.choices[0].message.tool_calls is not None
    assert any(call.args[0].message_type == MessageType.TOOL_CALL for call in mock_bus.call_args_list)


async def test_call_delivers_tool_result_via_handle_pending_tool_call(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [_tool_request_events()]
    await harness.client.call(conversation, tools)
    assistant_message = ChatCompletionMessage(
        role="assistant",
        content=None,
        tool_calls=[ChatCompletionMessageFunctionToolCall(id="tc1", function=Function(name="echo", arguments='{"text": "hi"}'), type="function")],
    )
    conversation.append_assistant_message(
        "copilot",
        ChatCompletion(id="c2", choices=[Choice(index=0, finish_reason="tool_calls", message=assistant_message)], created=0, model="gpt-5", object="chat.completion"),
    )
    await conversation.append_tool_message("echo", "hi", "text", "tc1", None)
    harness.sdk.session.scripted_events = [_event(AssistantMessageData(content="Done", message_id="m2")), _event(AssistantTurnEndData(turn_id="t2", model="gpt-5"))]

    # When
    completion = await harness.client.call(conversation, tools)

    # Then
    pending = harness.sdk.sessions[0].rpc.tools.pending_calls
    assert len(pending) == 1
    assert pending[0].request_id == "r1"
    assert pending[0].result is not None
    assert pending[0].result.text_result_for_llm == "hi"
    assert completion.choices[0].message.content == "Done"


async def test_call_ignores_stale_turn_end_emitted_when_tool_result_is_resolved(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given: after a tool result is resolved, the runtime closes the previously
    # suspended turn before starting the resumed one (assistant.turn_end, then
    # assistant.turn_start). The stale turn_end must not terminate the new turn.
    harness.sdk.script_queue = [_tool_request_events()]
    await harness.client.call(conversation, tools)
    assistant_message = ChatCompletionMessage(
        role="assistant",
        content=None,
        tool_calls=[ChatCompletionMessageFunctionToolCall(id="tc1", function=Function(name="echo", arguments='{"text": "hi"}'), type="function")],
    )
    conversation.append_assistant_message(
        "copilot",
        ChatCompletion(id="c2", choices=[Choice(index=0, finish_reason="tool_calls", message=assistant_message)], created=0, model="gpt-5", object="chat.completion"),
    )
    await conversation.append_tool_message("echo", "hi", "text", "tc1", None)
    harness.sdk.session.scripted_events = [
        _event(AssistantTurnEndData(turn_id="t1", model="gpt-5")),
        _event(AssistantTurnStartData(turn_id="t2", model="gpt-5")),
        _event(AssistantMessageData(content="Done", message_id="m2")),
        _event(AssistantTurnEndData(turn_id="t2", model="gpt-5")),
    ]

    # When
    completion = await harness.client.call(conversation, tools)

    # Then
    assert completion.choices[0].finish_reason == "stop"
    assert completion.choices[0].message.content == "Done"


async def test_call_ignores_stale_turn_end_without_turn_start_until_output_arrives(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given: even without an assistant.turn_start, a turn_end that precedes any
    # output belongs to the suspended turn and must be skipped.
    harness.sdk.script_queue = [_tool_request_events()]
    await harness.client.call(conversation, tools)
    assistant_message = ChatCompletionMessage(
        role="assistant",
        content=None,
        tool_calls=[ChatCompletionMessageFunctionToolCall(id="tc1", function=Function(name="echo", arguments='{"text": "hi"}'), type="function")],
    )
    conversation.append_assistant_message(
        "copilot",
        ChatCompletion(id="c2", choices=[Choice(index=0, finish_reason="tool_calls", message=assistant_message)], created=0, model="gpt-5", object="chat.completion"),
    )
    await conversation.append_tool_message("echo", "hi", "text", "tc1", None)
    harness.sdk.session.scripted_events = [
        _event(AssistantTurnEndData(turn_id="t1", model="gpt-5")),
        _event(AssistantMessageData(content="Done", message_id="m2")),
        _event(AssistantTurnEndData(turn_id="t2", model="gpt-5")),
    ]

    # When
    completion = await harness.client.call(conversation, tools)

    # Then
    assert completion.choices[0].message.content == "Done"


# =============================================================================
# Delivery / resume
# =============================================================================


async def test_call_with_no_new_entries_sends_empty_message_batch(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="first", message_id="m1")), _event(AssistantTurnEndData(turn_id="t1", model="gpt-5"))]]
    await harness.client.call(conversation, tools)
    harness.sdk.session.scripted_events = [_event(AssistantMessageData(content="second", message_id="m2")), _event(AssistantTurnEndData(turn_id="t2", model="gpt-5"))]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert harness.sdk.sessions[0].rpc.sent_batches[-1].messages == []


async def test_send_prompts_with_multiple_prompts_sends_batch(harness: _Harness) -> None:
    # Given
    session = _FakeSession()
    prompts = ["First", "Second"]

    # When
    await harness.client._send_prompts(cast(Any, session), prompts)

    # Then
    assert [item.prompt for item in session.rpc.sent_batches[0].messages] == ["First", "Second"]


async def test_send_prompts_with_single_prompt_uses_send(harness: _Harness) -> None:
    # Given
    session = _FakeSession()

    # When
    await harness.client._send_prompts(cast(Any, session), ["Only"])

    # Then
    assert session.sent_prompts == ["Only"]


async def test_call_after_new_conversation_creates_new_session(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [
        [_event(AssistantMessageData(content="first", message_id="m1")), _event(AssistantTurnEndData(turn_id="t1", model="gpt-5"))],
        [_event(AssistantMessageData(content="second", message_id="m2")), _event(AssistantTurnEndData(turn_id="t2", model="gpt-5"))],
    ]
    await harness.client.call(conversation, tools)
    new_conversation = Conversation(Hooks())
    await new_conversation.append_system_message("New System")
    await new_conversation.append_user_message("New User")

    # When
    await harness.client.call(new_conversation, tools)

    # Then
    assert len(harness.sdk.sessions) == 2
    assert harness.sdk.sessions[1].sent_prompts == ["New User"]


async def test_call_with_loaded_conversation_injects_transcript_into_system_message(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    conversation.append_assistant_message("copilot", _completion("prior reply"))
    await conversation.append_user_message("second")
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="second reply", message_id="m2")), _event(AssistantTurnEndData(turn_id="t2", model="gpt-5"))]]

    # When
    await harness.client.call(conversation, tools)

    # Then
    system_message = harness.sdk.last_create_kwargs["system_message"]["content"]
    assert "Restored Conversation Context" in system_message
    assert "User: User Prompt" in system_message
    assert "prior reply" in system_message
    assert harness.sdk.session.sent_prompts == ["second"]


async def test_call_when_switching_client_mid_conversation_restores_prior_turns(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    conversation.append_assistant_message("other", _completion("earlier"))
    await conversation.append_user_message("follow up")
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="answer", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]

    # When
    completion = await harness.client.call(conversation, tools)

    # Then
    assert completion.choices[0].message.content == "answer"
    assert "earlier" in harness.sdk.last_create_kwargs["system_message"]["content"]


# =============================================================================
# Reconciliation
# =============================================================================


async def test_call_when_thinking_level_changed_applies_set_model_on_next_call(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.model_infos = [_model_info("gpt-5", supported_efforts=["low", "high", "max"])]
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="first", message_id="m1")), _event(AssistantTurnEndData(turn_id="t1", model="gpt-5"))]]
    await harness.client.call(conversation, tools)
    harness.client.thinking_level = "LOW"
    harness.sdk.session.scripted_events = [_event(AssistantMessageData(content="second", message_id="m2")), _event(AssistantTurnEndData(turn_id="t2", model="gpt-5"))]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert harness.sdk.session.set_model_calls == [{"model": "gpt-5", "reasoning_effort": "low"}]


async def test_call_when_nothing_changed_does_not_call_set_model(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="first", message_id="m1")), _event(AssistantTurnEndData(turn_id="t1", model="gpt-5"))]]
    await harness.client.call(conversation, tools)
    harness.sdk.session.scripted_events = [_event(AssistantMessageData(content="second", message_id="m2")), _event(AssistantTurnEndData(turn_id="t2", model="gpt-5"))]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert harness.sdk.session.set_model_calls == []


async def test_call_reuses_cached_model_list_across_calls(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="first", message_id="m1")), _event(AssistantTurnEndData(turn_id="t1", model="gpt-5"))]]
    await harness.client.call(conversation, tools)
    harness.sdk.session.scripted_events = [_event(AssistantMessageData(content="second", message_id="m2")), _event(AssistantTurnEndData(turn_id="t2", model="gpt-5"))]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert harness.sdk.list_models_calls == 1


# =============================================================================
# Usage and status
# =============================================================================


async def test_call_maps_assistant_usage_to_completion_usage(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [
        [
            _event(AssistantMessageData(content="ok", message_id="m1")),
            _event(AssistantUsageData(model="gpt-5", input_tokens=10, output_tokens=5, cache_read_tokens=2, reasoning_tokens=1)),
            _event(AssistantTurnEndData(turn_id="t", model="gpt-5")),
        ]
    ]

    # When
    completion = await harness.client.call(conversation, tools)

    # Then
    usage = completion.usage
    assert usage is not None
    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 5
    assert usage.total_tokens == 15
    assert usage.prompt_tokens_details is not None
    assert usage.prompt_tokens_details.cached_tokens == 2
    assert usage.completion_tokens_details is not None
    assert usage.completion_tokens_details.reasoning_tokens == 1


async def test_call_without_usage_falls_back_to_message_tokens(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [
        [
            _event(AssistantMessageData(content="ok", message_id="m1", output_tokens=7)),
            _event(SessionUsageInfoData(current_tokens=42, messages_length=2, token_limit=1000)),
            _event(AssistantTurnEndData(turn_id="t", model="gpt-5")),
        ]
    ]

    # When
    completion = await harness.client.call(conversation, tools)

    # Then
    usage = completion.usage
    assert usage is not None
    assert usage.prompt_tokens == 42
    assert usage.completion_tokens == 7
    assert usage.total_tokens == 49


async def test_call_without_any_usage_returns_none_usage(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]

    # When
    completion = await harness.client.call(conversation, tools)

    # Then
    assert completion.usage is None


async def test_call_maps_length_finish_reason(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [
        [
            _event(AssistantMessageData(content="ok", message_id="m1")),
            _event(AssistantUsageData(model="gpt-5", input_tokens=1, output_tokens=1, finish_reason="length")),
            _event(AssistantTurnEndData(turn_id="t", model="gpt-5")),
        ]
    ]

    # When
    completion = await harness.client.call(conversation, tools)

    # Then
    assert completion.choices[0].finish_reason == "length"


async def test_call_maps_content_filter_finish_reason(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [
        [
            _event(AssistantMessageData(content="ok", message_id="m1")),
            _event(AssistantUsageData(model="gpt-5", input_tokens=1, output_tokens=1, content_filter_triggered=True)),
            _event(AssistantTurnEndData(turn_id="t", model="gpt-5")),
        ]
    ]

    # When
    completion = await harness.client.call(conversation, tools)

    # Then
    assert completion.choices[0].finish_reason == "content_filter"


# =============================================================================
# Errors, cancellation, cleanup
# =============================================================================


async def test_call_with_failed_turn_raises_client_error(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [[_event(SessionErrorData(error_type="server", message="kaboom"))]]

    # When / Then
    with pytest.raises(LLMClientError, match="kaboom"):
        await harness.client.call(conversation, tools)


async def test_call_when_cancelled_aborts_session_and_propagates(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [[_event(SessionIdleData(aborted=True))]]

    # When / Then
    with pytest.raises(asyncio.CancelledError):
        await harness.client.call(conversation, tools)
    assert harness.sdk.session.aborted is True


async def test_call_drains_stale_events_before_sending(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="first", message_id="m0")), _event(AssistantTurnEndData(turn_id="t0", model="gpt-5"))]]
    await harness.client.call(conversation, tools)
    session = harness.sdk.session
    session.handlers[0](_event(AssistantMessageData(content="stale", message_id="m0")))
    session.scripted_events = [_event(AssistantMessageData(content="fresh", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]

    # When
    completion = await harness.client.call(conversation, tools)

    # Then
    assert completion.choices[0].message.content == "fresh"


async def test_close_disconnects_sessions_stops_sdk_and_is_idempotent(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]
    await harness.client.call(conversation, tools)
    session = harness.sdk.session

    # When
    await harness.client.close()
    await harness.client.close()

    # Then
    assert session.disconnected is True
    assert session.handlers == []
    assert harness.sdk.stopped is True


async def test_close_without_started_sdk_does_not_raise(harness: _Harness) -> None:
    # When / Then
    await harness.client.close()


async def test_close_when_session_disconnect_fails_is_swallowed(harness: _Harness, conversation: Conversation, tools: Tools, mocker: MockerFixture) -> None:
    # Given
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]
    await harness.client.call(conversation, tools)
    mocker.patch.object(harness.sdk.session, "disconnect", side_effect=RuntimeError("already gone"))

    # When / Then
    await harness.client.close()


async def test_call_when_abort_fails_still_resets_state(harness: _Harness, conversation: Conversation, tools: Tools, mocker: MockerFixture) -> None:
    # Given
    harness.sdk.script_queue = [[_event(SessionIdleData(aborted=True))]]
    mocker.patch.object(_FakeSession, "abort", side_effect=RuntimeError("cannot abort"))

    # When / Then
    with pytest.raises(asyncio.CancelledError):
        await harness.client.call(conversation, tools)


async def test_supports_thinking_returns_cached_capability_without_await(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.model_infos = [_model_info("gpt-5", supports_reasoning=True)]
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]
    await harness.client.call(conversation, tools)

    # When
    result = harness.client.supports_thinking

    # Then
    assert result is True


async def test_call_updates_supports_thinking_from_model_capabilities(harness: _Harness, conversation: Conversation, tools: Tools) -> None:
    # Given
    harness.sdk.model_infos = [_model_info("gpt-5", supports_reasoning=False)]
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="ok", message_id="m1")), _event(AssistantTurnEndData(turn_id="t", model="gpt-5"))]]

    # When
    await harness.client.call(conversation, tools)

    # Then
    assert harness.client.supports_thinking is False


async def test_call_when_runtime_not_pinned_emits_warning_once(harness: _Harness, conversation: Conversation, tools: Tools, mock_bus: MagicMock, mocker: MockerFixture) -> None:
    # Given
    harness.client._runtime_path = "/custom/copilot"
    mocker.patch("frugalbot.clients.copilot._get_pinned_cli_version", return_value="1.0.85")
    harness.sdk.script_queue = [[_event(AssistantMessageData(content="first", message_id="m1")), _event(AssistantTurnEndData(turn_id="t1", model="gpt-5"))]]

    # When
    await harness.client.call(conversation, tools)
    harness.sdk.session.scripted_events = [_event(AssistantMessageData(content="second", message_id="m2")), _event(AssistantTurnEndData(turn_id="t2", model="gpt-5"))]
    await harness.client.call(conversation, tools)

    # Then
    warnings = [call for call in mock_bus.call_args_list if isinstance(call.args[0], MessageEvent) and call.args[0].message_type == MessageType.WARNING]
    assert len(warnings) == 1


async def test_two_conversations_do_not_share_session_state(harness: _Harness, tools: Tools) -> None:
    # Given
    first = Conversation(Hooks())
    await first.append_system_message("System One")
    await first.append_user_message("One")
    second = Conversation(Hooks())
    await second.append_system_message("System Two")
    await second.append_user_message("Two")
    harness.sdk.script_queue = [
        [_event(AssistantMessageData(content="one", message_id="m1")), _event(AssistantTurnEndData(turn_id="t1", model="gpt-5"))],
        [_event(AssistantMessageData(content="two", message_id="m2")), _event(AssistantTurnEndData(turn_id="t2", model="gpt-5"))],
    ]

    # When
    await harness.client.call(first, tools)
    await harness.client.call(second, tools)

    # Then
    assert len(harness.sdk.sessions) == 2
    assert harness.sdk.sessions[0].sent_prompts == ["One"]
    assert harness.sdk.sessions[1].sent_prompts == ["Two"]
