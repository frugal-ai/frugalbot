from unittest.mock import AsyncMock, patch

import orjson as json
import pytest

from frugalbot.ui.history import read_history, write_history


def _make_async_mock_file(read_data: bytes) -> AsyncMock:
    """Create an async context manager mock that returns file-like content."""
    mock_file = AsyncMock()
    mock_file.read = AsyncMock(return_value=read_data)
    mock_file.__aenter__ = AsyncMock(return_value=mock_file)
    mock_file.__aexit__ = AsyncMock(return_value=None)
    return mock_file


# --- Tests for read_history ---


async def test_read_history_with_no_file_returns_empty_list() -> None:
    # Given
    with patch("frugalbot.ui.history.HISTORY_FILE_PATH") as mock_path:
        mock_path.exists.return_value = False

        # When
        result = await read_history()

        # Then
        assert result == []


async def test_read_history_with_valid_user_prompts_returns_prompts() -> None:
    # Given
    prompts = ["first prompt", "second prompt", "third prompt"]
    file_data = json.dumps({"user_prompts": prompts})
    mock_file = _make_async_mock_file(file_data)

    with patch("frugalbot.ui.history.HISTORY_FILE_PATH") as mock_path:
        mock_path.exists.return_value = True
        with patch("aiofiles.open", return_value=mock_file):
            # When
            result = await read_history()

            # Then
            assert result == prompts


async def test_read_history_with_missing_user_prompts_key_returns_empty_list() -> None:
    # Given
    file_data = json.dumps({"other_key": "some_value"})
    mock_file = _make_async_mock_file(file_data)

    with patch("frugalbot.ui.history.HISTORY_FILE_PATH") as mock_path:
        mock_path.exists.return_value = True
        with patch("aiofiles.open", return_value=mock_file):
            # When
            result = await read_history()

            # Then
            assert result == []


async def test_read_history_with_empty_user_prompts_returns_empty_list() -> None:
    # Given
    file_data = json.dumps({"user_prompts": []})
    mock_file = _make_async_mock_file(file_data)

    with patch("frugalbot.ui.history.HISTORY_FILE_PATH") as mock_path:
        mock_path.exists.return_value = True
        with patch("aiofiles.open", return_value=mock_file):
            # When
            result = await read_history()

            # Then
            assert result == []


async def test_read_history_with_null_json_value_returns_empty_list() -> None:
    # Given
    file_data = json.dumps(None)
    mock_file = _make_async_mock_file(file_data)

    with patch("frugalbot.ui.history.HISTORY_FILE_PATH") as mock_path:
        mock_path.exists.return_value = True
        with patch("aiofiles.open", return_value=mock_file):
            # When
            result = await read_history()

            # Then
            assert result == []


async def test_read_history_with_empty_json_object_returns_empty_list() -> None:
    # Given
    file_data = json.dumps({})
    mock_file = _make_async_mock_file(file_data)

    with patch("frugalbot.ui.history.HISTORY_FILE_PATH") as mock_path:
        mock_path.exists.return_value = True
        with patch("aiofiles.open", return_value=mock_file):
            # When
            result = await read_history()

            # Then
            assert result == []


async def test_read_history_with_single_prompt_returns_single_item_list() -> None:
    # Given
    prompts = ["only prompt"]
    file_data = json.dumps({"user_prompts": prompts})
    mock_file = _make_async_mock_file(file_data)

    with patch("frugalbot.ui.history.HISTORY_FILE_PATH") as mock_path:
        mock_path.exists.return_value = True
        with patch("aiofiles.open", return_value=mock_file):
            # When
            result = await read_history()

            # Then
            assert result == ["only prompt"]


async def test_read_history_with_invalid_json_raises_decode_error() -> None:
    # Given
    invalid_data = b"this is not json at all {{{"
    mock_file = _make_async_mock_file(invalid_data)

    with patch("frugalbot.ui.history.HISTORY_FILE_PATH") as mock_path:
        mock_path.exists.return_value = True
        with patch("aiofiles.open", return_value=mock_file):
            # When / Then
            with pytest.raises(json.JSONDecodeError):
                await read_history()


# --- Tests for write_history ---


async def test_write_history_with_empty_list_writes_empty_prompts_array() -> None:
    # Given
    mock_file = AsyncMock()
    mock_file.write = AsyncMock()
    mock_file.__aenter__ = AsyncMock(return_value=mock_file)
    mock_file.__aexit__ = AsyncMock(return_value=None)

    with patch("aiofiles.open", return_value=mock_file):
        # When
        await write_history([])

        # Then
        mock_file.write.assert_called_once()
        written_data = mock_file.write.call_args[0][0]
        parsed = json.loads(written_data)
        assert parsed == {"user_prompts": []}


async def test_write_history_with_single_prompt_writes_correct_json() -> None:
    # Given
    mock_file = AsyncMock()
    mock_file.write = AsyncMock()
    mock_file.__aenter__ = AsyncMock(return_value=mock_file)
    mock_file.__aexit__ = AsyncMock(return_value=None)
    prompts = ["hello world"]

    with patch("aiofiles.open", return_value=mock_file):
        # When
        await write_history(prompts)

        # Then
        written_data = mock_file.write.call_args[0][0]
        parsed = json.loads(written_data)
        assert parsed == {"user_prompts": ["hello world"]}


