import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from frugalbot.tools.base import ToolConfig, ToolError
from frugalbot.tools.powershell import Powershell, _translate_path_for_powershell

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Tests in this file require Windows",
)


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
        "uv run pytest tests/frugalbot/test_nothing.py 2>&1 | Select-Object -Last 40",
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


# _translate_path_for_powershell() tests


def test_translate_path_for_powershell_with_windows_path_returns_unchanged() -> None:
    # Given
    windows_path = "C:\\Users\\test"

    # When
    result = _translate_path_for_powershell(windows_path)

    # Then
    assert result == windows_path


def test_translate_path_for_powershell_with_command_returns_unchanged_when_wslpath_missing() -> None:
    # Given
    command = "Get-ChildItem -Path '/tmp/test'"

    # When
    with patch("frugalbot.tools.powershell.shutil.which", return_value=None):
        result = _translate_path_for_powershell(command)

    # Then
    assert result == command


def test_translate_path_for_powershell_with_command_returns_unchanged_when_wslpath_fails() -> None:
    # Given
    command = "Get-ChildItem -Path '/tmp/test'"

    # When
    with patch("frugalbot.tools.powershell.subprocess.run") as run_mock:
        run_mock.return_value.returncode = 1
        run_mock.return_value.stdout = ""
        result = _translate_path_for_powershell(command)

    # Then
    assert result == command
