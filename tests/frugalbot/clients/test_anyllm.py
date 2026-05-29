import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import tenacity
from any_llm import LLMProvider
from any_llm.types.completion import CompletionUsage

from frugalbot.clients.anyllm import AnyLLMClient, AnyLLMConfig, ProviderModels
from frugalbot.events import MessageMarkup, MessageType
from frugalbot.tools.base import Tools

# --- Mocks and Helpers ---


class MockChunk:
    def __init__(self, id="id", model="model", created=123, choices=None, usage=None):
        self.id = id
        self.model = model
        self.created = created
        self.choices = choices or []
        self.usage = usage


class MockChoice:
    def __init__(self, delta=None, finish_reason=None):
        self.delta = delta
        self.finish_reason = finish_reason
        self.index = 0


class MockDelta:
    def __init__(self, content=None, reasoning=None, tool_calls=None):
        self.content = content
        self.reasoning = reasoning
        self.tool_calls = tool_calls


class MockReasoningDelta:
    def __init__(self, content):
        self.content = content


class MockToolCallDelta:
    def __init__(self, index, id=None, function=None):
        self.index = index
        self.id = id
        self.function = function


class MockFunctionDelta:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


def make_config(**kwargs) -> AnyLLMConfig:
    defaults = {
        "name": "test",
        "provider": LLMProvider.OPENAI,
        "model": "gpt-4",
        "api_key_env_var": "ANY_LLM_API_KEY",
        "base_url": "https://api.openai.com/v1",
    }
    defaults.update(kwargs)
    return AnyLLMConfig(**defaults)


@pytest.fixture
def mock_conversation():
    conv = MagicMock()
    conv.messages = [{"role": "user", "content": "hello"}]
    return conv


@pytest.fixture
def mock_tools():
    tools = Tools()
    return tools


@pytest.fixture
def client():
    config = make_config()
    with patch("os.getenv", return_value="fake-key"), patch("any_llm.AnyLLM.create") as mock_create:
        mock_create.return_value = MagicMock()
        client = AnyLLMClient(config)
        yield client


async def setup_mock_completion(client, chunks):
    async def mock_acompletion(**kwargs):
        for c in chunks:
            yield c

    client.client.acompletion = AsyncMock(side_effect=mock_acompletion)


# --- Tests: Initialization ---


async def test_init_with_valid_config_sets_model():
    # Given
    config = make_config(model="gpt-4o")

    # When
    with patch("os.getenv", return_value="fake-key"), patch("any_llm.AnyLLM.create"):
        client = AnyLLMClient(config)

    # Then
    assert client.model == "gpt-4o"


async def test_init_with_valid_config_calls_create_with_correct_args():
    # Given
    config = make_config()

    # When
    with patch("os.getenv", return_value="fake-key") as mock_getenv, patch("any_llm.AnyLLM.create") as mock_create:
        AnyLLMClient(config)

    # Then
    mock_getenv.assert_called_once_with("ANY_LLM_API_KEY")
    mock_create.assert_called_once_with(provider=LLMProvider.OPENAI, api_key="fake-key", api_base="https://api.openai.com/v1")


async def test_init_with_missing_api_key_calls_create_with_none():
    # Given
    config = make_config()

    # When
    with patch("os.getenv", return_value=None), patch("any_llm.AnyLLM.create") as mock_create:
        AnyLLMClient(config)

    # Then
    mock_create.assert_called_once_with(provider=LLMProvider.OPENAI, api_key=None, api_base="https://api.openai.com/v1")


async def test_init_with_no_base_url_passes_none():
    # Given
    config = make_config(base_url=None)

    # When
    with patch("os.getenv", return_value="fake-key"), patch("any_llm.AnyLLM.create") as mock_create:
        AnyLLMClient(config)

    # Then
    mock_create.assert_called_once_with(provider=LLMProvider.OPENAI, api_key="fake-key", api_base=None)


async def test_init_sets_provider_string():
    # Given
    config = make_config(provider=LLMProvider.OPENAI)

    # When
    with patch("os.getenv", return_value="fake-key"), patch("any_llm.AnyLLM.create"):
        client = AnyLLMClient(config)

    # Then
    assert client.provider == "openai"


