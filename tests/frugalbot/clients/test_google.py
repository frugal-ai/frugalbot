from unittest.mock import AsyncMock, MagicMock, patch

import orjson as json
import pytest
import tenacity

from frugalbot.clients.google import GoogleClient
from frugalbot.events import MessageMarkup, MessageType

# --- Mocks and Helpers (Gemini Specific) ---


class MockFunctionCall:
    def __init__(self, name=None, args=None, id=None):
        self.name = name
        self.args = args or {}
        if id:
            self.id = id


class MockPart:
    def __init__(self, text=None, thought=False, function_call=None, thought_signature=None):
        self.text = text
        self.thought = thought
        self.function_call = function_call
        self.thought_signature = thought_signature


class MockContent:
    def __init__(self, parts=None):
        self.parts = parts or []


class MockCandidate:
    def __init__(self, content=None, finish_reason=None):
        self.content = content
        self.finish_reason = finish_reason


class MockModalityTokenCount:
    def __init__(self, token_count=None):
        self.token_count = token_count


class MockUsageMetadata:
    def __init__(self, candidates_token_count=0, prompt_token_count=0, total_token_count=0):
        self.candidates_token_count = candidates_token_count
        self.prompt_token_count = prompt_token_count
        self.total_token_count = total_token_count
        self.cache_tokens_details = [MockModalityTokenCount(token_count=1), MockModalityTokenCount(token_count=2)]
        self.thoughts_token_count = 0


class MockChunk:
    def __init__(self, candidates=None, usage_metadata=None):
        self.candidates = candidates or []
        self.usage_metadata = usage_metadata


async def mock_generate_content_stream(chunks):
    for chunk in chunks:
        yield chunk


# --- Tests ---


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.api_key_env_var = "GEMINI_API_KEY"
    config.model = "gemini-2.5-pro"
    return config


@pytest.fixture
def mock_conversation():
    conv = MagicMock()
    conv.messages = [{"role": "user", "content": "hello"}]
    return conv


@pytest.fixture
def mock_tools():
    tools = MagicMock()
    tools.get_all.return_value = []
    return tools


@pytest.fixture
def client(mock_config):
    with patch("os.getenv", return_value="fake-key"), patch("frugalbot.clients.google.genai.Client") as mock_create:
        mock_instance = MagicMock()
        mock_instance.aio.models.generate_content_stream = AsyncMock()
        mock_create.return_value = mock_instance

        client = GoogleClient(mock_config)
        yield client


async def test_init_valid_config_sets_model(mock_config):
    # Given
    with patch("os.getenv", return_value="fake-key"), patch("frugalbot.clients.google.genai.Client"):
        # When
        client = GoogleClient(mock_config)

        # Then
        assert client.model == "gemini-2.5-pro"


async def test_init_valid_config_calls_client_with_api_key(mock_config):
    # Given
    with patch("os.getenv", return_value="fake-key"), patch("frugalbot.clients.google.genai.Client") as mock_create:
        # When
        GoogleClient(mock_config)

        # Then
        mock_create.assert_called_once_with(api_key="fake-key")


async def test_init_missing_api_key_calls_client_with_none(mock_config):
    # Given
    with patch("os.getenv", return_value=None), patch("frugalbot.clients.google.genai.Client") as mock_create:
        # When
        GoogleClient(mock_config)

        # Then
        mock_create.assert_called_once_with(api_key=None)


async def test_call_basic_completion_returns_aggregated_content(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Hello ")]))]),
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="world!")]))]),
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="")]), finish_reason="STOP")]),
    ]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].message.content == "Hello world!"


async def test_call_basic_completion_returns_correct_finish_reason(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Hello")]), finish_reason="STOP")]),
    ]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].finish_reason == "stop"


async def test_call_basic_completion_returns_assistant_role(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Hello")]), finish_reason="STOP")]),
    ]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].message.role == "assistant"


async def test_call_basic_completion_emits_assistant_messages(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Hello ")]))]),
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="world!")]))]),
    ]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    with patch("frugalbot.clients.google.bus.emit_and_handle", new_callable=AsyncMock) as mock_emit:
        # When
        await client.call(mock_conversation, mock_tools)

        # Then
        assert mock_emit.call_count == 2


async def test_call_reasoning_returns_reasoning_content(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Thinking...", thought=True)]))]),
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Answer!")]))]),
    ]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].message.reasoning.content == "Thinking..."


