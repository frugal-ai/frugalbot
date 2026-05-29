from pathlib import Path

import pytest
from pydantic import ValidationError
from pyfakefs.fake_filesystem import FakeFilesystem

from frugalbot.utils.hashline import (
    SingleHashlineEditParams,
    _apply_edits_to_lines,
    _compute_final_ranges,
    _create_hash_to_index_map,
    _DetailedEditParam,
    _generate_edit_results,
    _hash_lines,
    _validate_and_sort_edits,
    _write_edited_file,
    apply_hashline_edits,
    get_contents_with_line_hashes,
)

# --- Tests for SingleHashlineEditParams model validation ---


def test_single_hashline_edit_params_with_valid_single_line_edit_is_created() -> None:
    # Given
    start_hash = "1abcde"
    new_content = "replacement"

    # When
    params = SingleHashlineEditParams(start_hash=start_hash, new_content=new_content)

    # Then
    assert params.start_hash == start_hash
    assert params.new_content == new_content
    assert params.end_hash is None
    assert params.insert_after is False


def test_single_hashline_edit_params_with_valid_end_hash_is_created() -> None:
    # Given
    start_hash = "1abcde"
    end_hash = "3fghij"
    new_content = "replacement"

    # When
    params = SingleHashlineEditParams(start_hash=start_hash, new_content=new_content, end_hash=end_hash)

    # Then
    assert params.end_hash == end_hash


def test_single_hashline_edit_params_with_valid_insert_after_is_created() -> None:
    # Given
    start_hash = "1abcde"
    new_content = "inserted line"

    # When
    params = SingleHashlineEditParams(start_hash=start_hash, new_content=new_content, insert_after=True)

    # Then
    assert params.insert_after is True


def test_single_hashline_edit_params_with_insert_after_and_end_hash_raises_validation_error() -> None:
    # Given
    start_hash = "1abcde"
    end_hash = "3fghij"

    # When / Then
    with pytest.raises(ValidationError, match="insert_after cannot be used with end_hash"):
        SingleHashlineEditParams(start_hash=start_hash, new_content="content", end_hash=end_hash, insert_after=True)


def test_single_hashline_edit_params_with_short_start_hash_raises_validation_error() -> None:
    # Given
    short_hash = "abc"

    # When / Then
    with pytest.raises(ValidationError):
        SingleHashlineEditParams(start_hash=short_hash, new_content="content")


def test_single_hashline_edit_params_with_long_start_hash_raises_validation_error() -> None:
    # Given
    long_hash = "abcdefg"

    # When / Then
    with pytest.raises(ValidationError):
        SingleHashlineEditParams(start_hash=long_hash, new_content="content")


# --- Tests for _hash_lines ---


def test_hash_lines_with_multiple_lines_returns_correct_length_list() -> None:
    # Given
    lines = ["hello world", "foo bar", "baz qux"]

    # When
    result = _hash_lines(lines)

    # Then
    assert len(result) == 3
    assert all(isinstance(h, str) and len(h) == 6 for h in result)


def test_hash_lines_with_empty_list_returns_empty_list() -> None:
    # Given
    lines: list[str] = []

    # When
    result = _hash_lines(lines)

    # Then
    assert result == []


def test_hash_lines_with_identical_lines_produces_same_hash_suffix() -> None:
    # Given
    lines = ["same", "same", "same"]

    # When
    result = _hash_lines(lines)

    # Then
    # Hash suffixes should be identical but prefixes (line numbers) differ
    assert result[0][1:] == result[1][1:] == result[2][1:]
    assert result[0] != result[1] != result[2]


def test_hash_lines_with_empty_string_line_produces_hash() -> None:
    # Given
    lines = [""]

    # When
    result = _hash_lines(lines)

    # Then
    assert len(result) == 1
    assert len(result[0]) == 6


# --- Tests for get_contents_with_line_hashes ---


