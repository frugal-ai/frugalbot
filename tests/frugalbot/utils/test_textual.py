from unittest.mock import MagicMock

import pytest
from textual.widgets import TextArea
from textual.widgets.text_area import Document

from frugalbot.utils.textual import (
    get_text_area_document,
    get_word_at_cursor_location,
    get_word_location_at_cursor_location,
)

# --- Tests for get_text_area_document ---


def test_get_text_area_document_with_valid_document_returns_document() -> None:
    # Given
    textarea = MagicMock(spec=TextArea)
    textarea.document = MagicMock(spec=Document)

    # When
    result = get_text_area_document(textarea)

    # Then
    assert result is textarea.document


def test_get_text_area_document_with_non_document_raises_runtime_error() -> None:
    # Given
    textarea = MagicMock(spec=TextArea)
    textarea.document = "not a document"

    # When / Then
    with pytest.raises(TypeError, match="Unexpected type of document"):
        get_text_area_document(textarea)


def test_get_text_area_document_with_none_document_raises_runtime_error() -> None:
    # Given
    textarea = MagicMock(spec=TextArea)
    textarea.document = None

    # When / Then
    with pytest.raises(TypeError, match="Unexpected type of document"):
        get_text_area_document(textarea)


# --- Tests for get_word_location_at_cursor_location ---


def _create_mock_textarea(text: str, cursor_index: int) -> MagicMock:
    """Helper to create a mock TextArea with a given text and cursor index."""
    textarea = MagicMock(spec=TextArea)
    document = MagicMock(spec=Document)
    document.text = text
    document.get_index_from_location.return_value = cursor_index
    textarea.document = document
    textarea.cursor_location = (0, cursor_index)
    return textarea


def test_get_word_location_with_cursor_in_middle_of_word_returns_word_boundaries() -> None:
    # Given
    # text: "hello world"
    # cursor at index 3 ("l" in "hello")
    textarea = _create_mock_textarea("hello world", 3)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    assert result == (0, 5)


def test_get_word_location_with_cursor_at_start_of_word_returns_word_boundaries() -> None:
    # Given
    # text: "hello world"
    # cursor at index 0 (start of "hello")
    textarea = _create_mock_textarea("hello world", 0)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    assert result == (0, 5)


def test_get_word_location_with_cursor_at_end_of_word_returns_word_boundaries() -> None:
    # Given
    # text: "hello world"
    # cursor at index 5 (just after "hello", before space)
    textarea = _create_mock_textarea("hello world", 5)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    assert result == (0, 5)


def test_get_word_location_with_cursor_on_whitespace_returns_equal_indices() -> None:
    # Given
    # text: "hello world"
    # cursor at index 5 (on the space between "hello" and "world")
    # Actually index 5 is after "hello", the space is at index 5
    textarea = _create_mock_textarea("hello world", 5)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    # cursor_index=5, text[5]=" " is whitespace
    # word_start: walks back from 5, text[4]="o" not space -> 4, text[3]="l" -> 3...
    # Actually, let me reconsider: the cursor is at index 5 which is the space character
    # word_start_index starts at 5, text[4]="o" not space, walks back to 0
    # word_end_index starts at 5, text[5]=" " is space, stays at 5
    # So this would return (0, 5) — cursor at boundary picks up the word before it
    assert result == (0, 5)


def test_get_word_location_with_cursor_between_words_on_space_returns_empty_word() -> None:
    # Given
    # text: "hello  world" (two spaces)
    # cursor at index 6 (the second space)
    textarea = _create_mock_textarea("hello  world", 6)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    # cursor_index=6, text[6]=" " is space
    # word_start: starts at 6, text[5]=" " is space, stays at 5
    # Actually: word_start_index = min(12, 6) = 6
    # while 6 > 0 and not text[5].isspace(): text[5]=" " -> isspace is True, so loop doesn't run
    # word_start_index stays at 6... wait, condition is `not text[word_start_index - 1].isspace()`
    # text[5] = " ", isspace() = True, not True = False, loop doesn't run
    # word_start_index = 5... no wait
    # Let me re-read the code carefully:
    # word_start_index = min(len(text), cursor_index) = min(12, 6) = 6
    # while word_start_index > 0 and not text[word_start_index - 1].isspace():
    #   word_start_index -= 1
    # text[5] = " " (second space), isspace() = True, not True = False -> loop doesn't run
    # word_start_index stays at 6? No wait, "hello  world" has:
    # h=0, e=1, l=2, l=3, o=4, space=5, space=6, w=7, o=8, r=9, l=10, d=11
    # text[5] = " " -> isspace True -> not True = False -> loop doesn't run
    # word_start_index = 6
    # word_end_index = 6
    # while 6 < 12 and not text[6].isspace():
    # text[6] = " " -> isspace True -> not True = False -> loop doesn't run
    # word_end_index = 6
    assert result == (6, 6)


def test_get_word_location_with_cursor_at_start_of_text_returns_first_word() -> None:
    # Given
    # text: "hello world"
    # cursor at index 0
    textarea = _create_mock_textarea("hello world", 0)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    assert result == (0, 5)


def test_get_word_location_with_cursor_at_end_of_text_returns_last_word() -> None:
    # Given
    # text: "hello world"
    # cursor at index 11 (end of "world")
    textarea = _create_mock_textarea("hello world", 11)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    assert result == (6, 11)


def test_get_word_location_with_single_word_text_returns_full_word() -> None:
    # Given
    textarea = _create_mock_textarea("hello", 2)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    assert result == (0, 5)


def test_get_word_location_with_empty_text_returns_zero_zero() -> None:
    # Given
    textarea = _create_mock_textarea("", 0)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    assert result == (0, 0)