async def test_call_reasoning_returns_answer_content(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Thinking...", thought=True)]))]),
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Answer!")]))]),
    ]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].message.content == "Answer!"


async def test_call_reasoning_emits_thinking_messages(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Thinking...", thought=True)]))]),
    ]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    with patch("frugalbot.clients.google.bus.emit_and_handle", new_callable=AsyncMock) as mock_emit:
        # When
        await client.call(mock_conversation, mock_tools)

        # Then
        event = mock_emit.call_args[0][0]
        assert event.message_type == MessageType.THINKING


async def test_call_mixed_content_aggregates_reasoning(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="T1", thought=True), MockPart(text="C1")]))]),
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="T2", thought=True), MockPart(text="C2")]))]),
    ]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].message.reasoning.content == "T1T2"


async def test_call_mixed_content_aggregates_content(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="T1", thought=True), MockPart(text="C1")]))]),
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="T2", thought=True), MockPart(text="C2")]))]),
    ]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].message.content == "C1C2"


async def test_call_usage_metadata_returns_prompt_tokens(client, mock_conversation, mock_tools):
    # Given
    usage_data = MockUsageMetadata(prompt_token_count=10, candidates_token_count=20, total_token_count=30)
    chunks = [
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Hi")]))]),
        MockChunk(candidates=[], usage_metadata=usage_data),
    ]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.usage.prompt_tokens == 10


async def test_call_usage_metadata_returns_completion_tokens(client, mock_conversation, mock_tools):
    # Given
    usage_data = MockUsageMetadata(prompt_token_count=10, candidates_token_count=20, total_token_count=30)
    chunks = [
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Hi")]))]),
        MockChunk(candidates=[], usage_metadata=usage_data),
    ]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.usage.completion_tokens == 20


async def test_call_usage_metadata_returns_total_tokens(client, mock_conversation, mock_tools):
    # Given
    usage_data = MockUsageMetadata(prompt_token_count=10, candidates_token_count=20, total_token_count=30)
    chunks = [
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Hi")]))]),
        MockChunk(candidates=[], usage_metadata=usage_data),
    ]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.usage.total_tokens == 30


async def test_call_single_tool_call_returns_correct_id(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(function_call=MockFunctionCall(name="get_weather", args={"city": "London"}, id="call_1"))]))]),
    ]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].message.tool_calls[0].id == "call_1"


async def test_call_single_tool_call_returns_correct_function_name(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(function_call=MockFunctionCall(name="get_weather", args={"city": "London"}, id="call_1"))]))]),
    ]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].message.tool_calls[0].function.name == "get_weather"


async def test_call_single_tool_call_returns_correct_arguments(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(function_call=MockFunctionCall(name="get_weather", args={"city": "London"}, id="call_1"))]))]),
    ]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert json.loads(result.choices[0].message.tool_calls[0].function.arguments) == {"city": "London"}


async def test_call_single_tool_call_returns_tool_calls_finish_reason(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(function_call=MockFunctionCall(name="get_weather", args={"city": "London"}, id="call_1"))]))]),
    ]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].finish_reason == "tool_calls"


async def test_call_multiple_tool_calls_returns_correct_count(client, mock_conversation, mock_tools):
    # Given
    chunks = [
        MockChunk(
            candidates=[
                MockCandidate(
                    content=MockContent([MockPart(function_call=MockFunctionCall(name="tool1", args={"a": 1}, id="call_1")), MockPart(function_call=MockFunctionCall(name="tool2", args={"b": 2}, id="call_2"))])
                )
            ]
        ),
    ]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert len(result.choices[0].message.tool_calls) == 2