def test_get_contents_with_line_hashes_with_three_lines_returns_hash_prefixed_lines(fs: FakeFilesystem) -> None:
    # Given
    file_path = Path("/test/file.txt")
    fs.create_file(str(file_path), contents="hello\nworld\nfoo")

    # When
    result = get_contents_with_line_hashes(file_path)

    # Then
    assert len(result) == 3
    assert result[0].endswith("|hello")
    assert result[1].endswith("|world")
    assert result[2].endswith("|foo")


def test_get_contents_with_line_hashes_with_empty_file_returns_empty_list(fs: FakeFilesystem) -> None:
    # Given
    file_path = Path("/test/empty.txt")
    fs.create_file(str(file_path), contents="")

    # When
    result = get_contents_with_line_hashes(file_path)

    # Then
    assert result == []


def test_get_contents_with_line_hashes_with_single_line_returns_single_prefixed_line(fs: FakeFilesystem) -> None:
    # Given
    file_path = Path("/test/single.txt")
    fs.create_file(str(file_path), contents="only line\n")

    # When
    result = get_contents_with_line_hashes(file_path)

    # Then
    assert len(result) == 1
    assert result[0].endswith("|only line")


def test_get_contents_with_line_hashes_format_has_pipe_separator(fs: FakeFilesystem) -> None:
    # Given
    file_path = Path("/test/format.txt")
    fs.create_file(str(file_path), contents="line one\nline two")

    # When
    result = get_contents_with_line_hashes(file_path)

    # Then
    assert "|" in result[0]
    hash_part, content_part = result[0].split("|", 1)
    assert len(hash_part) == 6
    assert content_part == "line one"


# --- Tests for _create_hash_to_index_map ---


def test_create_hash_to_index_map_with_unique_hashes_returns_correct_mapping() -> None:
    # Given
    hashes = ["1abcde", "2fghij", "3klmno"]

    # When
    result = _create_hash_to_index_map(hashes)

    # Then
    assert result == {"1abcde": 0, "2fghij": 1, "3klmno": 2}


def test_create_hash_to_index_map_with_duplicate_hashes_keeps_first_occurrence() -> None:
    # Given
    hashes = ["1abcde", "2fghij", "1abcde", "4pqrst"]

    # When
    result = _create_hash_to_index_map(hashes)

    # Then
    assert result["1abcde"] == 0


def test_create_hash_to_index_map_with_empty_list_returns_empty_dict() -> None:
    # Given
    hashes: list[str] = []

    # When
    result = _create_hash_to_index_map(hashes)

    # Then
    assert result == {}


# --- Tests for _validate_and_sort_edits ---


def test_validate_and_sort_edits_with_single_valid_edit_returns_sorted_list() -> None:
    # Given
    hash_to_index = {"1abcde": 0, "2fghij": 1, "3klmno": 2}
    edit = SingleHashlineEditParams(start_hash="2fghij", new_content="new")
    edits = [edit]

    # When
    result = _validate_and_sort_edits(edits, hash_to_index)

    # Then
    assert len(result) == 1
    assert result[0][1].start_line_index == 1
    assert result[0][1].end_line_index == 1


def test_validate_and_sort_edits_with_unordered_edits_returns_sorted_by_start_index() -> None:
    # Given
    hash_to_index = {"1abcde": 0, "2fghij": 1, "3klmno": 2}
    edits = [
        SingleHashlineEditParams(start_hash="3klmno", new_content="c"),
        SingleHashlineEditParams(start_hash="1abcde", new_content="a"),
    ]

    # When
    result = _validate_and_sort_edits(edits, hash_to_index)

    # Then
    assert result[0][1].start_line_index == 0
    assert result[1][1].start_line_index == 2


def test_validate_and_sort_edits_with_invalid_start_hash_raises_value_error() -> None:
    # Given
    hash_to_index = {"1abcde": 0}
    edit = SingleHashlineEditParams(start_hash="9zzzzz", new_content="new")

    # When / Then
    with pytest.raises(ValueError, match="Invalid start_hash"):
        _validate_and_sort_edits([edit], hash_to_index)


