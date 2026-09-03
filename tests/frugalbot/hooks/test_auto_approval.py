import sys
from unittest.mock import AsyncMock, patch

import pytest

from frugalbot.hooks.auto_approval import AutoApprovalConfig, AutoApprovalHook, _is_match
from frugalbot.hooks.base import ApprovalState, PreToolCallHook


def test_is_match_with_identical_lists_returns_true():
    # Given
    a = ["echo", "hello"]
    b = ["echo", "hello"]

    # When
    result = _is_match(a, b)

    # Then
    assert result is True


def test_is_match_with_prefix_match_returns_true():
    # Given
    a = ["echo"]
    b = ["echo", "hello", "world"]

    # When
    result = _is_match(a, b)

    # Then
    assert result is True


def test_is_match_with_dontcare_wildcard_returns_true():
    # Given
    a = ["echo", "DONTCARE"]
    b = ["echo", "anything_here"]

    # When
    result = _is_match(a, b)

    # Then
    assert result is True


def test_is_match_with_b_shorter_than_a_returns_false():
    # Given
    a = ["echo", "hello"]
    b = ["echo"]

    # When
    result = _is_match(a, b)

    # Then
    assert result is False


def test_is_match_with_mismatched_elements_returns_false():
    # Given
    a = ["echo"]
    b = ["mkdir", "plans"]

    # When
    result = _is_match(a, b)

    # Then
    assert result is False


def test_is_match_with_empty_a_returns_true():
    # Given
    a: list[str] = []
    b = ["echo", "hello"]

    # When
    result = _is_match(a, b)

    # Then
    assert result is True


def _make_hook_data(tool_name: str, arguments: dict[str, str]) -> PreToolCallHook:
    return PreToolCallHook(tool_name=tool_name, arguments=arguments)


@pytest.fixture
def shell_tool_name() -> str:
    return "powershell" if sys.platform == "win32" else "bash"


async def test_run_with_already_approved_state_leaves_state_approved(shell_tool_name):
    # Given
    config = AutoApprovalConfig(enabled=True, exempted=[], allowed=[], denied=[])
    auto_approval = AutoApprovalHook(config)
    hook_data = PreToolCallHook(
        tool_name=shell_tool_name,
        arguments={"command": "echo hello"},
        state=ApprovalState.APPROVED,
    )

    # When
    await auto_approval.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.APPROVED


async def test_run_with_already_denied_state_leaves_state_denied(shell_tool_name):
    # Given
    config = AutoApprovalConfig(enabled=True, exempted=[], allowed=[["echo"]], denied=[])
    auto_approval = AutoApprovalHook(config)
    hook_data = PreToolCallHook(
        tool_name=shell_tool_name,
        arguments={"command": "echo hello"},
        state=ApprovalState.DENIED,
    )

    # When
    await auto_approval.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.DENIED


async def test_run_with_listfiles_tool_is_approved():
    # Given
    config = AutoApprovalConfig(enabled=True, exempted=[], allowed=[], denied=[])
    auto_approval = AutoApprovalHook(config)
    hook_data = _make_hook_data("listfiles", {})

    # When
    await auto_approval.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.APPROVED


async def test_run_with_relative_path_is_approved():
    # Given
    config = AutoApprovalConfig(enabled=True, exempted=[], allowed=[], denied=[])
    auto_approval = AutoApprovalHook(config)
    hook_data = _make_hook_data("edit", {"path": "src/main.py"})

    # When
    await auto_approval.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.APPROVED


async def test_run_with_relative_path_with_leading_whitespace_is_approved():
    # Given
    config = AutoApprovalConfig(enabled=True, exempted=[], allowed=[], denied=[])
    auto_approval = AutoApprovalHook(config)
    hook_data = _make_hook_data("edit", {"path": "  src/main.py"})

    # When
    await auto_approval.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.APPROVED


async def test_run_with_unix_absolute_path_is_denied():
    # Given
    config = AutoApprovalConfig(enabled=True, exempted=[], allowed=[], denied=[])
    auto_approval = AutoApprovalHook(config)
    hook_data = _make_hook_data("edit", {"path": "/etc/passwd"})

    # When
    await auto_approval.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.DENIED


async def test_run_with_unix_absolute_path_sets_denied_reason():
    # Given
    config = AutoApprovalConfig(enabled=True, exempted=[], allowed=[], denied=[])
    auto_approval = AutoApprovalHook(config)
    hook_data = _make_hook_data("edit", {"path": "/etc/passwd"})

    # When
    await auto_approval.run(hook_data)

    # Then
    assert hook_data.denied_reason == "Absolute paths are not allowed"


@pytest.fixture
def absolute_path() -> str:
    return "\\Users\\admin\\file.txt" if sys.platform == "win32" else "/etc/sudo.conf"


async def test_run_with_windows_absolute_path_is_denied(absolute_path):
    # Given
    config = AutoApprovalConfig(enabled=True, exempted=[], allowed=[], denied=[])
    auto_approval = AutoApprovalHook(config)
    hook_data = _make_hook_data("edit", {"path": absolute_path})

    # When
    await auto_approval.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.DENIED


