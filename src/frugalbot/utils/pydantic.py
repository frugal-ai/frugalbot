from typing import Any

from pydantic import BaseModel


def get_clean_tool_parameters_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Inlines $defs and removes all 'title' fields for LLM compatibility."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            # If it's a reference, merge the definition into the current node
            if "$ref" in node:
                ref_key = node["$ref"].split("/")[-1]
                # Merge the definition body with any local overrides (except the $ref itself)
                combined = {**defs[ref_key], **{k: v for k, v in node.items() if k != "$ref"}}
                return resolve(combined)

            # Recurse through dictionary, stripping 'title' keys
            return {k: resolve(v) for k, v in node.items() if k != "title"}

        if isinstance(node, list):
            return [resolve(item) for item in node]

        return node

    return resolve(schema)