async def test_init_sets_base_url_property():
    # Given
    config = make_config(base_url="https://custom.api.com/v1")

    # When
    with patch("os.getenv", return_value="fake-key"), patch("any_llm.AnyLLM.create"):
        client = AnyLLMClient(config)

    # Then
    assert client.base_url == "https://custom.api.com/v1"


async def test_init_with_none_base_url_sets_empty_string():
    # Given
    config = make_config(base_url=None)

    # When
    with patch("os.getenv", return_value="fake-key"), patch("any_llm.AnyLLM.create"):
        client = AnyLLMClient(config)

    # Then
    assert client.base_url == ""


async def test_init_sets_supports_thinking_to_true():
    # Given
    config = make_config()

    # When
    with patch("os.getenv", return_value="fake-key"), patch("any_llm.AnyLLM.create"):
        client = AnyLLMClient(config)

    # Then
    assert client.supports_thinking is True


# --- Tests: Basic Completion ---


async def test_call_with_basic_completion_returns_correct_response(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(choices=[MockChoice(delta=MockDelta(content="Hello "))]),
        MockChunk(choices=[MockChoice(delta=MockDelta(content="world!"))]),
        MockChunk(choices=[MockChoice(delta=MockDelta(content=""), finish_reason="stop")]),
    ]
    await setup_mock_completion(client, chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].message.content == "Hello world!"


async def test_call_with_basic_completion_emits_assistant_events(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(choices=[MockChoice(delta=MockDelta(content="Hello "))]),
        MockChunk(choices=[MockChoice(delta=MockDelta(content="world!"))]),
        MockChunk(choices=[MockChoice(delta=MockDelta(content=""), finish_reason="stop")]),
    ]
    await setup_mock_completion(client, chunks)

    # When
    with patch("frugalbot.clients.anyllm.bus.emit_and_handle", new_callable=AsyncMock) as mock_emit:
        await client.call(mock_conversation, mock_tools)

    # Then
    assert mock_emit.call_count == 2


# --- Tests: Reasoning / Thinking ---


async def test_call_with_reasoning_returns_reasoning_and_content(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(choices=[MockChoice(delta=MockDelta(reasoning=MockReasoningDelta("Thinking...")))]),
        MockChunk(choices=[MockChoice(delta=MockDelta(content="Answer!"))]),
    ]
    await setup_mock_completion(client, chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].message.reasoning.content == "Thinking..."


async def test_call_with_reasoning_emits_thinking_and_assistant_events(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(choices=[MockChoice(delta=MockDelta(reasoning=MockReasoningDelta("Thinking...")))]),
        MockChunk(choices=[MockChoice(delta=MockDelta(content="Answer!"))]),
    ]
    await setup_mock_completion(client, chunks)

    # When
    with patch("frugalbot.clients.anyllm.bus.emit_and_handle", new_callable=AsyncMock) as mock_emit:
        await client.call(mock_conversation, mock_tools)

    # Then
    assert mock_emit.call_count == 2


# --- Tests: Mixed Content ---


async def test_call_with_mixed_content_returns_concatenated_results(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(choices=[MockChoice(delta=MockDelta(reasoning=MockReasoningDelta("T1"), content="C1"))]),
        MockChunk(choices=[MockChoice(delta=MockDelta(reasoning=MockReasoningDelta("T2"), content="C2"))]),
    ]
    await setup_mock_completion(client, chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].message.content == "C1C2"


async def test_call_with_mixed_content_emits_multiple_events(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(choices=[MockChoice(delta=MockDelta(reasoning=MockReasoningDelta("T1"), content="C1"))]),
        MockChunk(choices=[MockChoice(delta=MockDelta(reasoning=MockReasoningDelta("T2"), content="C2"))]),
    ]
    await setup_mock_completion(client, chunks)

    # When
    with patch("frugalbot.clients.anyllm.bus.emit_and_handle", new_callable=AsyncMock) as mock_emit:
        await client.call(mock_conversation, mock_tools)

    # Then
    assert mock_emit.call_count == 4


# --- Tests: Usage ---


