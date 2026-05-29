from enum import Enum


class AutocompleteMode(Enum):
    NONE = 1
    COMMAND = 2
    HISTORY = 3
    FILE_PATH = 4
