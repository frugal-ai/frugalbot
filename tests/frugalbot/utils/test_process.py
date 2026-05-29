import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from frugalbot.events import MessageEvent, MessageMarkup, MessageType
from frugalbot.utils.process import read_stdout_and_stream_output_as_events


@pytest.fixture()
def mock_bus() -> Generator[MagicMock]:
    with patch("frugalbot.utils.process.bus") as mock:
        mock.emit_and_handle = AsyncMock()
        yield mock


def _make_process(stdout: asyncio.StreamReader | None) -> asyncio.subprocess.Process:
    proc = MagicMock(spec=asyncio.subprocess.Process)
    proc.stdout = stdout
    return proc


async def test_read_stdout_with_no_stdout_returns_empty_string(mock_bus: MagicMock) -> None:
    # Given
    proc = _make_process(stdout=None)

    # When
    result = await read_stdout_and_stream_output_as_events(proc)

    # Then
    assert result == ""


async def test_read_stdout_with_empty_stream_returns_empty_string(mock_bus: MagicMock) -> None:
    # Given
    reader = asyncio.StreamReader()
    reader.feed_eof()
    proc = _make_process(stdout=reader)

    # When
    result = await read_stdout_and_stream_output_as_events(proc)

    # Then
    assert result == ""


async def test_read_stdout_with_single_chunk_returns_decoded_output(mock_bus: MagicMock) -> None:
    # Given
    reader = asyncio.StreamReader()
    reader.feed_data(b"hello world")
    reader.feed_eof()
    proc = _make_process(stdout=reader)

    # When
    result = await read_stdout_and_stream_output_as_events(proc)

    # Then
    assert result == "hello world"


async def test_read_stdout_with_multiple_chunks_concatenates_output(mock_bus: MagicMock) -> None:
    # Given
    reader = asyncio.StreamReader()
    reader.feed_data(b"chunk1")
    reader.feed_data(b"chunk2")
    reader.feed_data(b"chunk3")
    reader.feed_eof()
    proc = _make_process(stdout=reader)

    # When
    result = await read_stdout_and_stream_output_as_events(proc)

    # Then
    assert result == "chunk1chunk2chunk3"


async def test_read_stdout_emits_first_chunk_as_first_event(mock_bus: MagicMock) -> None:
    # Given
    reader = asyncio.StreamReader()
    reader.feed_data(b"test")
    reader.feed_eof()
    proc = _make_process(stdout=reader)

    # When
    await read_stdout_and_stream_output_as_events(proc)

    # Then
    first_call = mock_bus.emit_and_handle.call_args_list[0]
    event: MessageEvent = first_call.args[0]
    assert event.message == "test"
    assert event.message_type == MessageType.TOOL_OUTPUT
    assert event.message_markup == MessageMarkup.MARKDOWN
    assert event.is_stream is True


async def test_read_stdout_emits_last_chunk_as_last_event(mock_bus: MagicMock) -> None:
    # Given
    reader = asyncio.StreamReader()
    reader.feed_data(b"test")
    reader.feed_eof()
    proc = _make_process(stdout=reader)

    # When
    await read_stdout_and_stream_output_as_events(proc)

    # Then
    last_call = mock_bus.emit_and_handle.call_args_list[-1]
    event: MessageEvent = last_call.args[0]
    assert event.message == "test"
    assert event.message_type == MessageType.TOOL_OUTPUT
    assert event.message_markup == MessageMarkup.MARKDOWN
    assert event.is_stream is True


async def test_read_stdout_emits_streaming_event_for_each_chunk(mock_bus: MagicMock) -> None:
    # Given
    reader = asyncio.StreamReader()
    reader.feed_data(b"AAA")
    reader.feed_eof()
    proc = _make_process(stdout=reader)

    # When
    await read_stdout_and_stream_output_as_events(proc)

    # Then
    calls = mock_bus.emit_and_handle.call_args_list
    assert len(calls) == 1  # one chunk = one event
    chunk_event: MessageEvent = calls[0].args[0]
    assert chunk_event.message == "AAA"
    assert chunk_event.message_type == MessageType.TOOL_OUTPUT
    assert chunk_event.message_markup == MessageMarkup.MARKDOWN
    assert chunk_event.is_stream is True


async def test_read_stdout_with_invalid_bytes_replaces_errors(mock_bus: MagicMock) -> None:
    # Given
    reader = asyncio.StreamReader()
    reader.feed_data(b"\xff\xfe invalid bytes")
    reader.feed_eof()
    proc = _make_process(stdout=reader)

    # When
    result = await read_stdout_and_stream_output_as_events(proc)

    # Then
    assert "\ufffd" in result


async def test_read_stdout_with_multiline_output_preserves_newlines(mock_bus: MagicMock) -> None:
    # Given
    reader = asyncio.StreamReader()
    reader.feed_data(b"line1\nline2\nline3\n")
    reader.feed_eof()
    proc = _make_process(stdout=reader)

    # When
    result = await read_stdout_and_stream_output_as_events(proc)

    # Then
    assert result == "line1\nline2\nline3\n"
