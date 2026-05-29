import dataclasses
import enum
import inspect
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from typing import Annotated, Any, Literal, get_args, get_origin, get_type_hints, is_typeddict

from pydantic import BaseModel as PydanticBaseModel


def get_generic_type_of_base_class(obj: Any, base_class: type, position: int) -> type | None:
    if isinstance(obj, type):
        cls = obj
    else:
        cls = type(obj)
    bases = getattr(cls, "__orig_bases__", ())
    generic_param = None
    for base in bases:
        if get_origin(base) is base_class:
            args = get_args(base)
            if args and position < len(args):
                generic_param = args[position]
                break
    return generic_param


def python_type_to_json_schema(python_type: Any) -> dict[str, Any]:
    """Convert Python type annotation to a JSON Schema for a parameter.

    Supported mappings (subset tailored for LLM tool schemas):
    - Primitives: str/int/float/bool -> string/integer/number/boolean
    - bytes -> string with contentEncoding base64
    - datetime/date/time -> string with format date-time/date/time
    - list[T] / Sequence[T] / set[T] / frozenset[T] -> array with items=schema(T)
      - set/frozenset include uniqueItems=true
      - list without type args defaults items to string
    - dict[K,V] / Mapping[K,V] -> object with additionalProperties=schema(V)
      - dict without type args defaults additionalProperties to string
    - tuple[T1, T2, ...] -> array with prefixItems per element and min/maxItems
    - tuple[T, ...] -> array with items=schema(T)
    - Union[X, Y] and X | Y -> oneOf=[schema(X), schema(Y)] (without top-level type)
    - Optional[T] (Union[T, None]) -> schema(T) (nullability not encoded)
    - Literal[...]/Enum -> enum with appropriate type inference when uniform
    - TypedDict -> object with properties/required per annotations
    - dataclass/Pydantic BaseModel -> object with nested properties inferred from fields
    """
    origin = get_origin(python_type)
    args = get_args(python_type)

    # Bug Fix: Process Annotated recursively to preserve description for all underlying types
    if Annotated is not None and origin is Annotated and len(args) >= 1:
        inner_type = args[0]
        description = args[1] if len(args) >= 2 else None
        schema = python_type_to_json_schema(inner_type).copy()
        if description is not None:
            schema["description"] = description
        return schema

    # Bug Fix: Explicitly handle None or NoneType mapping to null
    if python_type is type(None) or python_type is None:
        return {"type": "null"}

    if python_type is Any:
        return {"type": "string"}

    primitive_map = {str: "string", int: "integer", float: "number", bool: "boolean"}
    if python_type in primitive_map:
        return {"type": primitive_map[python_type]}

    if python_type is bytes:
        return {"type": "string", "contentEncoding": "base64"}
    if python_type is datetime:
        return {"type": "string", "format": "date-time"}
    if python_type is date:
        return {"type": "string", "format": "date"}
    if python_type is time:
        return {"type": "string", "format": "time"}

    # Bug Fix: Set fallback for unparameterized collections (e.g., bare set, dict, list)
    actual_origin = origin or python_type

    if origin is Literal or actual_origin is Literal:
        literal_values = list(args)
        schema_lit: dict[str, Any] = {"enum": literal_values}
        if literal_values:  # Bug Fix: Ensure literals are populated before inferring type
            if all(isinstance(v, bool) for v in literal_values):
                schema_lit["type"] = "boolean"
            elif all(isinstance(v, str) for v in literal_values):
                schema_lit["type"] = "string"
            elif all(isinstance(v, int) and not isinstance(v, bool) for v in literal_values):
                schema_lit["type"] = "integer"
            elif all(isinstance(v, int | float) and not isinstance(v, bool) for v in literal_values):
                schema_lit["type"] = "number"
        return schema_lit

    if inspect.isclass(python_type) and issubclass(python_type, enum.Enum):
        enum_values = [e.value for e in python_type]
        value_types = {type(v) for v in enum_values}
        schema: dict[str, Any] = {"enum": enum_values}
        if value_types:  # Bug Fix: Ensure value subset logic doesn't erroneously match an empty set
            if value_types == {str}:
                schema["type"] = "string"
            elif value_types == {int}:
                schema["type"] = "integer"
            elif value_types <= {int, float}:
                schema["type"] = "number"
            elif value_types == {bool}:
                schema["type"] = "boolean"
        return schema

    if is_typeddict(python_type):
        annotations: dict[str, Any] = getattr(python_type, "__annotations__", {}) or {}
        required_keys = set(getattr(python_type, "__required_keys__", set()))
        td_properties: dict[str, Any] = {}
        td_required: list[str] = []
        for field_name, field_type in annotations.items():
            td_properties[field_name] = python_type_to_json_schema(field_type)
            if field_name in required_keys:
                td_required.append(field_name)
        schema_td: dict[str, Any] = {
            "type": "object",
            "properties": td_properties,
        }
        if td_required:
            schema_td["required"] = td_required
        return schema_td

    if inspect.isclass(python_type) and dataclasses.is_dataclass(python_type):
        type_hints = get_type_hints(python_type, include_extras=True)
        dc_properties: dict[str, Any] = {}
        dc_required: list[str] = []
        for field in dataclasses.fields(python_type):
            field_type = type_hints.get(field.name, Any)
            dc_properties[field.name] = python_type_to_json_schema(field_type)
            if field.default is dataclasses.MISSING and getattr(field, "default_factory", dataclasses.MISSING) is dataclasses.MISSING:
                dc_required.append(field.name)
        schema_dc: dict[str, Any] = {"type": "object", "properties": dc_properties}
        if dc_required:
            schema_dc["required"] = dc_required
        return schema_dc

    if inspect.isclass(python_type) and issubclass(python_type, PydanticBaseModel):
        model_type_hints = get_type_hints(python_type)
        pd_properties: dict[str, Any] = {}
        pd_required: list[str] = []
        model_fields = getattr(python_type, "model_fields", {})
        for name, field_info in model_fields.items():
            pd_properties[name] = python_type_to_json_schema(model_type_hints.get(name, Any))
            is_required = getattr(field_info, "is_required", None)
            if callable(is_required) and is_required():
                pd_required.append(name)
        schema_pd: dict[str, Any] = {"type": "object", "properties": pd_properties}
        if pd_required:
            schema_pd["required"] = pd_required
        return schema_pd

    if actual_origin in (list, Sequence, set, frozenset):
        item_type = args[0] if args else Any
        item_schema = python_type_to_json_schema(item_type)
        schema_arr: dict[str, Any] = {"type": "array", "items": item_schema or {"type": "string"}}
        if actual_origin in (set, frozenset):
            schema_arr["uniqueItems"] = True
        return schema_arr

    if actual_origin is tuple:
        if not args:
            return {"type": "array", "items": {"type": "string"}}
        if len(args) == 2 and args[1] is Ellipsis:
            return {"type": "array", "items": python_type_to_json_schema(args[0])}
        prefix_items = [python_type_to_json_schema(a) for a in args]
        return {
            "type": "array",
            "prefixItems": prefix_items,
            "minItems": len(prefix_items),
            "maxItems": len(prefix_items),
        }

    if actual_origin in (dict, Mapping):
        value_type = args[1] if len(args) >= 2 else Any
        value_schema = python_type_to_json_schema(value_type)
        return {"type": "object", "additionalProperties": value_schema or {"type": "string"}}

    typing_union = getattr(__import__("typing"), "Union", None)
    try:
        import types

        union_types = (typing_union, types.UnionType)
    except ImportError, AttributeError:
        union_types = (typing_union,)

    if actual_origin in union_types:
        non_none_args = [a for a in args if a is not type(None)]
        if len(non_none_args) > 1:
            schemas = [python_type_to_json_schema(arg) for arg in non_none_args]
            return {"oneOf": schemas}
        if non_none_args:
            return python_type_to_json_schema(non_none_args[0])
        return {"type": "string"}

    return {"type": "string"}
