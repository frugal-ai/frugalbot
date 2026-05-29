from pathlib import Path
from typing import Final

import pytest
from jsonschema import ValidationError

from frugalbot.tools.base import ToolError
from frugalbot.tools.edit import Edit
from frugalbot.tools.hashline_config import HashlineConfig
from frugalbot.utils.hashline import get_contents_with_line_hashes


@pytest.fixture
def hundred_line_file(fs) -> Path:
    """A file with 100 lines for testing."""
    test_file = Path("/test_file.txt")
    lines = [f"This is line {i}." for i in range(1, 101)]
    fs.create_file(test_file, contents="\n".join(lines) + "\n")
    return test_file


def _get_hash_from_line(line: str) -> str:
    """Extract the hash portion from a hashline-formatted line (HASH|content)."""
    return line.split("|")[0]


async def test_run_empty_file_raises_tool_error(fs) -> None:
    # Given
    test_file = Path("/empty_file.txt")
    fs.create_file(test_file)
    tool = Edit(HashlineConfig())
    params = dict(path=str(test_file), edits=[dict(start_hash="123456", new_content="This is the new first line.\n")])

    # When / Then
    with pytest.raises(ToolError, match=r"File is empty"):
        await tool.run(**params)


async def test_run_single_line_updates_content(hundred_line_file: Path) -> None:
    # Given
    hashed_lines = get_contents_with_line_hashes(hundred_line_file)
    hash_first = _get_hash_from_line(hashed_lines[0])
    tool = Edit(HashlineConfig())
    params = dict(path=str(hundred_line_file), edits=[dict(start_hash=hash_first, new_content="This is the edited line 1.")])

    # When
    await tool.run(**params)

    # Then
    assert hundred_line_file.read_text().startswith("This is the edited line 1.")


async def test_run_line_range_updates_content(hundred_line_file: Path) -> None:
    # Given
    hashed_lines = get_contents_with_line_hashes(hundred_line_file)
    hash_first = _get_hash_from_line(hashed_lines[0])
    hash_third = _get_hash_from_line(hashed_lines[2])
    tool = Edit(HashlineConfig())
    params = dict(path=str(hundred_line_file), edits=[dict(start_hash=hash_first, end_hash=hash_third, new_content="Edited range")])

    # When
    await tool.run(**params)

    # Then
    lines = hundred_line_file.read_text().splitlines()
    assert lines[0] == "Edited range"


async def test_run_insert_after_adds_line(hundred_line_file: Path) -> None:
    # Given
    hashed_lines = get_contents_with_line_hashes(hundred_line_file)
    hash_first = _get_hash_from_line(hashed_lines[0])
    tool = Edit(HashlineConfig())
    params = dict(path=str(hundred_line_file), edits=[dict(start_hash=hash_first, new_content="Inserted line", insert_after=True)])

    # When
    await tool.run(**params)

    # Then
    lines = hundred_line_file.read_text().splitlines()
    assert lines[1] == "Inserted line"


async def test_run_single_line_deletion_removes_line(hundred_line_file: Path) -> None:
    # Given
    hashed_lines = get_contents_with_line_hashes(hundred_line_file)
    hash_second = _get_hash_from_line(hashed_lines[1])
    tool = Edit(HashlineConfig())
    params = dict(path=str(hundred_line_file), edits=[dict(start_hash=hash_second, new_content="")])

    # When
    await tool.run(**params)

    # Then
    assert "This is line 2." not in hundred_line_file.read_text()


async def test_run_line_range_deletion_removes_lines(hundred_line_file: Path) -> None:
    # Given
    hashed_lines = get_contents_with_line_hashes(hundred_line_file)
    hash_second = _get_hash_from_line(hashed_lines[1])
    hash_fourth = _get_hash_from_line(hashed_lines[3])
    tool = Edit(HashlineConfig())
    params = dict(path=str(hundred_line_file), edits=[dict(start_hash=hash_second, end_hash=hash_fourth, new_content="")])

    # When
    await tool.run(**params)

    # Then
    lines = hundred_line_file.read_text().splitlines()
    assert "This is line 2." not in lines


def test_validate_args_invalid_hash_raises_validation_error() -> None:
    # Given
    tool = Edit(HashlineConfig())
    params = dict(path="test.txt", edits=[dict(start_hash="zz", new_content="fail\n")])

    # When / Then
    with pytest.raises(ValidationError, match=r"'zz' is too short"):
        tool.validate_args(params)


async def test_run_non_existent_file_raises_tool_error() -> None:
    # Given
    tool = Edit(HashlineConfig())
    params = dict(path="non_existent_file.txt", edits=[dict(start_hash="a1b2c3", new_content="test\n")])

    # When / Then
    with pytest.raises(ToolError, match=r"Unable to edit .* path must exist"):
        await tool.run(**params)


