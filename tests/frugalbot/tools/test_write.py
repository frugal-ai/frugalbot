from pathlib import Path

import pytest

from frugalbot.tools.base import ToolError
from frugalbot.tools.hashline_config import HashlineConfig
from frugalbot.tools.write import Write


async def test_run_with_valid_path_and_contents_creates_file(fs) -> None:
    # Given
    tool = Write(HashlineConfig())
    test_file = Path("/new_file.txt")
    contents = "Hello, world!\nThis is a test file."

    # When
    await tool.run(path=str(test_file), contents=contents)

    # Then
    assert test_file.read_text(encoding="utf-8") == contents


async def test_run_with_missing_parent_directory_creates_directories_and_file(fs) -> None:
    # Given
    tool = Write(HashlineConfig())
    test_file = Path("/subfolder/deep/new_file.txt")
    contents = "Nested file content."

    # When
    await tool.run(path=str(test_file), contents=contents)

    # Then
    assert test_file.read_text(encoding="utf-8") == contents


async def test_run_with_write_failure_raises_tool_error(monkeypatch) -> None:
    # Given
    tool = Write(HashlineConfig())

    def mock_write_text(*args: object, **kwargs: object) -> None:
        raise OSError("Disk full")

    monkeypatch.setattr("pathlib.Path.write_text", mock_write_text)

    # When / Then
    with pytest.raises(ToolError, match=r"Unable to write .* Disk full"):
        await tool.run(path="some_path.txt", contents="some contents")


@pytest.mark.parametrize(
    "contents",
    [
        "",
        "Unicode: \xf1o\xf1o \U0001f389",
        "Line1\nLine2\nLine3\n",
    ],
)
async def test_run_with_various_contents_writes_file_correctly(fs, contents: str) -> None:
    # Given
    tool = Write(HashlineConfig())
    test_file = Path("/test_file.txt")

    # When
    await tool.run(path=str(test_file), contents=contents)

    # Then
    assert test_file.read_text(encoding="utf-8") == contents


def test_get_guidelines_with_default_config_returns_description() -> None:
    # Given
    tool = Write(HashlineConfig())

    # When
    guidelines = tool.get_guidelines()

    # Then
    assert "Use this tool to create a new file." in guidelines


def test_get_schema_with_default_config_returns_valid_schema() -> None:
    # Given
    tool = Write(HashlineConfig())

    # When
    schema = tool.get_schema()

    # Then
    assert schema["function"]["name"] == "write"


def test_description_with_hashline_enabled_mentions_hash_format() -> None:
    # Given
    tool = Write(HashlineConfig(hashline=True))

    # When
    description = tool.description

    # Then
    assert "6-character hex string" in description


def test_description_with_hashline_disabled_returns_basic_description() -> None:
    # Given
    tool = Write(HashlineConfig(hashline=False))

    # When
    description = tool.description

    # Then
    assert "Write or overwrite the contents of a file" in description