def test_get_word_location_with_cursor_beyond_text_length_clamps_to_length() -> None:
    # Given
    # text: "hello" (length 5), cursor at index 10
    textarea = _create_mock_textarea("hello", 10)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    # cursor_index=10 but clamped: word_start = min(5, 10) = 5
    # Walk back: text[4]="o", text[3]="l", text[2]="l", text[1]="e", text[0]="h" -> word_start=0
    # word_end = min(5, 10) = 5, 5 < 5 is False -> word_end=5
    assert result == (0, 5)


def test_get_word_location_with_cursor_on_second_word_returns_second_word_boundaries() -> None:
    # Given
    # text: "hello world"
    # cursor at index 8 (in "world")
    textarea = _create_mock_textarea("hello world", 8)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    assert result == (6, 11)


def test_get_word_location_with_multiline_text_returns_correct_word() -> None:
    # Given
    # text: "hello\nworld"
    # cursor at index 8 (in "world", character "r")
    textarea = _create_mock_textarea("hello\nworld", 8)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    # "world" starts at index 6 (after "hello\n")
    assert result == (6, 11)


def test_get_word_location_with_tab_separated_words_returns_correct_word() -> None:
    # Given
    # text: "hello\tworld"
    # cursor at index 8 (in "world")
    textarea = _create_mock_textarea("hello\tworld", 8)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    assert result == (6, 11)


def test_get_word_location_with_newline_between_words_returns_first_word() -> None:
    # Given
    # text: "hello\nworld"
    # cursor at index 5 (on the newline)
    textarea = _create_mock_textarea("hello\nworld", 5)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    # Newline is whitespace, so walking back captures "hello", walking forward stops at newline
    assert result == (0, 5)


def test_get_word_location_with_word_containing_numbers_returns_full_word() -> None:
    # Given
    # text: "foo123bar baz"
    # cursor at index 6 (on "3")
    textarea = _create_mock_textarea("foo123bar baz", 6)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    assert result == (0, 9)


def test_get_word_location_with_word_containing_special_chars_returns_full_word() -> None:
    # Given
    # text: "hello_world foo"
    # cursor at index 7 (on "r" in "hello_world")
    textarea = _create_mock_textarea("hello_world foo", 7)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    assert result == (0, 11)


def test_get_word_location_with_only_whitespace_returns_equal_indices() -> None:
    # Given
    textarea = _create_mock_textarea("   ", 1)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    assert result == (1, 1)


def test_get_word_location_with_leading_whitespace_returns_correct_word() -> None:
    # Given
    # text: "   hello"
    # cursor at index 5 (in "hello")
    textarea = _create_mock_textarea("   hello", 5)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    assert result == (3, 8)


def test_get_word_location_with_trailing_whitespace_returns_correct_word() -> None:
    # Given
    # text: "hello   "
    # cursor at index 3 (in "hello")
    textarea = _create_mock_textarea("hello   ", 3)

    # When
    result = get_word_location_at_cursor_location(textarea)

    # Then
    assert result == (0, 5)


# --- Tests for get_word_at_cursor_location ---


def test_get_word_at_cursor_with_cursor_in_middle_of_word_returns_word() -> None:
    # Given
    # text: "hello world"
    # cursor at index 2 (in "hello")
    textarea = _create_mock_textarea("hello world", 2)

    # When
    result = get_word_at_cursor_location(textarea)

    # Then
    assert result == "hello"


def test_get_word_at_cursor_with_cursor_on_whitespace_returns_empty_string() -> None:
    # Given
    # text: "hello  world" (two spaces)
    # cursor at index 6 (on second space)
    textarea = _create_mock_textarea("hello  world", 6)

    # When
    result = get_word_at_cursor_location(textarea)

    # Then
    assert result == ""


def test_get_word_at_cursor_with_cursor_at_start_of_word_returns_word() -> None:
    # Given
    # text: "hello world"
    # cursor at index 6 (start of "world")
    textarea = _create_mock_textarea("hello world", 6)

    # When
    result = get_word_at_cursor_location(textarea)

    # Then
    assert result == "world"


def test_get_word_at_cursor_with_cursor_at_end_of_word_returns_word() -> None:
    # Given
    # text: "hello world"
    # cursor at index 11 (end of "world")
    textarea = _create_mock_textarea("hello world", 11)

    # When
    result = get_word_at_cursor_location(textarea)

    # Then
    assert result == "world"


def test_get_word_at_cursor_with_empty_text_returns_empty_string() -> None:
    # Given
    textarea = _create_mock_textarea("", 0)

    # When
    result = get_word_at_cursor_location(textarea)

    # Then
    assert result == ""


def test_get_word_at_cursor_with_single_word_returns_word() -> None:
    # Given
    textarea = _create_mock_textarea("hello", 3)

    # When
    result = get_word_at_cursor_location(textarea)

    # Then
    assert result == "hello"


def test_get_word_at_cursor_with_cursor_beyond_text_length_returns_word() -> None:
    # Given
    # text: "hello" (length 5), cursor at index 10
    textarea = _create_mock_textarea("hello", 10)

    # When
    result = get_word_at_cursor_location(textarea)

    # Then
    assert result == "hello"


def test_get_word_at_cursor_with_only_whitespace_returns_empty_string() -> None:
    # Given
    textarea = _create_mock_textarea("   ", 1)

    # When
    result = get_word_at_cursor_location(textarea)

    # Then
    assert result == ""


def test_get_word_at_cursor_with_newline_separated_text_returns_correct_word() -> None:
    # Given
    # text: "hello\nworld"
    # cursor at index 8 (in "world")
    textarea = _create_mock_textarea("hello\nworld", 8)

    # When
    result = get_word_at_cursor_location(textarea)

    # Then
    assert result == "world"