async def test_call_with_usage_metadata_returns_usage(client, mock_conversation, mock_tools):
    # Given
    usage = CompletionUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
    chunks = [
        MockChunk(choices=[MockChoice(delta=MockDelta(content="Hi"))]),
        MockChunk(choices=[MockChoice(delta=MockDelta(content=""))], usage=usage),
    ]
    await setup_mock_completion(client, chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.usage == usage


# --- Tests: Tool Calls ---


async def test_call_with_split_tool_call_returns_combined_tool_call(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(choices=[MockChoice(delta=MockDelta(tool_calls=[MockToolCallDelta(index=0, id="call_1", function=MockFunctionDelta(name="get_weather"))]))]),
        MockChunk(choices=[MockChoice(delta=MockDelta(tool_calls=[MockToolCallDelta(index=0, function=MockFunctionDelta(arguments='{"city": "Lon'))]))]),
        MockChunk(choices=[MockChoice(delta=MockDelta(tool_calls=[MockToolCallDelta(index=0, function=MockFunctionDelta(arguments='don"}'))]))]),
    ]
    await setup_mock_completion(client, chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].message.tool_calls[0].function.arguments == '{"city": "London"}'


async def test_call_with_multiple_tool_calls_returns_all_calls(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(
            choices=[
                MockChoice(
                    delta=MockDelta(
                        tool_calls=[
                            MockToolCallDelta(index=0, id="call_1", function=MockFunctionDelta(name="tool1")),
                            MockToolCallDelta(index=1, id="call_2", function=MockFunctionDelta(name="tool2")),
                        ]
                    )
                )
            ]
        ),
        MockChunk(
            choices=[
                MockChoice(
                    delta=MockDelta(
                        tool_calls=[
                            MockToolCallDelta(index=0, function=MockFunctionDelta(arguments="arg1")),
                            MockToolCallDelta(index=1, function=MockFunctionDelta(arguments="arg2")),
                        ]
                    )
                )
            ]
        ),
    ]
    await setup_mock_completion(client, chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert len(result.choices[0].message.tool_calls) == 2


async def test_call_with_tools_passes_schemas_to_acompletion(client, mock_conversation, mock_tools):
    # Given
    mock_tool = MagicMock()
    mock_tool.get_schema.return_value = {"type": "function", "function": {"name": "test_tool"}}
    mock_tools._register_tool("test_tool", mock_tool)

    chunks = [MockChunk(choices=[MockChoice(delta=MockDelta(content=""))])]

    async def mock_acompletion(**kwargs):
        for c in chunks:
            yield c

    client.client.acompletion = AsyncMock(side_effect=mock_acompletion)

    # When
    await client.call(mock_conversation, mock_tools)

    # Then
    client.client.acompletion.assert_called_once()
    call_kwargs = cast(AsyncMock, client.client.acompletion).call_args.kwargs
    assert call_kwargs["tools"] == [{"type": "function", "function": {"name": "test_tool"}}]


async def test_call_with_no_tools_passes_empty_list(client, mock_conversation, mock_tools):
    # Given
    chunks = [MockChunk(choices=[MockChoice(delta=MockDelta(content="Hi"))])]
    await setup_mock_completion(client, chunks)

    # When
    await client.call(mock_conversation, mock_tools)

    # Then
    call_kwargs = cast(AsyncMock, client.client.acompletion).call_args.kwargs
    assert call_kwargs["tools"] == []


# --- Tests: Thinking Level ---


@pytest.mark.parametrize("level", ["HIGH", "MEDIUM", "LOW", "NONE"])
async def test_call_with_none_thinking_passes_correct_reasoning_effort(level, client, mock_conversation, mock_tools):
    # Given
    chunks = [MockChunk(choices=[MockChoice(delta=MockDelta(content="Hi"))])]
    await setup_mock_completion(client, chunks)
    client.thinking_level = level

    # When
    await client.call(mock_conversation, mock_tools)

    # Then
    call_kwargs = cast(AsyncMock, client.client.acompletion).call_args.kwargs
    if level == "NONE":
        assert call_kwargs["reasoning_effort"] is None
    else:
        assert call_kwargs["reasoning_effort"] == level.lower()


async def test_call_with_xhigh_enabled_and_matching_model_passes_xhigh():
    # Given
    provider_models = [ProviderModels(provider="openai", models=["gpt-4"])]
    config = make_config(use_xhigh_not_high=True, xhigh_provider_models=provider_models)
    with patch("os.getenv", return_value="fake-key"), patch("any_llm.AnyLLM.create") as mock_create:
        mock_create.return_value = MagicMock()
        client = AnyLLMClient(config)

    chunks = [MockChunk(choices=[MockChoice(delta=MockDelta(content="Hi"))])]
    await setup_mock_completion(client, chunks)
    mock_conversation = MagicMock()
    mock_conversation.messages = [{"role": "user", "content": "hello"}]
    mock_tools = Tools()
    client.thinking_level = "HIGH"

    # When
    await client.call(mock_conversation, mock_tools)

    # Then
    call_kwargs = cast(AsyncMock, client.client.acompletion).call_args.kwargs
    assert call_kwargs["reasoning_effort"] == "xhigh"


async def test_call_with_xhigh_enabled_but_not_high_level_passes_low():
    # Given
    provider_models = [ProviderModels(provider="openai", models=["gpt-4"])]
    config = make_config(use_xhigh_not_high=True, xhigh_provider_models=provider_models)
    with patch("os.getenv", return_value="fake-key"), patch("any_llm.AnyLLM.create") as mock_create:
        mock_create.return_value = MagicMock()
        client = AnyLLMClient(config)

    chunks = [MockChunk(choices=[MockChoice(delta=MockDelta(content="Hi"))])]
    await setup_mock_completion(client, chunks)
    mock_conversation = MagicMock()
    mock_conversation.messages = [{"role": "user", "content": "hello"}]
    mock_tools = Tools()
    client.thinking_level = "LOW"

    # When
    await client.call(mock_conversation, mock_tools)

    # Then
    call_kwargs = cast(AsyncMock, client.client.acompletion).call_args.kwargs
    assert call_kwargs["reasoning_effort"] == "low"


async def test_call_with_xhigh_enabled_but_model_not_in_list_passes_high():
    # Given
    provider_models = [ProviderModels(provider="openai", models=["gpt-5"])]
    config = make_config(use_xhigh_not_high=True, xhigh_provider_models=provider_models)
    with patch("os.getenv", return_value="fake-key"), patch("any_llm.AnyLLM.create") as mock_create:
        mock_create.return_value = MagicMock()
        client = AnyLLMClient(config)

    chunks = [MockChunk(choices=[MockChoice(delta=MockDelta(content="Hi"))])]
    await setup_mock_completion(client, chunks)
    mock_conversation = MagicMock()
    mock_conversation.messages = [{"role": "user", "content": "hello"}]
    mock_tools = Tools()
    client.thinking_level = "HIGH"

    # When
    await client.call(mock_conversation, mock_tools)

    # Then
    call_kwargs = cast(AsyncMock, client.client.acompletion).call_args.kwargs
    assert call_kwargs["reasoning_effort"] == "high"


# --- Tests: Event Emission ---


async def test_call_with_content_emits_event_with_markdown_markup(client, mock_conversation, mock_tools):
    # Given
    chunks = [MockChunk(choices=[MockChoice(delta=MockDelta(content="Hello"))])]
    await setup_mock_completion(client, chunks)

    # When
    with patch("frugalbot.clients.anyllm.bus.emit_and_handle", new_callable=AsyncMock) as mock_emit:
        await client.call(mock_conversation, mock_tools)

    # Then
    event = mock_emit.call_args[0][0]
    assert event.message_markup == MessageMarkup.MARKDOWN


async def test_call_passes_stream_true_and_include_usage(client, mock_conversation, mock_tools):
    # Given
    chunks = [MockChunk(choices=[MockChoice(delta=MockDelta(content="Hi"))])]
    await setup_mock_completion(client, chunks)

    # When
    await client.call(mock_conversation, mock_tools)

    # Then
    call_kwargs = cast(AsyncMock, client.client.acompletion).call_args.kwargs
    assert call_kwargs["stream"] is True
    assert call_kwargs["stream_options"] == {"include_usage": True}


# --- Tests: Retries ---


async def test_call_with_transient_failures_eventually_returns_success(client, mock_conversation, mock_tools):
    # Given
    fail_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal fail_count
        fail_count += 1
        if fail_count <= 3:
            raise TimeoutError("Timeout!")
        yield MockChunk(choices=[MockChoice(delta=MockDelta(content="Success"))])

    client.client.acompletion = AsyncMock(side_effect=mock_acompletion)

    # When
    with patch("frugalbot.clients.anyllm.bus.emit_and_handle", new_callable=AsyncMock), patch("tenacity.nap.time.sleep", return_value=None), patch("asyncio.sleep", return_value=None):
        result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].message.content == "Success"


async def test_call_with_transient_failures_emits_error_events(client, mock_conversation, mock_tools):
    # Given
    fail_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal fail_count
        fail_count += 1
        if fail_count <= 3:
            raise TimeoutError("Timeout!")
        yield MockChunk(choices=[MockChoice(delta=MockDelta(content="Success"))])

    client.client.acompletion = AsyncMock(side_effect=mock_acompletion)

    # When
    with patch("frugalbot.clients.anyllm.bus.emit_and_handle", new_callable=AsyncMock) as mock_emit:
        with patch("tenacity.nap.time.sleep", return_value=None), patch("asyncio.sleep", return_value=None):
            await client.call(mock_conversation, mock_tools)

    # Then
    error_events = [call[0][0] for call in mock_emit.call_args_list if call[0][0].message_type == MessageType.ERROR]
    assert len(error_events) == 3


async def test_call_with_permanent_failure_raises_retry_error(client, mock_conversation, mock_tools):
    # Given
    async def mock_acompletion(**kwargs):
        raise TimeoutError("Permanent Failure")

    client.client.acompletion = AsyncMock(side_effect=mock_acompletion)

    # When
    with patch("frugalbot.clients.anyllm.bus.emit_and_handle", new_callable=AsyncMock):
        with patch("tenacity.nap.time.sleep", return_value=None), patch("asyncio.sleep", return_value=None):
            with pytest.raises(tenacity.RetryError):
                await client.call(mock_conversation, mock_tools)

    # Then
    assert client.client.acompletion.call_count == 20


async def test_call_with_cancelled_error_does_not_retry(client, mock_conversation, mock_tools):
    # Given
    async def mock_acompletion(**kwargs):
        raise asyncio.CancelledError()

    client.client.acompletion = AsyncMock(side_effect=mock_acompletion)

    # When / Then
    with patch("tenacity.nap.time.sleep", return_value=None), patch("asyncio.sleep", return_value=None):
        with pytest.raises(asyncio.CancelledError):
            await client.call(mock_conversation, mock_tools)

    # Then
    assert client.client.acompletion.call_count == 1


# --- Tests: Edge Cases ---


async def test_call_with_empty_stream_returns_empty_assistant_response(client, mock_conversation, mock_tools):
    # Given
    async def mock_acompletion(**kwargs):
        if False:
            yield

    client.client.acompletion = AsyncMock(side_effect=mock_acompletion)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].message.content is None


async def test_call_with_null_finish_reason_defaults_to_stop(client, mock_conversation, mock_tools):
    # Given
    chunks = [MockChunk(choices=[MockChoice(delta=MockDelta(content="Hi"), finish_reason=None)])]
    await setup_mock_completion(client, chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].finish_reason == "stop"


async def test_call_passes_extra_body_to_acompletion():
    # Given
    config = make_config(extra_body={"custom_param": "value"})
    with patch("os.getenv", return_value="fake-key"), patch("any_llm.AnyLLM.create") as mock_create:
        mock_create.return_value = MagicMock()
        client = AnyLLMClient(config)

    chunks = [MockChunk(choices=[MockChoice(delta=MockDelta(content="Hi"))])]
    await setup_mock_completion(client, chunks)
    mock_conversation = MagicMock()
    mock_conversation.messages = [{"role": "user", "content": "hello"}]
    mock_tools = Tools()

    # When
    await client.call(mock_conversation, mock_tools)

    # Then
    call_kwargs = cast(AsyncMock, client.client.acompletion).call_args.kwargs
    assert call_kwargs["extra_body"] == {"custom_param": "value"}
