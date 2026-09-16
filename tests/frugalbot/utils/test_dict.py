from frugalbot.utils.dict import normalize_alias_keys


def test_normalize_alias_keys_with_canonical_present_strips_aliases() -> None:
    # Given
    target = {"contents": "canonical", "content": "alias"}

    # When
    normalize_alias_keys(target, "contents", ("content",))

    # Then
    assert target == {"contents": "canonical"}


def test_normalize_alias_keys_with_alias_only_promotes_alias() -> None:
    # Given
    target = {"content": "alias"}

    # When
    normalize_alias_keys(target, "contents", ("content",))

    # Then
    assert target == {"contents": "alias"}


def test_normalize_alias_keys_with_multiple_aliases_promotes_first_and_strips_rest() -> None:
    # Given
    target = {"new_contents": "first", "content": "second"}

    # When
    normalize_alias_keys(target, "new_content", ("new_contents", "content", "contents"))

    # Then
    assert target == {"new_content": "first"}


def test_normalize_alias_keys_with_no_keys_present_leaves_dict_unchanged() -> None:
    # Given
    target = {"path": "f.txt"}

    # When
    normalize_alias_keys(target, "contents", ("content",))

    # Then
    assert target == {"path": "f.txt"}
