from typing import Annotated

import jsonschema
import pytest

import frugalbot.tools.powershell
from frugalbot.tools.base import ToolBase, ToolConfig, Tools


@pytest.fixture
def tools():
    t = Tools()
    yield t
    t.unload()


def test_get_schema_with_example_tool_returns_correct_schema(tools):
    # Given
    class ExampleTool(ToolBase):
        """Example tool for testing."""

        async def run(self, param1: Annotated[int, "An integer parameter"], param2: Annotated[str, "A string parameter"] = "default") -> str:
            return f"Received {param1} and {param2}"

    tool = ExampleTool(ToolConfig())
    expected_schema = {
        "type": "function",
        "function": {
            "name": "exampletool",
            "description": "Example tool for testing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "param1": {
                        "type": "integer",
                        "description": "An integer parameter",
                    },
                    "param2": {
                        "type": "string",
                        "description": "A string parameter (default: default)",
                    },
                },
                "required": ["param1"],
            },
        },
    }

    # When
    schema = tool.get_schema()

    # Then
    assert schema == expected_schema


def test_get_schema_with_missing_annotation_raises_type_error(tools):
    # Given
    class InvalidTool(ToolBase):
        async def run(self, param1: int) -> str:
            return "ok"

    tool = InvalidTool(ToolConfig())

    # When
    with pytest.raises(TypeError, match="Missing description for parameter 'param1'") as excinfo:
        tool.get_schema()

    # Then
    assert excinfo.type is TypeError


def test_get_guidelines_by_default_returns_empty_list(tools):
    # Given
    class ExampleTool(ToolBase):
        async def run(self, param1: Annotated[int, "An integer parameter"]) -> str:
            return "ok"

    tool = ExampleTool(ToolConfig())

    # When
    guidelines = tool.get_guidelines()

    # Then
    assert guidelines == []


def test_validate_args_with_valid_args_returns_none(tools):
    # Given
    class ExampleTool(ToolBase):
        async def run(self, param1: Annotated[int, "An integer parameter"]) -> str:
            return "ok"

    tool = ExampleTool(ToolConfig())
    args = {"param1": 123}

    # When
    result = tool.validate_args(args)

    # Then
    assert result is None


def test_validate_args_with_invalid_args_raises_validation_error(tools):
    # Given
    class ExampleTool(ToolBase):
        """Example tool for testing."""

        async def run(self, param1: Annotated[int, "An integer parameter"]) -> str:
            return "ok"

    tool = ExampleTool(ToolConfig())
    args = {"param1": "not an integer"}

    # When
    with pytest.raises(jsonschema.ValidationError) as excinfo:
        tool.validate_args(args)

    # Then
    assert excinfo.type is jsonschema.ValidationError


def test_load_with_config_populates_registry(tools):
    # Given
    config = {"powershell": {}}

    # When
    tools.load(config)

    # Then
    assert "powershell" in [t.name for t in tools.get_all()]


def test_load_with_config_instantiates_powershell_tool(tools):
    # Given
    config = {"powershell": {}}

    # When
    tools.load(config)

    # Then
    assert isinstance(tools.get("powershell"), frugalbot.tools.powershell.Powershell)


def test_get_with_existing_tool_returns_tool(tools):
    # Given
    config = {"powershell": {}}
    tools.load(config)

    # When
    tool = tools.get("powershell")

    # Then
    assert isinstance(tool, frugalbot.tools.powershell.Powershell)


def test_get_with_missing_tool_raises_key_error(tools):
    # Given
    # Registry is empty due to tools fixture

    # When / Then
    with pytest.raises(KeyError, match="Invalid tool name: 'nonexistent'"):
        tools.get("nonexistent")
