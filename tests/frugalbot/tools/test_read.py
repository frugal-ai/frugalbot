from pathlib import Path

import pytest

from frugalbot.tools.base import ToolError
from frugalbot.tools.hashline_config import HashlineConfig
from frugalbot.tools.read import Read


def create_test_file(path: Path, lines: int) -> None:
    file_text = "".join(f"This is line {i}.\n" for i in range(1, lines + 1))
    path.write_text(file_text, encoding="utf-8")


@pytest.fixture
def read_tool() -> Read:
    return Read(HashlineConfig())


async def test_read_with_valid_file_returns_full_content(fs, read_tool: Read) -> None:
    # Given
    test_file = Path("/test_file.txt")
    create_test_file(test_file, 10)

    # When
    result = await read_tool.run(path=str(test_file))

    # Then
    assert result.path == str(test_file)
    assert result.number_of_lines_in_file == 10
    assert result.line_start == 1
    assert len(result.contents.splitlines()) == 10
    assert "This is line 1" in result.contents
    assert "This is line 10" in result.contents
    # Check hash format: 6 chars + |
    assert len(result.contents.splitlines()[0].split("|")[0]) == 6


async def test_read_with_limit_returns_truncated_content(fs, read_tool: Read) -> None:
    # Given
    test_file = Path("/test_file.txt")
    create_test_file(test_file, 10)

    # When
    result = await read_tool.run(path=str(test_file), limit=5)

    # Then
    assert len(result.contents.splitlines()) == 5
    assert "This is line 1" in result.contents
    assert "This is line 5" in result.contents
    assert "This is line 6" not in result.contents


async def test_read_with_line_start_returns_content_from_offset(fs, read_tool: Read) -> None:
    # Given
    test_file = Path("/test_file.txt")
    create_test_file(test_file, 10)

    # When
    result = await read_tool.run(path=str(test_file), line_start=6)

    # Then
    assert len(result.contents.splitlines()) == 5
    assert "This is line 6" in result.contents
    assert "This is line 10" in result.contents
    assert "This is line 5" not in result.contents
    assert result.line_start == 6


async def test_read_with_limit_minus_one_returns_all_lines(fs, read_tool: Read) -> None:
    # Given
    test_file = Path("/test_file.txt")
    create_test_file(test_file, 10)

    # When
    result = await read_tool.run(path=str(test_file), limit=-1)

    # Then
    assert len(result.contents.splitlines()) == 10
    assert "This is line 1" in result.contents
    assert "This is line 10" in result.contents


async def test_read_with_limit_minus_one_and_line_start_returns_remaining_lines(fs, read_tool: Read) -> None:
    # Given
    test_file = Path("/test_file.txt")
    create_test_file(test_file, 10)

    # When
    result = await read_tool.run(path=str(test_file), line_start=6, limit=-1)

    # Then
    assert len(result.contents.splitlines()) == 5
    assert "This is line 6" in result.contents
    assert "This is line 10" in result.contents
    assert "This is line 5" not in result.contents


async def test_read_with_line_start_and_limit_returns_range(fs, read_tool: Read) -> None:
    # Given
    test_file = Path("/test_file.txt")
    create_test_file(test_file, 10)

    # When
    result = await read_tool.run(path=str(test_file), line_start=3, limit=3)

    # Then
    assert len(result.contents.splitlines()) == 3
    assert "This is line 3" in result.contents
    assert "This is line 5" in result.contents
    assert "This is line 6" not in result.contents


@pytest.mark.parametrize("line_start", [0, -1])
async def test_read_with_invalid_line_start_raises_tool_error(fs, read_tool: Read, line_start: int) -> None:
    # Given
    test_file = Path("/test_file.txt")
    create_test_file(test_file, 10)

    # When
    with pytest.raises(ToolError, match="Line number must be a positive integer"):
        await read_tool.run(path=str(test_file), line_start=line_start)


@pytest.mark.parametrize("limit", [0, -2])
async def test_read_with_invalid_limit_raises_tool_error(fs, read_tool: Read, limit: int) -> None:
    # Given
    test_file = Path("/test_file.txt")
    create_test_file(test_file, 10)

    # When
    with pytest.raises(
        ToolError,
        match="The maximum number of lines to read must be a positive integer or -1",
    ):
        await read_tool.run(path=str(test_file), limit=limit)


async def test_read_with_non_existent_file_raises_tool_error(fs, read_tool: Read) -> None:
    # Given
    # No file created — intentionally testing non-existent file path

    # When
    with pytest.raises(ToolError, match="Unable to read"):
        await read_tool.run(path="non_existent_file.txt")


async def test_read_with_utf8_content_returns_decoded_text(fs, read_tool: Read) -> None:
    # Given
    test_file = Path("/utf8_test.txt")
    utf8_text = "Hello World!\nこんにちは世界\n🚀 Emoji test\nC'est la vie\n"
    test_file.write_text(utf8_text, encoding="utf-8")

    # When
    result = await read_tool.run(path=str(test_file))

    # Then
    assert result.number_of_lines_in_file == 4
    assert "こんにちは世界" in result.contents
    assert "🚀 Emoji test" in result.contents
    assert "C'est la vie" in result.contents


def test_read_get_schema_returns_valid_schema(read_tool: Read) -> None:
    # Given
    # No setup needed beyond the read_tool fixture

    # When
    schema = read_tool.get_schema()

    # Then
    assert len(schema) > 0
    properties = schema["function"]["parameters"]["properties"]
    assert "path" in properties
    assert "line_start" in properties
    assert "limit" in properties
