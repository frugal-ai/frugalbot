"""Tests for frugalbot.utils.pydantic."""

from typing import Any

from pydantic import BaseModel

from frugalbot.utils.pydantic import get_clean_tool_parameters_schema

# --- Helpers & Factories ---


def _make_simple_model() -> type[BaseModel]:
    """Create a simple model with no nested structures."""

    class SimpleModel(BaseModel):
        name: str
        count: int

    return SimpleModel


def _make_model_with_defaults() -> type[BaseModel]:
    """Create a model with default values."""

    class ModelWithDefaults(BaseModel):
        name: str = "default"
        count: int = 0

    return ModelWithDefaults


def _make_nested_model() -> type[BaseModel]:
    """Create a model with a nested sub-model."""

    class Address(BaseModel):
        street: str
        city: str

    class Person(BaseModel):
        name: str
        address: Address

    return Person


def _make_model_with_list_of_submodels() -> type[BaseModel]:
    """Create a model with a list of nested sub-models."""

    class Item(BaseModel):
        id: int
        label: str

    class Order(BaseModel):
        order_id: str
        items: list[Item]

    return Order


def _make_deeply_nested_model() -> type[BaseModel]:
    """Create a model with multiple levels of nesting."""

    class Location(BaseModel):
        lat: float
        lng: float

    class Address(BaseModel):
        street: str
        location: Location

    class Company(BaseModel):
        name: str
        address: Address

    return Company


def _make_model_with_optional_nested() -> type[BaseModel]:
    """Create a model with an optional nested sub-model."""

    class Metadata(BaseModel):
        key: str
        value: str

    class Resource(BaseModel):
        name: str
        metadata: Metadata | None = None

    return Resource


# --- Tests ---


class TestGetCleanToolParametersSchema:
    def test_simple_model_returns_schema_without_titles(self):
        # Given
        model = _make_simple_model()

        # When
        result = get_clean_tool_parameters_schema(model)

        # Then
        assert "title" not in result
        assert result["type"] == "object"
        assert "name" in result["properties"]
        assert "count" in result["properties"]

    def test_simple_model_has_no_defs_key(self):
        # Given
        model = _make_simple_model()

        # When
        result = get_clean_tool_parameters_schema(model)

        # Then
        assert "$defs" not in result

    def test_model_with_defaults_preserves_default_values(self):
        # Given
        model = _make_model_with_defaults()

        # When
        result = get_clean_tool_parameters_schema(model)

        # Then
        assert result["properties"]["name"]["default"] == "default"
        assert result["properties"]["count"]["default"] == 0

    def test_model_with_defaults_strips_titles_from_properties(self):
        # Given
        model = _make_model_with_defaults()

        # When
        result = get_clean_tool_parameters_schema(model)

        # Then
        assert "title" not in result
        assert "title" not in result["properties"]["name"]
        assert "title" not in result["properties"]["count"]

    def test_nested_model_inlines_submodel_definition(self):
        # Given
        model = _make_nested_model()

        # When
        result = get_clean_tool_parameters_schema(model)

        # Then
        assert "$defs" not in result
        assert "$ref" not in str(result)
        assert result["properties"]["address"]["type"] == "object"
        assert "street" in result["properties"]["address"]["properties"]
        assert "city" in result["properties"]["address"]["properties"]

    def test_nested_model_strips_titles_at_all_levels(self):
        # Given
        model = _make_nested_model()

        # When
        result = get_clean_tool_parameters_schema(model)

        # Then
        assert "title" not in result
        assert "title" not in result["properties"]["address"]
        assert "title" not in result["properties"]["address"]["properties"]["street"]
        assert "title" not in result["properties"]["address"]["properties"]["city"]

    def test_model_with_list_of_submodels_inlines_item_schema(self):
        # Given
        model = _make_model_with_list_of_submodels()

        # When
        result = get_clean_tool_parameters_schema(model)

        # Then
        assert "$defs" not in result
        assert "$ref" not in str(result)
        items_schema = result["properties"]["items"]
        assert items_schema["type"] == "array"
        assert items_schema["items"]["type"] == "object"
        assert "id" in items_schema["items"]["properties"]
        assert "label" in items_schema["items"]["properties"]

    def test_model_with_list_of_submodels_strips_titles(self):
        # Given
        model = _make_model_with_list_of_submodels()

        # When
        result = get_clean_tool_parameters_schema(model)

        # Then
        assert "title" not in result
        assert "title" not in result["properties"]["items"]
        assert "title" not in result["properties"]["items"]["items"]

    def test_deeply_nested_model_resolves_all_levels(self):
        # Given
        model = _make_deeply_nested_model()

        # When
        result = get_clean_tool_parameters_schema(model)

        # Then
        assert "$defs" not in result
        assert "$ref" not in str(result)
        location = result["properties"]["address"]["properties"]["location"]
        assert location["type"] == "object"
        assert "lat" in location["properties"]
        assert "lng" in location["properties"]

    def test_deeply_nested_model_strips_titles_at_all_levels(self):
        # Given
        model = _make_deeply_nested_model()

        # When
        result = get_clean_tool_parameters_schema(model)

        # Then

        def assert_no_titles(node: Any, path: str = "root") -> None:
            if isinstance(node, dict):
                assert "title" not in node, f"Found 'title' at {path}"
                for key, value in node.items():
                    assert_no_titles(value, f"{path}.{key}")
            elif isinstance(node, list):
                for i, item in enumerate(node):
                    assert_no_titles(item, f"{path}[{i}]")

        assert_no_titles(result)

    def test_model_with_optional_nested_inlines_definition(self):
        # Given
        model = _make_model_with_optional_nested()

        # When
        result = get_clean_tool_parameters_schema(model)

        # Then
        assert "$defs" not in result
        assert "$ref" not in str(result)
        metadata_prop = result["properties"]["metadata"]
        # Optional fields become anyOf with the type and null
        assert "anyOf" in metadata_prop or "type" in metadata_prop

    def test_model_with_optional_nested_strips_titles(self):
        # Given
        model = _make_model_with_optional_nested()

        # When
        result = get_clean_tool_parameters_schema(model)

        # Then

        def assert_no_titles(node: Any) -> None:
            if isinstance(node, dict):
                assert "title" not in node
                for value in node.values():
                    assert_no_titles(value)
            elif isinstance(node, list):
                for item in node:
                    assert_no_titles(item)

        assert_no_titles(result)

    def test_result_is_plain_dict(self):
        # Given
        model = _make_nested_model()

        # When
        result = get_clean_tool_parameters_schema(model)

        # Then
        assert isinstance(result, dict)

    def test_required_fields_preserved(self):
        # Given
        model = _make_simple_model()

        # When
        result = get_clean_tool_parameters_schema(model)

        # Then
        assert "required" in result
        assert "name" in result["required"]
        assert "count" in result["required"]

    def test_required_fields_not_modified_for_optional(self):
        # Given
        model = _make_model_with_defaults()

        # When
        result = get_clean_tool_parameters_schema(model)

        # Then
        # Fields with defaults should not appear in required
        assert result.get("required", []) == []
