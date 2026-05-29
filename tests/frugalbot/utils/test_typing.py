import dataclasses
import enum
from datetime import date, datetime, time
from typing import Annotated, Any, Literal, TypedDict

import pytest
from pydantic import BaseModel

from frugalbot.utils.typing import python_type_to_json_schema


@pytest.mark.parametrize(
    "target_type, expected_type",
    [
        (int, "integer"),
        (str, "string"),
        (float, "number"),
        (bool, "boolean"),
        (Any, "string"),
    ],
)
def test_python_type_to_json_schema_primitive_type_returns_mapped_schema(target_type, expected_type):
    # Given
    # Context provided by parametrize

    # When
    result = python_type_to_json_schema(target_type)

    # Then
    assert result == {"type": expected_type}


def test_python_type_to_json_schema_annotated_primitive_returns_schema_with_description():
    # Given
    target_type = Annotated[int, "User age"]

    # When
    result = python_type_to_json_schema(target_type)

    # Then
    assert result == {"type": "integer", "description": "User age"}


def test_python_type_to_json_schema_annotated_complex_type_returns_schema_with_description():
    # Given
    target_type = Annotated[list[int], "List of IDs"]

    # When
    result = python_type_to_json_schema(target_type)

    # Then
    assert result == {"type": "array", "items": {"type": "integer"}, "description": "List of IDs"}


@pytest.mark.parametrize(
    "target_type, expected_format",
    [
        (datetime, "date-time"),
        (date, "date"),
        (time, "time"),
    ],
)
def test_python_type_to_json_schema_datetime_type_returns_formatted_string_schema(target_type, expected_format):
    # Given
    # Context provided by parametrize

    # When
    result = python_type_to_json_schema(target_type)

    # Then
    assert result == {"type": "string", "format": expected_format}


def test_python_type_to_json_schema_bytes_type_returns_base64_string_schema():
    # Given
    target_type = bytes

    # When
    result = python_type_to_json_schema(target_type)

    # Then
    assert result == {"type": "string", "contentEncoding": "base64"}


def test_python_type_to_json_schema_plain_set_returns_unique_array_schema():
    # Given
    target_type = set

    # When
    result = python_type_to_json_schema(target_type)

    # Then
    assert result == {"type": "array", "items": {"type": "string"}, "uniqueItems": True}


def test_python_type_to_json_schema_parameterized_list_returns_array_schema():
    # Given
    target_type = list[float]

    # When
    result = python_type_to_json_schema(target_type)

    # Then
    assert result == {"type": "array", "items": {"type": "number"}}


def test_python_type_to_json_schema_parameterized_tuple_returns_prefix_items_schema():
    # Given
    target_type = tuple[str, int]

    # When
    result = python_type_to_json_schema(target_type)

    # Then
    assert result == {"type": "array", "prefixItems": [{"type": "string"}, {"type": "integer"}], "minItems": 2, "maxItems": 2}


def test_python_type_to_json_schema_parameterized_dict_returns_object_schema():
    # Given
    target_type = dict[str, int]

    # When
    result = python_type_to_json_schema(target_type)

    # Then
    assert result == {"type": "object", "additionalProperties": {"type": "integer"}}


def test_python_type_to_json_schema_union_type_returns_oneof_schema():
    # Given
    target_type = int | str

    # When
    result = python_type_to_json_schema(target_type)

    # Then
    assert result == {"oneOf": [{"type": "integer"}, {"type": "string"}]}


def test_python_type_to_json_schema_optional_type_returns_unwrapped_schema():
    # Given
    target_type = bool | None

    # When
    result = python_type_to_json_schema(target_type)

    # Then
    assert result == {"type": "boolean"}


def test_python_type_to_json_schema_literal_type_returns_enum_schema():
    # Given
    target_type = Literal["admin", "user"]

    # When
    result = python_type_to_json_schema(target_type)

    # Then
    assert result == {"type": "string", "enum": ["admin", "user"]}


def test_python_type_to_json_schema_populated_enum_returns_mapped_enum_schema():
    # Given
    class Status(enum.Enum):
        ACTIVE = 1
        INACTIVE = 0

    # When
    result = python_type_to_json_schema(Status)

    # Then
    assert result == {"type": "integer", "enum": [1, 0]}


def test_python_type_to_json_schema_empty_enum_returns_untyped_enum_schema():
    # Given
    class EmptyEnum(enum.Enum):
        pass

    # When
    result = python_type_to_json_schema(EmptyEnum)

    # Then
    assert result == {"enum": []}


def test_python_type_to_json_schema_typeddict_returns_object_properties_schema():
    # Given
    class Config(TypedDict):
        host: str
        port: int

    # When
    result = python_type_to_json_schema(Config)

    # Then
    assert result == {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer"}}, "required": ["host", "port"]}


def test_python_type_to_json_schema_dataclass_returns_object_properties_schema():
    # Given
    @dataclasses.dataclass
    class Profile:
        username: str
        age: int = 18

    # When
    result = python_type_to_json_schema(Profile)

    # Then
    assert result == {"type": "object", "properties": {"username": {"type": "string"}, "age": {"type": "integer"}}, "required": ["username"]}


def test_python_type_to_json_schema_pydantic_model_returns_object_properties_schema():
    # Given
    class Product(BaseModel):
        id: int
        in_stock: bool = True

    # When
    result = python_type_to_json_schema(Product)

    # Then
    assert result == {"type": "object", "properties": {"id": {"type": "integer"}, "in_stock": {"type": "boolean"}}, "required": ["id"]}


@dataclasses.dataclass
class Node:
    name: str
    children: list[Node]


def test_python_type_to_json_schema_recursive_dataclass_raises_recursion_error():
    # Given
    # Context provided by the module-level Node class

    # When
    with pytest.raises(RecursionError):
        python_type_to_json_schema(Node)

    # Then
    # Verified implicitly by pytest.raises Context Manager


def test_python_type_to_json_schema_none_type_returns_null_schema():
    # Given
    target_type = type(None)

    # When
    result = python_type_to_json_schema(target_type)

    # Then
    assert result == {"type": "null"}
