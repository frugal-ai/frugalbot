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
