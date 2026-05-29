import bisect
from hashlib import md5
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, model_validator

_HASH_STRING_LENGTH = 6


class SingleHashlineEditParams(BaseModel):
    start_hash: str = Field(..., min_length=_HASH_STRING_LENGTH, max_length=_HASH_STRING_LENGTH, description=f"{_HASH_STRING_LENGTH}-char hash of the start line or single line to edit (inclusive)")
    new_content: str = Field(..., description="Replacement text (empty string = delete)")
    end_hash: str | None = Field(
        default=None, min_length=_HASH_STRING_LENGTH, max_length=_HASH_STRING_LENGTH, description=f"{_HASH_STRING_LENGTH}-char hash of the end line (inclusive). Omit for single-line edit"
    )
    insert_after: bool = Field(default=False, description="If true, insert the new content after the line specified by start_hash. Cannot be used with end_hash.")

    @model_validator(mode="after")
    def validate_constraints(self) -> Self:
        if self.insert_after and self.end_hash:
            raise ValueError("insert_after cannot be used with end_hash")
        return self


class _DetailedEditParam(SingleHashlineEditParams):
    start_line_index: int = 0
    end_line_index: int = 0


def _hash_lines(lines: list[str]) -> list[str]:
    """Generate short hashes for each line."""
    hashes = []
    for idx, line in enumerate(lines, start=1):
        line_hash = md5(line.encode()).hexdigest()
        hash_len = _HASH_STRING_LENGTH - len(str(idx))
        hashes.append(f"{idx}{line_hash[:hash_len]}")
    return hashes


def get_contents_with_line_hashes(path: Path) -> list[str]:
    """Read a file and return its lines prefixed with their hashes."""
    contents = path.read_text(encoding="utf-8")
    lines = contents.splitlines()
    hashes = _hash_lines(lines)

    if len(hashes) != len(lines):
        raise RuntimeError("Length of hashes and lines is not equal. This should never happen.")

    return [f"{h}|{line}" for h, line in zip(hashes, lines, strict=True)]


def _create_hash_to_index_map(hashes: list[str]) -> dict[str, int]:
    """Create a mapping from hash to line index, keeping the first occurrence."""
    hash_to_index = {}
    for idx, h in enumerate(hashes):
        hash_to_index.setdefault(h, idx)
    return hash_to_index


def _validate_and_sort_edits(edits: list[SingleHashlineEditParams], hash_to_index: dict[str, int]) -> list[tuple[int, _DetailedEditParam]]:
    """Validate edits against the file's hashes and sort them by start line index."""
    ordered_edits: list[tuple[int, _DetailedEditParam]] = []

    for i, edit in enumerate(edits):
        if edit.insert_after and edit.end_hash:
            raise ValueError("end_hash cannot be specified when insert_after is true")

        if edit.start_hash not in hash_to_index:
            raise ValueError(f"Invalid start_hash {edit.start_hash}. Read the file again to retrieve a valid hash.")

        if edit.end_hash is not None and edit.end_hash not in hash_to_index:
            raise ValueError(f"Invalid end_hash {edit.end_hash}. Read the file again to retrieve a valid hash.")

        start_index = hash_to_index[edit.start_hash]
        end_index = hash_to_index[edit.end_hash] if edit.end_hash else start_index

        if start_index > end_index:
            raise ValueError(f"line index of start_hash ({edit.start_hash}) is greater than line index of end hash ({edit.end_hash})")

        detailed_edit = _DetailedEditParam(**edit.model_dump(), start_line_index=start_index, end_line_index=end_index)
        bisect.insort(ordered_edits, (i, detailed_edit), key=lambda e: e[1].start_line_index)

    return ordered_edits


def _compute_final_ranges(ordered_edits: list[tuple[int, _DetailedEditParam]]) -> dict[int, tuple[int, int]]:
    """Compute the line ranges for each edit in the resulting file state."""
    shift = 0
    final_ranges: dict[int, tuple[int, int]] = {}

    for orig_idx, edit in ordered_edits:
        new_lines_len = len(edit.new_content.splitlines())

        if edit.insert_after:
            start = edit.start_line_index + 1 + shift
            shift += new_lines_len
        else:
            start = edit.start_line_index + shift
            replaced_len = edit.end_line_index - edit.start_line_index + 1
            shift += new_lines_len - replaced_len

        end = start + new_lines_len - 1
        final_ranges[orig_idx] = (start, end)

    return final_ranges


def _apply_edits_to_lines(lines: list[str], ordered_edits: list[tuple[int, _DetailedEditParam]]) -> list[str]:
    """Apply the sorted edits to the list of lines in reverse order."""
    result_lines = lines.copy()

    # Apply in reverse to avoid shifting indices for subsequent edits
    for _, edit in reversed(ordered_edits):
        new_lines = edit.new_content.splitlines()

        if edit.insert_after:
            insert_pos = edit.start_line_index + 1
            result_lines[insert_pos:insert_pos] = new_lines
        else:
            start = edit.start_line_index
            end = edit.end_line_index + 1
            result_lines[start:end] = new_lines

    return result_lines


def _write_edited_file(path: Path, original_contents: str, edited_lines: list[str]) -> None:
    """Write the modified lines back to the file, preserving trailing newlines."""
    edited_contents = "\n".join(edited_lines)
    if original_contents.endswith("\n") or not original_contents:
        edited_contents += "\n"

    path.write_text(edited_contents, encoding="utf-8")


def _generate_edit_results(edited_lines: list[str], final_ranges: dict[int, tuple[int, int]], num_edits: int) -> list[str]:
    """Generate the context blocks to return for each applied edit."""
    final_hashes = _hash_lines(edited_lines)
    final_formatted_lines = [f"{h}|{line}" for h, line in zip(final_hashes, edited_lines, strict=True)]

    results: list[str] = []
    for i in range(num_edits):
        start, end = final_ranges[i]

        # Include 1 adjacent line above and below the edit
        slice_start = max(0, start - 1)
        slice_end = min(len(final_formatted_lines), end + 2)

        context_block = "\n".join(final_formatted_lines[slice_start:slice_end])
        results.append(context_block)

    return results


def apply_hashline_edits(path: Path, edits: list[SingleHashlineEditParams]) -> list[str]:
    """Apply line-based edits using hash identifiers to a file."""
    contents = path.read_text(encoding="utf-8")
    lines = contents.splitlines()

    if not lines:
        raise ValueError("File is empty. Use 'write' tool to write file contents.")

    hashes = _hash_lines(lines)
    hash_to_index = _create_hash_to_index_map(hashes)

    ordered_edits = _validate_and_sort_edits(edits, hash_to_index)
    final_ranges = _compute_final_ranges(ordered_edits)

    edited_lines = _apply_edits_to_lines(lines, ordered_edits)
    _write_edited_file(path, contents, edited_lines)

    return _generate_edit_results(edited_lines, final_ranges, len(edits))
