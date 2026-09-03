import sys
from typing import Annotated, Any

import jsonschema
import pytest

import frugalbot.tools.bash
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


def _get_platform_tool_module() -> Any:
    """Return the platform-appropriate command tool module for testing registry loading."""
    if sys.platform == "win32":
        return frugalbot.tools.powershell
    return frugalbot.tools.bash


def test_load_with_config_populates_registry(tools):
    # Given
    tool_name = _get_platform_tool_module().__name__.split(".")[-1]
    config = {tool_name: {}}

    # When
    tools.load(config)

    # Then
    assert tool_name in [t.name for t in tools.get_all()]


def test_load_with_config_instantiates_platform_tool(tools):
    # Given
    tool_module = _get_platform_tool_module()
    tool_name = tool_module.__name__.split(".")[-1]
    config = {tool_name: {}}

    # When
    tools.load(config)

    # Then
    assert isinstance(tools.get(tool_name), tool_module.__dict__[tool_name.capitalize()])


def test_get_with_existing_tool_returns_tool(tools):
    # Given
    tool_module = _get_platform_tool_module()
    tool_name = tool_module.__name__.split(".")[-1]
    config = {tool_name: {}}
    tools.load(config)

    # When
    tool = tools.get(tool_name)

    # Then
    assert isinstance(tool, tool_module.__dict__[tool_name.capitalize()])


def test_get_with_missing_tool_raises_key_error(tools):
    # Given
    # Registry is empty due to tools fixture

    # When / Then
    with pytest.raises(KeyError, match="Invalid tool name: 'nonexistent'"):
        tools.get("nonexistent")