def test_validate_and_sort_edits_with_invalid_end_hash_raises_value_error() -> None:
    # Given
    hash_to_index = {"1abcde": 0, "2fghij": 1}
    edit = SingleHashlineEditParams(start_hash="1abcde", new_content="new", end_hash="9zzzzz")

    # When / Then
    with pytest.raises(ValueError, match="Invalid end_hash"):
        _validate_and_sort_edits([edit], hash_to_index)


def test_validate_and_sort_edits_with_start_hash_after_end_hash_raises_value_error() -> None:
    # Given
    hash_to_index = {"1abcde": 0, "2fghij": 1, "3klmno": 2}
    edit = SingleHashlineEditParams(start_hash="3klmno", new_content="new", end_hash="1abcde")

    # When / Then
    with pytest.raises(ValueError, match="start_hash"):
        _validate_and_sort_edits([edit], hash_to_index)


def test_validate_and_sort_edits_with_empty_edits_returns_empty_list() -> None:
    # Given
    hash_to_index = {"1abcde": 0}

    # When
    result = _validate_and_sort_edits([], hash_to_index)

    # Then
    assert result == []


# --- Tests for _compute_final_ranges ---


def test_compute_final_ranges_with_single_replace_returns_correct_range() -> None:
    # Given
    edit = _DetailedEditParam(start_hash="1abcde", new_content="replaced", start_line_index=0, end_line_index=0)
    ordered_edits = [(0, edit)]

    # When
    result = _compute_final_ranges(ordered_edits)

    # Then
    assert result[0] == (0, 0)


def test_compute_final_ranges_with_deletion_returns_range_with_end_less_than_start() -> None:
    # Given
    edit = _DetailedEditParam(start_hash="1abcde", new_content="", start_line_index=1, end_line_index=1)
    ordered_edits = [(0, edit)]

    # When
    result = _compute_final_ranges(ordered_edits)

    # Then
    # Deleting 1 line and adding 0 lines: shift = -1, end = start + 0 - 1 = start - 1
    assert result[0][0] == 1
    assert result[0][1] == 0


def test_compute_final_ranges_with_insert_after_returns_range_after_start_line() -> None:
    # Given
    edit = _DetailedEditParam(start_hash="1abcde", new_content="inserted", insert_after=True, start_line_index=0, end_line_index=0)
    ordered_edits = [(0, edit)]

    # When
    result = _compute_final_ranges(ordered_edits)

    # Then
    assert result[0] == (1, 1)


def test_compute_final_ranges_with_multiline_content_returns_correct_range() -> None:
    # Given
    edit = _DetailedEditParam(start_hash="1abcde", new_content="line1\nline2\nline3", start_line_index=0, end_line_index=0)
    ordered_edits = [(0, edit)]

    # When
    result = _compute_final_ranges(ordered_edits)

    # Then
    assert result[0] == (0, 2)


def test_compute_final_ranges_with_multiple_edits_computes_correct_shifts() -> None:
    # Given
    edit1 = _DetailedEditParam(start_hash="1abcde", new_content="a\nb", start_line_index=0, end_line_index=0)
    edit2 = _DetailedEditParam(start_hash="3klmno", new_content="c", start_line_index=2, end_line_index=2)
    ordered_edits = [(0, edit1), (1, edit2)]

    # When
    result = _compute_final_ranges(ordered_edits)

    # Then
    # edit1: replaces line 0 with 2 lines. shift becomes 1. range = (0, 1)
    assert result[0] == (0, 1)
    # edit2: original index 2, shifted by 1 -> start=3, range=(3,3)
    assert result[1] == (3, 3)


# --- Tests for _apply_edits_to_lines ---


def test_apply_edits_to_lines_with_single_replace_modifies_correct_line() -> None:
    # Given
    lines = ["line0", "line1", "line2"]
    edit = _DetailedEditParam(start_hash="1abcde", new_content="replaced", start_line_index=1, end_line_index=1)
    ordered_edits = [(0, edit)]

    # When
    result = _apply_edits_to_lines(lines, ordered_edits)

    # Then
    assert result == ["line0", "replaced", "line2"]


