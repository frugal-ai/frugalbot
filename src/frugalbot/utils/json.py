import re
from typing import Any

import orjson as json
import yaml


def json_to_readable_yaml(json_str_or_dict: str | dict[str, Any]) -> str:
    def str_presenter(dumper, data):
        if "\n" in data:
            cleaned = data.replace("\r\n", "\n").replace("\r", "\n")
            cleaned = re.sub(r"[ \t]+$", "", cleaned, flags=re.MULTILINE)
            return dumper.represent_scalar("tag:yaml.org,2002:str", cleaned, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    yaml.add_representer(str, str_presenter)
    if isinstance(json_str_or_dict, str):
        json_str_or_dict = json.loads(json_str_or_dict)
    return yaml.dump(json_str_or_dict, allow_unicode=True, sort_keys=False, width=100).rstrip()