async def test_write_history_with_multiple_prompts_writes_all_in_order() -> None:
    # Given
    mock_file = AsyncMock()
    mock_file.write = AsyncMock()
    mock_file.__aenter__ = AsyncMock(return_value=mock_file)
    mock_file.__aexit__ = AsyncMock(return_value=None)
    prompts = ["alpha", "beta", "gamma"]

    with patch("aiofiles.open", return_value=mock_file):
        # When
        await write_history(prompts)

        # Then
        written_data = mock_file.write.call_args[0][0]
        parsed = json.loads(written_data)
        assert parsed["user_prompts"] == ["alpha", "beta", "gamma"]


async def test_write_history_with_duplicates_dedupes_keeping_last_occurrence() -> None:
    # Given
    mock_file = AsyncMock()
    mock_file.write = AsyncMock()
    mock_file.__aenter__ = AsyncMock(return_value=mock_file)
    mock_file.__aexit__ = AsyncMock(return_value=None)
    prompts = ["a", "b", "a", "c", "b"]

    with patch("aiofiles.open", return_value=mock_file):
        # When
        await write_history(prompts)

        # Then
        written_data = mock_file.write.call_args[0][0]
        parsed = json.loads(written_data)
        # Last occurrences: "a" at index 2, "c" at index 3, "b" at index 4
        assert parsed["user_prompts"] == ["a", "c", "b"]


async def test_write_history_with_all_identical_prompts_keeps_one() -> None:
    # Given
    mock_file = AsyncMock()
    mock_file.write = AsyncMock()
    mock_file.__aenter__ = AsyncMock(return_value=mock_file)
    mock_file.__aexit__ = AsyncMock(return_value=None)
    prompts = ["same", "same", "same", "same"]

    with patch("aiofiles.open", return_value=mock_file):
        # When
        await write_history(prompts)

        # Then
        written_data = mock_file.write.call_args[0][0]
        parsed = json.loads(written_data)
        assert parsed["user_prompts"] == ["same"]


async def test_write_history_with_more_than_500_unique_items_limits_to_500() -> None:
    # Given
    mock_file = AsyncMock()
    mock_file.write = AsyncMock()
    mock_file.__aenter__ = AsyncMock(return_value=mock_file)
    mock_file.__aexit__ = AsyncMock(return_value=None)
    prompts = [f"prompt_{i}" for i in range(600)]

    with patch("aiofiles.open", return_value=mock_file):
        # When
        await write_history(prompts)

        # Then
        written_data = mock_file.write.call_args[0][0]
        parsed = json.loads(written_data)
        assert len(parsed["user_prompts"]) == 500
        # Should keep last 500 items: prompt_100 through prompt_599
        assert parsed["user_prompts"][0] == "prompt_100"
        assert parsed["user_prompts"][-1] == "prompt_599"


async def test_write_history_with_exactly_500_unique_items_keeps_all() -> None:
    # Given
    mock_file = AsyncMock()
    mock_file.write = AsyncMock()
    mock_file.__aenter__ = AsyncMock(return_value=mock_file)
    mock_file.__aexit__ = AsyncMock(return_value=None)
    prompts = [f"prompt_{i}" for i in range(500)]

    with patch("aiofiles.open", return_value=mock_file):
        # When
        await write_history(prompts)

        # Then
        written_data = mock_file.write.call_args[0][0]
        parsed = json.loads(written_data)
        assert len(parsed["user_prompts"]) == 500
        assert parsed["user_prompts"][0] == "prompt_0"
        assert parsed["user_prompts"][-1] == "prompt_499"


async def test_write_history_with_501_unique_items_keeps_last_500() -> None:
    # Given
    mock_file = AsyncMock()
    mock_file.write = AsyncMock()
    mock_file.__aenter__ = AsyncMock(return_value=mock_file)
    mock_file.__aexit__ = AsyncMock(return_value=None)
    prompts = [f"prompt_{i}" for i in range(501)]

    with patch("aiofiles.open", return_value=mock_file):
        # When
        await write_history(prompts)

        # Then
        written_data = mock_file.write.call_args[0][0]
        parsed = json.loads(written_data)
        assert len(parsed["user_prompts"]) == 500
        assert parsed["user_prompts"][0] == "prompt_1"
        assert parsed["user_prompts"][-1] == "prompt_500"


async def test_write_history_with_duplicates_and_overflow_keeps_last_500_unique() -> None:
    # Given
    mock_file = AsyncMock()
    mock_file.write = AsyncMock()
    mock_file.__aenter__ = AsyncMock(return_value=mock_file)
    mock_file.__aexit__ = AsyncMock(return_value=None)
    # 600 items where first 100 are duplicates of last 100
    prompts = [f"prompt_{i}" for i in range(500)] + [f"prompt_{i}" for i in range(400, 500)]

    with patch("aiofiles.open", return_value=mock_file):
        # When
        await write_history(prompts)

        # Then
        written_data = mock_file.write.call_args[0][0]
        parsed = json.loads(written_data)
        assert len(parsed["user_prompts"]) == 500
        # After dedup, last occurrences order: prompt_0..prompt_499
        assert parsed["user_prompts"][0] == "prompt_0"
        assert parsed["user_prompts"][-1] == "prompt_499"


async def test_write_history_opens_file_in_write_binary_mode() -> None:
    # Given
    mock_file = AsyncMock()
    mock_file.write = AsyncMock()
    mock_file.__aenter__ = AsyncMock(return_value=mock_file)
    mock_file.__aexit__ = AsyncMock(return_value=None)

    with patch("frugalbot.ui.history.HISTORY_FILE_PATH") as mock_path:
        with patch("aiofiles.open", return_value=mock_file) as mock_open:
            # When
            await write_history(["test"])

            # Then
            mock_open.assert_called_once_with(mock_path, "wb")