def test_apply_edits_to_lines_with_range_replace_replaces_multiple_lines() -> None:
    # Given
    lines = ["line0", "line1", "line2", "line3"]
    edit = _DetailedEditParam(start_hash="1abcde", new_content="new", start_line_index=1, end_line_index=2)
    ordered_edits = [(0, edit)]

    # When
    result = _apply_edits_to_lines(lines, ordered_edits)

    # Then
    assert result == ["line0", "new", "line3"]


def test_apply_edits_to_lines_with_deletion_removes_line() -> None:
    # Given
    lines = ["line0", "line1", "line2"]
    edit = _DetailedEditParam(start_hash="1abcde", new_content="", start_line_index=1, end_line_index=1)
    ordered_edits = [(0, edit)]

    # When
    result = _apply_edits_to_lines(lines, ordered_edits)

    # Then
    assert result == ["line0", "line2"]


def test_apply_edits_to_lines_with_insert_after_adds_lines_after_target() -> None:
    # Given
    lines = ["line0", "line1", "line2"]
    edit = _DetailedEditParam(start_hash="1abcde", new_content="inserted", insert_after=True, start_line_index=0, end_line_index=0)
    ordered_edits = [(0, edit)]

    # When
    result = _apply_edits_to_lines(lines, ordered_edits)

    # Then
    assert result == ["line0", "inserted", "line1", "line2"]


def test_apply_edits_to_lines_with_multiple_edits_applies_all_in_correct_order() -> None:
    # Given
    lines = ["a", "b", "c", "d"]
    edit1 = _DetailedEditParam(start_hash="1abcde", new_content="X", start_line_index=0, end_line_index=0)
    edit2 = _DetailedEditParam(start_hash="2fghij", new_content="Y", start_line_index=3, end_line_index=3)
    ordered_edits = [(0, edit1), (1, edit2)]

    # When
    result = _apply_edits_to_lines(lines, ordered_edits)

    # Then
    assert result == ["X", "b", "c", "Y"]


def test_apply_edits_to_lines_with_multiline_new_content_inserts_multiple_lines() -> None:
    # Given
    lines = ["before", "after"]
    edit = _DetailedEditParam(start_hash="1abcde", new_content="mid1\nmid2\nmid3", start_line_index=0, end_line_index=0)
    ordered_edits = [(0, edit)]

    # When
    result = _apply_edits_to_lines(lines, ordered_edits)

    # Then
    assert result == ["mid1", "mid2", "mid3", "after"]


# --- Tests for _write_edited_file ---


def test_write_edited_file_with_trailing_newline_preserves_newline(fs: FakeFilesystem) -> None:
    # Given
    file_path = Path("/test/file.txt")
    fs.create_file(str(file_path), contents="old\n")
    edited_lines = ["new"]

    # When
    _write_edited_file(file_path, "old\n", edited_lines)

    # Then
    assert file_path.read_text() == "new\n"


def test_write_edited_file_without_trailing_newline_does_not_add_newline(fs: FakeFilesystem) -> None:
    # Given
    file_path = Path("/test/file.txt")
    fs.create_file(str(file_path), contents="old")
    edited_lines = ["new"]

    # When
    _write_edited_file(file_path, "old", edited_lines)

    # Then
    assert file_path.read_text() == "new"


def test_write_edited_file_with_empty_original_content_adds_trailing_newline(fs: FakeFilesystem) -> None:
    # Given
    file_path = Path("/test/file.txt")
    fs.create_file(str(file_path), contents="")
    edited_lines = ["new"]

    # When
    _write_edited_file(file_path, "", edited_lines)

    # Then
    assert file_path.read_text() == "new\n"


def test_write_edited_file_with_multiple_lines_joins_with_newlines(fs: FakeFilesystem) -> None:
    # Given
    file_path = Path("/test/file.txt")
    fs.create_file(str(file_path), contents="old\n")
    edited_lines = ["line1", "line2", "line3"]

    # When
    _write_edited_file(file_path, "old\n", edited_lines)

    # Then
    assert file_path.read_text() == "line1\nline2\nline3\n"


# --- Tests for _generate_edit_results ---


