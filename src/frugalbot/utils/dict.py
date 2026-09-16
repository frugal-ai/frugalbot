import copy
from typing import Any


def get_next_value[KeyType, ValType](dictionary: dict[KeyType, ValType], current_key: KeyType) -> ValType:
    dict_iter = iter(dictionary)
    for key in dict_iter:
        if key == current_key:
            break
    next_key = next(dict_iter, None)
    if next_key is not None:
        next_val = dictionary[next_key]
    else:
        next_val = next(iter(dictionary.values()))
    return next_val


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively merges the 'override' dictionary into the 'base' dictionary.
    """
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def normalize_alias_keys(
    target: dict[str, Any],
    canonical_key: str,
    aliases: tuple[str, ...] | list[str],
) -> None:
    """Normalize alias keys in target dictionary to the canonical key.

    If the canonical key is already present, any alias keys are stripped.
    If the canonical key is absent, the first present alias is promoted to
    canonical, and all remaining alias keys are stripped.
    """
    if canonical_key in target:
        for alias in aliases:
            target.pop(alias, None)
        return

    for alias in aliases:
        if alias in target:
            target[canonical_key] = target.pop(alias)
            break

    for alias in aliases:
        target.pop(alias, None)