async def test_run_with_subshell_in_command_leaves_state_not_set(shell_tool_name):
    # Given
    config = AutoApprovalConfig(enabled=True, exempted=[], allowed=[["echo"]], denied=[])
    auto_approval = AutoApprovalHook(config)
    hook_data = _make_hook_data(shell_tool_name, {"command": "echo $(malware.exe)"})

    # When
    await auto_approval.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.NOT_SET


async def test_run_with_all_commands_allowed_is_approved(shell_tool_name):
    # Given
    config = AutoApprovalConfig(enabled=True, exempted=[], allowed=[["echo"], ["mkdir"]], denied=[])
    auto_approval = AutoApprovalHook(config)
    hook_data = _make_hook_data(shell_tool_name, {"command": "echo hello; mkdir plans"})

    # When
    with patch("frugalbot.hooks.auto_approval._split_shell_commands", new_callable=AsyncMock) as mock_split:
        mock_split.return_value = [["echo", "hello"], ["mkdir", "plans"]]
        await auto_approval.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.APPROVED


async def test_run_with_all_commands_exempted_is_approved(shell_tool_name):
    # Given
    config = AutoApprovalConfig(enabled=True, exempted=[["echo"], ["mkdir"]], allowed=[], denied=[])
    auto_approval = AutoApprovalHook(config)
    hook_data = _make_hook_data(shell_tool_name, {"command": "echo hello; mkdir plans"})

    # When
    with patch("frugalbot.hooks.auto_approval._split_shell_commands", new_callable=AsyncMock) as mock_split:
        mock_split.return_value = [["echo", "hello"], ["mkdir", "plans"]]
        await auto_approval.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.APPROVED


async def test_run_with_denied_command_is_denied(shell_tool_name):
    # Given
    config = AutoApprovalConfig(
        enabled=True,
        exempted=[],
        allowed=[["echo"], ["Remove-Item"]],
        denied=[(["Remove-Item", "-Recurse"], "Recursive deletion is not allowed")],
    )
    auto_approval = AutoApprovalHook(config)
    hook_data = _make_hook_data(shell_tool_name, {"command": "Remove-Item -Recurse C:\\temp"})

    # When
    with patch("frugalbot.hooks.auto_approval._split_shell_commands", new_callable=AsyncMock) as mock_split:
        mock_split.return_value = [["Remove-Item", "-Recurse", "C:\\temp"]]
        await auto_approval.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.DENIED


async def test_run_with_denied_command_sets_denied_reason(shell_tool_name):
    # Given
    config = AutoApprovalConfig(
        enabled=True,
        exempted=[],
        allowed=[["echo"], ["Remove-Item"]],
        denied=[(["Remove-Item", "-Recurse"], "Recursive deletion is not allowed")],
    )
    auto_approval = AutoApprovalHook(config)
    hook_data = _make_hook_data(shell_tool_name, {"command": "Remove-Item -Recurse C:\\temp"})

    # When
    with patch("frugalbot.hooks.auto_approval._split_shell_commands", new_callable=AsyncMock) as mock_split:
        mock_split.return_value = [["Remove-Item", "-Recurse", "C:\\temp"]]
        await auto_approval.run(hook_data)

    # Then
    assert hook_data.denied_reason == "Recursive deletion is not allowed"


async def test_run_with_command_not_in_allowed_list_leaves_state_not_set(shell_tool_name):
    # Given
    config = AutoApprovalConfig(enabled=True, exempted=[], allowed=[["echo"]], denied=[])
    auto_approval = AutoApprovalHook(config)
    hook_data = _make_hook_data(shell_tool_name, {"command": "mkdir plans"})

    # When
    with patch("frugalbot.hooks.auto_approval._split_shell_commands", new_callable=AsyncMock) as mock_split:
        mock_split.return_value = [["mkdir", "plans"]]
        await auto_approval.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.NOT_SET


async def test_run_with_partial_command_match_is_approved(shell_tool_name):
    # Given
    config = AutoApprovalConfig(enabled=True, exempted=[], allowed=[["Get-Content"]], denied=[])
    auto_approval = AutoApprovalHook(config)
    hook_data = _make_hook_data(shell_tool_name, {"command": "Get-Content file.txt"})

    # When
    with patch("frugalbot.hooks.auto_approval._split_shell_commands", new_callable=AsyncMock) as mock_split:
        mock_split.return_value = [["Get-Content", "file.txt"]]
        await auto_approval.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.APPROVED


async def test_run_with_dontcare_in_allowed_list_approves_any_argument(shell_tool_name):
    # Given
    config = AutoApprovalConfig(enabled=True, exempted=[], allowed=[["Get-Content", "DONTCARE"]], denied=[])
    auto_approval = AutoApprovalHook(config)
    hook_data = _make_hook_data(shell_tool_name, {"command": "Get-Content any_file.txt"})

    # When
    with patch("frugalbot.hooks.auto_approval._split_shell_commands", new_callable=AsyncMock) as mock_split:
        mock_split.return_value = [["Get-Content", "any_file.txt"]]
        await auto_approval.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.APPROVED