def test_generate_edit_results_with_single_edit_returns_context_block() -> None:
    # Given
    edited_lines = ["hello", "world", "foo"]
    final_ranges = {0: (1, 1)}

    # When
    result = _generate_edit_results(edited_lines, final_ranges, 1)

    # Then
    assert len(result) == 1
    # Context includes 1 line above, the edited line, and 1 line below
    assert len(result[0].splitlines()) == 3


def test_generate_edit_results_with_edit_at_start_of_file_includes_only_available_context() -> None:
    # Given
    edited_lines = ["first", "second", "third"]
    final_ranges = {0: (0, 0)}

    # When
    result = _generate_edit_results(edited_lines, final_ranges, 1)

    # Then
    context_lines = result[0].splitlines()
    # No line above, so only the edited line + 1 below
    assert len(context_lines) == 2
    assert context_lines[0].endswith("|first")
    assert context_lines[1].endswith("|second")


def test_generate_edit_results_with_edit_at_end_of_file_includes_only_available_context() -> None:
    # Given
    edited_lines = ["first", "second", "third"]
    final_ranges = {0: (2, 2)}

    # When
    result = _generate_edit_results(edited_lines, final_ranges, 1)

    # Then
    context_lines = result[0].splitlines()
    # No line below, so 1 above + edited line
    assert len(context_lines) == 2
    assert context_lines[0].endswith("|second")
    assert context_lines[1].endswith("|third")


def test_generate_edit_results_with_multiple_edits_returns_multiple_context_blocks() -> None:
    # Given
    edited_lines = ["a", "b", "c", "d"]
    final_ranges = {0: (0, 0), 1: (3, 3)}

    # When
    result = _generate_edit_results(edited_lines, final_ranges, 2)

    # Then
    assert len(result) == 2


def test_generate_edit_results_with_deleted_line_range_shows_context_around_deletion() -> None:
    # Given
    edited_lines = ["a", "c"]
    # Deletion at original index 1, shift=-1, so start=1, end=0
    final_ranges = {0: (1, 0)}

    # When
    result = _generate_edit_results(edited_lines, final_ranges, 1)

    # Then
    assert len(result) == 1
    # Should still produce valid context lines
    context_lines = result[0].splitlines()
    assert len(context_lines) >= 1


def test_generate_edit_results_with_single_line_file_returns_single_line_context() -> None:
    # Given
    edited_lines = ["only"]
    final_ranges = {0: (0, 0)}

    # When
    result = _generate_edit_results(edited_lines, final_ranges, 1)

    # Then
    assert len(result) == 1
    assert len(result[0].splitlines()) == 1
    assert result[0].endswith("|only")


# --- Tests for apply_hashline_edits (main public entry point) ---


@pytest.fixture
def three_line_file(fs: FakeFilesystem) -> tuple[Path, list[str]]:
    """Creates a file with three lines and returns (path, lines_with_hashes)."""
    file_path = Path("/test/file.txt")
    fs.create_file(str(file_path), contents="hello\nworld\nfoo\n")
    hashes_lines = get_contents_with_line_hashes(file_path)
    return file_path, hashes_lines


def test_apply_hashline_edits_with_single_line_replace_returns_context_and_modifies_file(
    three_line_file: tuple[Path, list[str]],
) -> None:
    # Given
    file_path, hashes_lines = three_line_file
    hash_2 = hashes_lines[1].split("|", 1)[0]
    edit = SingleHashlineEditParams(start_hash=hash_2, new_content="replaced")

    # When
    result = apply_hashline_edits(file_path, [edit])

    # Then
    assert len(result) == 1
    file_content = file_path.read_text()
    assert "replaced" in file_content
    assert "world" not in file_content


def test_apply_hashline_edits_with_range_replace_replaces_all_lines_in_range(
    three_line_file: tuple[Path, list[str]],
) -> None:
    # Given
    file_path, hashes_lines = three_line_file
    hash_1 = hashes_lines[0].split("|", 1)[0]
    hash_2 = hashes_lines[1].split("|", 1)[0]
    edit = SingleHashlineEditParams(start_hash=hash_1, new_content="combined", end_hash=hash_2)

    # When
    result = apply_hashline_edits(file_path, [edit])

    # Then
    assert len(result) == 1
    file_content = file_path.read_text()
    assert file_content == "combined\nfoo\n"


