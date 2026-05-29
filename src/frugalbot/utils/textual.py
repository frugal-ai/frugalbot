from typing import cast

from textual.widgets import TextArea
from textual.widgets.text_area import Document


def get_text_area_document(textarea: TextArea) -> Document:
    if isinstance(textarea.document, Document):
        return cast(Document, textarea.document)
    raise TypeError(f"Unexpected type of document for text area: {type(textarea.document)}")


def get_word_location_at_cursor_location(textarea: TextArea) -> tuple[int, int]:
    cursor_index = get_text_area_document(textarea).get_index_from_location(textarea.cursor_location)
    text = textarea.document.text
    word_start_index = min(len(text), cursor_index)
    while word_start_index > 0 and not text[word_start_index - 1].isspace():
        word_start_index -= 1
    word_end_index = min(len(text), cursor_index)
    while word_end_index < len(text) and not text[word_end_index].isspace():
        word_end_index += 1
    return (word_start_index, word_end_index)


def get_word_at_cursor_location(textarea: TextArea) -> str:
    word_start_index, word_end_index = get_word_location_at_cursor_location(textarea)
    return textarea.document.text[word_start_index:word_end_index]