async def test_call_with_tools_passes_tool_schemas_to_genai_client(client, mock_conversation):
    # Given
    mock_tool = MagicMock()
    mock_tool.get_schema.return_value = {"type": "function", "function": {"name": "test_tool", "description": "A test tool", "parameters": {"type": "object", "properties": {"arg1": {"type": "string"}}}}}

    mock_tools = MagicMock()
    mock_tools.get_all.return_value = [mock_tool]

    chunks = [MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Done")]))])]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    # When
    await client.call(mock_conversation, mock_tools)

    # Then
    mock_tools.get_all.assert_called_once()
    mock_tool.get_schema.assert_called_once()


async def test_call_event_bus_emits_message_event_with_markdown_markup(client, mock_conversation, mock_tools):
    # Given
    chunks = [MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Hello")]))])]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    with patch("frugalbot.clients.google.bus.emit_and_handle", new_callable=AsyncMock) as mock_emit:
        # When
        await client.call(mock_conversation, mock_tools)

        # Then
        event = mock_emit.call_args[0][0]
        assert event.message_markup == MessageMarkup.MARKDOWN


async def test_retry_on_failure_returns_success_after_retries(client, mock_conversation, mock_tools):
    # Given
    fail_count = 0

    async def mock_fail_then_succeed(**kwargs):
        nonlocal fail_count
        fail_count += 1
        if fail_count <= 3:
            raise TimeoutError("Timeout!")
        yield MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Success")]))])

    client.client.aio.models.generate_content_stream.side_effect = mock_fail_then_succeed

    with patch("asyncio.sleep", new_callable=AsyncMock):
        # When
        result = await client.call(mock_conversation, mock_tools)

        # Then
        assert result.choices[0].message.content == "Success"


async def test_retry_on_failure_emits_error_messages(client, mock_conversation, mock_tools):
    # Given
    fail_count = 0

    async def mock_fail_then_succeed(**kwargs):
        nonlocal fail_count
        fail_count += 1
        if fail_count <= 3:
            raise TimeoutError("Timeout!")
        yield MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Success")]))])

    client.client.aio.models.generate_content_stream.side_effect = mock_fail_then_succeed

    with patch("frugalbot.events.bus.emit_and_handle", new_callable=AsyncMock) as mock_emit:
        with patch("asyncio.sleep", new_callable=AsyncMock):
            # When
            await client.call(mock_conversation, mock_tools)

            # Then
            error_events = [call[0][0] for call in mock_emit.call_args_list if call[0][0].message_type == MessageType.ERROR]
            assert len(error_events) == 3


async def test_terminal_failure_raises_retry_error(client, mock_conversation, mock_tools):
    # Given
    async def mock_permanent_failure(**kwargs):
        raise TimeoutError("Permanent Failure")

    client.client.aio.models.generate_content_stream.side_effect = mock_permanent_failure

    with patch("asyncio.sleep", new_callable=AsyncMock):
        # When / Then
        with pytest.raises(tenacity.RetryError):
            await client.call(mock_conversation, mock_tools)


async def test_empty_stream_returns_empty_content(client, mock_conversation, mock_tools):
    # Given
    async def mock_empty_stream(**kwargs):
        if False:
            yield

    client.client.aio.models.generate_content_stream.side_effect = mock_empty_stream

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].message.content is None


async def test_finish_reason_max_tokens_maps_to_length(client, mock_conversation, mock_tools):
    # Given
    chunks = [MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Limit hit")]), finish_reason="MAX_TOKENS")])]
    client.client.aio.models.generate_content_stream.side_effect = lambda **kwargs: mock_generate_content_stream(chunks)

    # When
    result = await client.call(mock_conversation, mock_tools)

    # Then
    assert result.choices[0].finish_reason == "length"


async def test_call_with_system_instruction_passes_instruction_to_client(client, mock_tools):
    # Given
    conv = MagicMock()
    conv.messages = [{"role": "system", "content": "You are a helpful bot."}]

    async def mock_gen_done(**kwargs):
        yield MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Done")]))])

    client.client.aio.models.generate_content_stream.side_effect = mock_gen_done

    # When
    await client.call(conv, mock_tools)

    # Then
    _args, kwargs = client.client.aio.models.generate_content_stream.call_args
    assert kwargs["config"].system_instruction == "You are a helpful bot."


async def test_call_with_messages_passes_converted_contents_to_client(client, mock_tools):
    # Given
    conv = MagicMock()
    conv.messages = [
        {"role": "user", "content": "Query 1"},
        {"role": "assistant", "content": "Response 1"},
    ]

    async def mock_gen_done(**kwargs):
        yield MockChunk(candidates=[MockCandidate(content=MockContent([MockPart(text="Done")]))])

    client.client.aio.models.generate_content_stream.side_effect = mock_gen_done

    # When
    await client.call(conv, mock_tools)

    # Then
    _args, kwargs = client.client.aio.models.generate_content_stream.call_args
    assert len(kwargs["contents"]) == 2
    assert kwargs["contents"][0].role == "user"
    assert kwargs["contents"][1].role == "model"