def test_apply_hashline_edits_with_empty_new_content_deletes_line(
    three_line_file: tuple[Path, list[str]],
) -> None:
    # Given
    file_path, hashes_lines = three_line_file
    hash_2 = hashes_lines[1].split("|", 1)[0]
    edit = SingleHashlineEditParams(start_hash=hash_2, new_content="")

    # When
    result = apply_hashline_edits(file_path, [edit])

    # Then
    assert len(result) == 1
    file_content = file_path.read_text()
    assert file_content == "hello\nfoo\n"


def test_apply_hashline_edits_with_insert_after_adds_line_after_target(
    three_line_file: tuple[Path, list[str]],
) -> None:
    # Given
    file_path, hashes_lines = three_line_file
    hash_1 = hashes_lines[0].split("|", 1)[0]
    edit = SingleHashlineEditParams(start_hash=hash_1, new_content="inserted", insert_after=True)

    # When
    result = apply_hashline_edits(file_path, [edit])

    # Then
    assert len(result) == 1
    file_content = file_path.read_text()
    assert file_content == "hello\ninserted\nworld\nfoo\n"


def test_apply_hashline_edits_with_multiple_edits_applies_all(three_line_file: tuple[Path, list[str]]) -> None:
    # Given
    file_path, hashes_lines = three_line_file
    hash_1 = hashes_lines[0].split("|", 1)[0]
    hash_3 = hashes_lines[2].split("|", 1)[0]
    edits = [
        SingleHashlineEditParams(start_hash=hash_1, new_content="FIRST"),
        SingleHashlineEditParams(start_hash=hash_3, new_content="LAST"),
    ]

    # When
    result = apply_hashline_edits(file_path, edits)

    # Then
    assert len(result) == 2
    file_content = file_path.read_text()
    assert file_content == "FIRST\nworld\nLAST\n"


def test_apply_hashline_edits_with_file_without_trailing_newline_preserves_format(fs: FakeFilesystem) -> None:
    # Given
    file_path = Path("/test/noterminal.txt")
    fs.create_file(str(file_path), contents="hello\nworld\nfoo")
    hashes_lines = get_contents_with_line_hashes(file_path)
    hash_1 = hashes_lines[0].split("|", 1)[0]
    edit = SingleHashlineEditParams(start_hash=hash_1, new_content="replaced")

    # When
    apply_hashline_edits(file_path, [edit])

    # Then
    file_content = file_path.read_text()
    assert not file_content.endswith("\n")
    assert file_content == "replaced\nworld\nfoo"


def test_apply_hashline_edits_with_empty_file_raises_value_error(fs: FakeFilesystem) -> None:
    # Given
    file_path = Path("/test/empty.txt")
    fs.create_file(str(file_path), contents="")

    # When / Then
    with pytest.raises(ValueError, match="File is empty"):
        apply_hashline_edits(file_path, [SingleHashlineEditParams(start_hash="1abcde", new_content="new")])


def test_apply_hashline_edits_with_invalid_hash_raises_value_error(three_line_file: tuple[Path, list[str]]) -> None:
    # Given
    file_path, _ = three_line_file
    edit = SingleHashlineEditParams(start_hash="9zzzzz", new_content="new")

    # When / Then
    with pytest.raises(ValueError, match="Invalid start_hash"):
        apply_hashline_edits(file_path, [edit])


def test_apply_hashline_edits_returns_context_with_correct_line_hashes(
    three_line_file: tuple[Path, list[str]],
) -> None:
    # Given
    file_path, hashes_lines = three_line_file
    hash_2 = hashes_lines[1].split("|", 1)[0]
    edit = SingleHashlineEditParams(start_hash=hash_2, new_content="replaced")

    # When
    result = apply_hashline_edits(file_path, [edit])

    # Then
    context_block = result[0]
    context_lines = context_block.splitlines()
    # Verify all context lines have the hash|content format
    for line in context_lines:
        assert "|" in line
        hash_part = line.split("|", 1)[0]
        assert len(hash_part) == 6


