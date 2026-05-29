from pathlib import Path
from typing import Any

import pytest

from frugalbot.tools.base import ToolConfig, ToolError
from frugalbot.tools.powershell import Powershell


@pytest.fixture
def populated_directory(tmp_path: Path) -> Path:
    """A directory with two text files for testing."""
    test_dir = tmp_path / "test_directory"
    test_dir.mkdir()
    (test_dir / "file1.txt").write_text("This is file 1. 😒", encoding="utf-8")
    (test_dir / "file2.txt").write_text("This is file 2. ✅", encoding="utf-8")
    return test_dir


@pytest.fixture
def powershell_tool() -> Powershell:
    return Powershell(ToolConfig())


@pytest.fixture
def powershell_schema(powershell_tool: Powershell) -> dict[str, Any]:
    """The schema for the default Powershell tool."""
    return powershell_tool.get_schema()


# run() tests


async def test_run_with_list_directory_command_returns_file_info(powershell_tool: Powershell, populated_directory: Path) -> None:
    # Given
    command = rf"Get-ChildItem -Path '{populated_directory}' -Recurse -File | Select-Object Name, Length"

    # When
    result = await powershell_tool.run(command)

    # Then
    assert "file1.txt" in result.output


@pytest.mark.parametrize(
    "command",
    [
        "Get-Content does/not/exist/__init__.py",
        "Get-Process | Select-Object -First 1 -Property Id",
        "Get-Content {path} -Encoding utf8 | Select-Object -First 30 | ForEach-Object {{ Write-Output \\\"'$_'\\\" }}",
    ],
)
async def test_run_with_various_commands_does_not_output_xml(powershell_tool: Powershell, command: str, populated_directory: Path) -> None:
    # Given
    command = command.format(path=populated_directory / "file1.txt")

    # When
    result = await powershell_tool.run(command)

    # Then
    assert "CLIXML" not in result.output


async def test_run_with_echo_command_returns_expected_output(powershell_tool: Powershell) -> None:
    # Given
    command = "Write-Output 'Hello World'"

    # When
    result = await powershell_tool.run(command)

    # Then
    assert "Hello World" in result.output


async def test_run_with_invalid_command_returns_nonzero_returncode(powershell_tool: Powershell) -> None:
    # Given
    command = "Invoke-NonExistentCmdlet12345"

    # When
    result = await powershell_tool.run(command)

    # Then
    assert result.returncode != 0


async def test_run_with_sleep_command_raises_tool_error_on_timeout(powershell_tool: Powershell) -> None:
    # Given
    command = "Start-Sleep -Seconds 5"
    timeout = 0.1

    # When / Then
    with pytest.raises(ToolError, match=r"timed out after 0\.1 seconds"):
        await powershell_tool.run(command, timeout_in_seconds=timeout)


# get_schema() tests


def test_get_schema_returns_correct_function_name(powershell_schema: dict[str, Any]) -> None:
    # Given
    func = powershell_schema["function"]

    # When
    name = func["name"]

    # Then
    assert name == "powershell"


def test_get_schema_returns_correct_description(powershell_schema: dict[str, Any]) -> None:
    # Given
    func = powershell_schema["function"]

    # When
    description = func["description"]

    # Then
    assert description == "Run a Powershell command and returns its output."


def test_get_schema_returns_object_parameter_type(powershell_schema: dict[str, Any]) -> None:
    # Given
    params = powershell_schema["function"]["parameters"]

    # When
    param_type = params["type"]

    # Then
    assert param_type == "object"


def test_get_schema_returns_command_and_timeout_properties(powershell_schema: dict[str, Any]) -> None:
    # Given
    props = powershell_schema["function"]["parameters"]["properties"]

    # When
    prop_keys = set(props.keys())

    # Then
    assert prop_keys == {"command", "timeout_in_seconds"}


def test_get_schema_returns_command_type_as_string(powershell_schema: dict[str, Any]) -> None:
    # Given
    command_prop = powershell_schema["function"]["parameters"]["properties"]["command"]

    # When
    command_type = command_prop["type"]

    # Then
    assert command_type == "string"


def test_get_schema_returns_command_description(powershell_schema: dict[str, Any]) -> None:
    # Given
    command_prop = powershell_schema["function"]["parameters"]["properties"]["command"]

    # When
    description = command_prop["description"]

    # Then
    assert description == "The PowerShell command(s) to execute."


def test_get_schema_returns_command_as_required_parameter(powershell_schema: dict[str, Any]) -> None:
    # Given
    required = powershell_schema["function"]["parameters"]["required"]

    # When
    required_set = set(required)

    # Then
    assert required_set == {"command"}


# description property tests


def test_description_returns_basic_description(powershell_tool: Powershell) -> None:
    # Given

    # When
    description = powershell_tool.description

    # Then
    assert description == "Run a Powershell command and returns its output."


@pytest.mark.parametrize(
    "expected_guideline",
    [
        "Use powershell commands only (eg. use 'Invoke-WebRequest' not 'curl' or 'wget').",
        "Ensure correct command separators: Use ; when chaining commands.",
    ],
)
def test_get_guidelines_always_includes_core_rule(powershell_tool: Powershell, expected_guideline: str) -> None:
    # Given

    # When
    guidelines = powershell_tool.get_guidelines()

    # Then
    assert expected_guideline in guidelines


# name property tests


def test_name_returns_lowercase_class_name(powershell_tool: Powershell) -> None:
    # Given

    # When
    name = powershell_tool.name

    # Then
    assert name == "powershell"