def test_get_guidelines_hashline_enabled_returns_rules() -> None:
    # Given
    tool = Edit(HashlineConfig())

    # When
    guidelines = tool.get_guidelines()

    # Then
    assert "If a file already exists" in guidelines[0]


def test_get_schema_hashline_enabled_returns_schema() -> None:
    # Given
    tool = Edit(HashlineConfig())

    # When
    schema = tool.get_schema()

    # Then
    assert schema is not None


async def test_run_multiple_edits_updates_all_lines(hundred_line_file: Path) -> None:
    # Given
    hashed_lines = get_contents_with_line_hashes(hundred_line_file)
    hash_first = _get_hash_from_line(hashed_lines[0])
    hash_fiftieth = _get_hash_from_line(hashed_lines[49])
    tool = Edit(HashlineConfig())
    params = dict(
        path=str(hundred_line_file),
        edits=[
            dict(start_hash=hash_first, new_content="Edited line 1"),
            dict(start_hash=hash_fiftieth, new_content="Edited line 50"),
        ],
    )

    # When
    await tool.run(**params)

    # Then
    lines = hundred_line_file.read_text().splitlines()
    assert lines[0] == "Edited line 1"


async def test_run_classic_edit_non_unique_content_raises_tool_error(hundred_line_file: Path) -> None:
    # Given
    tool = Edit(HashlineConfig(hashline=False))
    params = dict(path=str(hundred_line_file), old_content="", new_content="hello")

    # When / Then
    with pytest.raises(ToolError, match=r"Old content '' is not unique"):
        await tool.run(**params)


async def test_run_classic_edit_empty_file_updates_content(fs) -> None:
    # Given
    empty_file_path = Path("/empty.txt")
    fs.create_file(empty_file_path, contents="")
    tool = Edit(HashlineConfig(hashline=False))
    params = dict(path=str(empty_file_path), old_content="", new_content="hello")

    # When
    await tool.run(**params)

    # Then
    assert empty_file_path.read_text() == "hello"


async def test_run_classic_edit_non_existent_file_creates_and_updates_content(fs) -> None:
    # Given
    new_file_path = Path("/doesnotexist.txt")
    tool = Edit(HashlineConfig(hashline=False))
    params = dict(path=str(new_file_path), old_content="", new_content="hello")

    # When
    await tool.run(**params)

    # Then
    assert new_file_path.read_text() == "hello"


async def test_run_classic_edit_unique_content_updates_line(fs) -> None:
    # Given
    test_file = Path("/classic_test.txt")
    fs.create_file(test_file, contents="Line 1\nLine 2\nLine 3")
    tool = Edit(HashlineConfig(hashline=False))
    params = dict(path=str(test_file), old_content="Line 2", new_content="Line 2 edited")

    # When
    await tool.run(**params)

    # Then
    assert "Line 2 edited" in test_file.read_text()


async def test_run_classic_edit_with_two_extra_leading_spaces_updates_line(fs) -> None:
    # Given
    four_spaces: Final = " " * 4
    six_spaces: Final = " " * 6
    test_file = Path("/classic_test.txt")
    fs.create_file(test_file, contents=f"{four_spaces}Line 1\n{four_spaces}Line 2\n{four_spaces}Line 3")
    tool = Edit(HashlineConfig(hashline=False))
    params = dict(path=str(test_file), old_content=f"\n{six_spaces}Line 2\n{six_spaces}Line 3", new_content=f"\n{six_spaces}Line 2 edited\n{six_spaces}Line 3 edited")

    # When
    await tool.run(**params)

    # Then
    assert f"\n{four_spaces}Line 2 edited\n{four_spaces}Line 3 edited" in test_file.read_text()


async def test_run_classic_edit_non_unique_content_replace_all_updates_all_lines(fs) -> None:
    # Given
    test_file = Path("/replace_all_test.txt")
    fs.create_file(test_file, contents="Hello\nWorld\nHello")
    tool = Edit(HashlineConfig(hashline=False))
    params = dict(path=str(test_file), old_content="Hello", new_content="Hi", replace_all=True)

    # When
    await tool.run(**params)

    # Then
    assert test_file.read_text() == "Hi\nWorld\nHi"


def test_description_hashline_enabled_returns_hashline_description() -> None:
    # Given
    tool = Edit(HashlineConfig(hashline=True))

    # When
    description = tool.description

    # Then
    assert "Must specify the hexadecimal hash" in description


def test_description_hashline_disabled_returns_classic_description() -> None:
    # Given
    tool = Edit(HashlineConfig(hashline=False))

    # When
    description = tool.description

    # Then
    assert "Returns a diff of the file" in description