def test_apply_hashline_edits_with_empty_edits_list_returns_no_results(
    three_line_file: tuple[Path, list[str]],
) -> None:
    # Given
    file_path, _ = three_line_file

    # When
    result = apply_hashline_edits(file_path, [])

    # Then
    assert result == []


def test_apply_hashline_edits_with_file_containing_only_newline_replaces_empty_line(
    fs: FakeFilesystem,
) -> None:
    # Given
    file_path = Path("/test/newline.txt")
    fs.create_file(str(file_path), contents="\n")
    hashes_lines = get_contents_with_line_hashes(file_path)
    hash_1 = hashes_lines[0].split("|", 1)[0]
    edit = SingleHashlineEditParams(start_hash=hash_1, new_content="content")

    # When
    apply_hashline_edits(file_path, [edit])

    # Then
    # File with just \n becomes one empty line "", which is not considered empty
    assert file_path.read_text() == "content\n"


def test_apply_hashline_edits_with_multiline_replacement_correctly_replaces(
    three_line_file: tuple[Path, list[str]],
) -> None:
    # Given
    file_path, hashes_lines = three_line_file
    hash_2 = hashes_lines[1].split("|", 1)[0]
    edit = SingleHashlineEditParams(start_hash=hash_2, new_content="line_a\nline_b\nline_c")

    # When
    result = apply_hashline_edits(file_path, [edit])

    # Then
    assert len(result) == 1
    file_content = file_path.read_text()
    assert file_content == "hello\nline_a\nline_b\nline_c\nfoo\n"


def test_apply_hashline_edits_with_range_replacement_using_multiline_content(
    three_line_file: tuple[Path, list[str]],
) -> None:
    # Given
    file_path, hashes_lines = three_line_file
    hash_1 = hashes_lines[0].split("|", 1)[0]
    hash_3 = hashes_lines[2].split("|", 1)[0]
    edit = SingleHashlineEditParams(start_hash=hash_1, new_content="alpha\nbeta", end_hash=hash_3)

    # When
    result = apply_hashline_edits(file_path, [edit])

    # Then
    assert len(result) == 1
    file_content = file_path.read_text()
    assert file_content == "alpha\nbeta\n"


def test_apply_hashline_edits_preserves_original_file_not_mutated_in_place(fs: FakeFilesystem) -> None:
    # Given
    file_path = Path("/test/mutable.txt")
    original = "first\nsecond\nthird\n"
    fs.create_file(str(file_path), contents=original)
    hashes_lines = get_contents_with_line_hashes(file_path)
    hash_2 = hashes_lines[1].split("|", 1)[0]
    edit = SingleHashlineEditParams(start_hash=hash_2, new_content="CHANGED")

    # When
    apply_hashline_edits(file_path, [edit])

    # Then
    assert file_path.read_text() != original
    assert "CHANGED" in file_path.read_text()


def test_apply_hashline_edits_with_insert_after_and_multiline_content_inserts_all_lines(
    three_line_file: tuple[Path, list[str]],
) -> None:
    # Given
    file_path, hashes_lines = three_line_file
    hash_1 = hashes_lines[0].split("|", 1)[0]
    edit = SingleHashlineEditParams(start_hash=hash_1, new_content="new1\nnew2", insert_after=True)

    # When
    apply_hashline_edits(file_path, [edit])

    # Then
    file_content = file_path.read_text()
    assert file_content == "hello\nnew1\nnew2\nworld\nfoo\n"


def test_apply_hashline_edits_with_result_context_for_insert_after_shows_inserted_lines(
    three_line_file: tuple[Path, list[str]],
) -> None:
    # Given
    file_path, hashes_lines = three_line_file
    hash_1 = hashes_lines[0].split("|", 1)[0]
    edit = SingleHashlineEditParams(start_hash=hash_1, new_content="inserted", insert_after=True)

    # When
    result = apply_hashline_edits(file_path, [edit])

    # Then
    context_block = result[0]
    assert "inserted" in context_block
