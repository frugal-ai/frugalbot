import builtins
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import orjson as json
import pytest
from pyfakefs.fake_filesystem import FakeFilesystem
from pytest_mock import MockerFixture

from frugalbot.events import QuestionResponse, UserChoiceInteractionEvent, UserCompositeInteractionEvent
from frugalbot.hooks.base import ApprovalState, PreToolCallHook
from frugalbot.hooks.manual_approval import ManualApprovalConfig, ManualApprovalHook

_FEEDBACK = "Don't do this"


@pytest.fixture
def fs_aiofiles(fs: FakeFilesystem, mocker: MockerFixture) -> FakeFilesystem:
    mocker.patch("aiofiles.threadpool.sync_open", builtins.open)
    return fs


@pytest.fixture
def config(fs_aiofiles: FakeFilesystem) -> ManualApprovalConfig:
    return ManualApprovalConfig(approved_tool_calls_path=Path("/frugalbot/approved_tools.json"))


@pytest.fixture
def mock_bus(mocker: MockerFixture) -> AsyncMock:
    return mocker.patch("frugalbot.hooks.manual_approval.bus", AsyncMock())


async def _respond_yes(event: Any) -> None:
    event.future.set_result(QuestionResponse.YES)


async def _respond_always(event: Any) -> None:
    event.future.set_result(QuestionResponse.ALWAYS)


async def _respond_denied(event: Any) -> None:
    responses: dict[type, Any] = {
        UserChoiceInteractionEvent: QuestionResponse.NO,
        UserCompositeInteractionEvent: (QuestionResponse.NO, ""),
    }
    event.future.set_result(responses[type(event)])


async def _respond_denied_with_feedback(event: Any) -> None:
    responses: dict[type, Any] = {
        UserChoiceInteractionEvent: QuestionResponse.NO,
        UserCompositeInteractionEvent: (QuestionResponse.YES, _FEEDBACK),
    }
    event.future.set_result(responses[type(event)])


def _write_approved_tools(path: Path, entries: dict[str, list[dict[str, Any]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(entries))


def test_manual_approval_config_when_path_uses_tilde_expands_user() -> None:
    # Given / When
    config = ManualApprovalConfig(approved_tool_calls_path=Path("~/.frugalbot/approved_tools.json"))

    # Then
    assert config.approved_tool_calls_path == Path.home() / ".frugalbot/approved_tools.json"


def test_is_pre_approved_when_incoming_has_timeout_and_saved_does_not_returns_true(config: ManualApprovalConfig) -> None:
    # Given
    hook = ManualApprovalHook(config)
    hook.pre_approved_tool_calls = {"powershell": [{"command": "pytest"}]}

    # When
    result = hook._is_pre_approved("powershell", {"command": "pytest", "timeout_in_seconds": 45})

    # Then
    assert result is True


def test_is_pre_approved_when_saved_has_timeout_and_incoming_does_not_returns_true(config: ManualApprovalConfig) -> None:
    # Given
    hook = ManualApprovalHook(config)
    hook.pre_approved_tool_calls = {"powershell": [{"command": "pytest", "timeout_in_seconds": 20}]}

    # When
    result = hook._is_pre_approved("powershell", {"command": "pytest"})

    # Then
    assert result is True


def test_is_pre_approved_when_timeouts_differ_returns_true(config: ManualApprovalConfig) -> None:
    # Given
    hook = ManualApprovalHook(config)
    hook.pre_approved_tool_calls = {"powershell": [{"command": "pytest", "timeout_in_seconds": 30}]}

    # When
    result = hook._is_pre_approved("powershell", {"command": "pytest", "timeout_in_seconds": 60})

    # Then
    assert result is True


def test_is_pre_approved_when_command_differs_returns_false(config: ManualApprovalConfig) -> None:
    # Given
    hook = ManualApprovalHook(config)
    hook.pre_approved_tool_calls = {"powershell": [{"command": "pytest"}]}

    # When
    result = hook._is_pre_approved("powershell", {"command": "pytest -v", "timeout_in_seconds": 45})

    # Then
    assert result is False


async def test_save_to_pre_approved_tools_strips_timeout_in_seconds(config: ManualApprovalConfig, fs_aiofiles: FakeFilesystem) -> None:
    # Given
    hook = ManualApprovalHook(config)
    hook.pre_approved_tool_calls = {}

    # When
    await hook._save_to_pre_approved_tools("powershell", {"command": "git status", "timeout_in_seconds": 20})

    # Then
    assert json.loads(config.approved_tool_calls_path.read_bytes()) == {"powershell": [{"command": "git status"}]}


async def test_save_to_pre_approved_tools_with_duplicate_calls_stores_single_entry(config: ManualApprovalConfig, fs_aiofiles: FakeFilesystem) -> None:
    # Given
    hook = ManualApprovalHook(config)
    hook.pre_approved_tool_calls = {}

    # When
    await hook._save_to_pre_approved_tools("test_tool", {"a": 1})
    await hook._save_to_pre_approved_tools("test_tool", {"a": 1})

    # Then
    assert json.loads(config.approved_tool_calls_path.read_bytes()) == {"test_tool": [{"a": 1}]}


async def test_save_to_pre_approved_tools_with_existing_entry_does_not_write_file(config: ManualApprovalConfig, fs_aiofiles: FakeFilesystem, mocker: MockerFixture) -> None:
    # Given
    hook = ManualApprovalHook(config)
    hook.pre_approved_tool_calls = {"test_tool": [{"a": 1}]}
    mock_open = mocker.patch("frugalbot.hooks.manual_approval.aiofiles.open")

    # When
    await hook._save_to_pre_approved_tools("test_tool", {"a": 1})

    # Then
    mock_open.assert_not_called()


async def test_save_to_pre_approved_tools_creates_missing_parent_directory(fs_aiofiles: FakeFilesystem) -> None:
    # Given
    config = ManualApprovalConfig(approved_tool_calls_path=Path("/frugalbot/nested/deep/approved_tools.json"))
    hook = ManualApprovalHook(config)
    hook.pre_approved_tool_calls = {}

    # When
    await hook._save_to_pre_approved_tools("powershell", {"command": "pytest"})

    # Then
    assert json.loads(config.approved_tool_calls_path.read_bytes()) == {"powershell": [{"command": "pytest"}]}


async def test_pre_approved_tools_survives_restart_simulation(config: ManualApprovalConfig, fs_aiofiles: FakeFilesystem, mock_bus: AsyncMock) -> None:
    # Given
    saved_hook = ManualApprovalHook(config)
    saved_hook.pre_approved_tool_calls = {}
    await saved_hook._save_to_pre_approved_tools("powershell", {"command": "pytest", "timeout_in_seconds": 45})
    restarted_hook = ManualApprovalHook(config)
    hook_data = PreToolCallHook(tool_name="powershell", arguments={"command": "pytest"})

    # When
    await restarted_hook.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.APPROVED


async def test_run_with_already_approved_state_does_nothing(config: ManualApprovalConfig, mock_bus: AsyncMock) -> None:
    # Given
    hook = ManualApprovalHook(config)
    hook_data = PreToolCallHook(tool_name="test_tool", arguments={"a": 1}, state=ApprovalState.APPROVED)

    # When
    await hook.run(hook_data)

    # Then
    mock_bus.emit_and_handle.assert_not_called()


async def test_run_with_already_denied_state_does_nothing(config: ManualApprovalConfig, mock_bus: AsyncMock) -> None:
    # Given
    hook = ManualApprovalHook(config)
    hook_data = PreToolCallHook(tool_name="test_tool", arguments={"a": 1}, state=ApprovalState.DENIED)

    # When
    await hook.run(hook_data)

    # Then
    mock_bus.emit_and_handle.assert_not_called()


async def test_run_with_pre_approved_tool_sets_state_approved(config: ManualApprovalConfig, fs_aiofiles: FakeFilesystem, mock_bus: AsyncMock) -> None:
    # Given
    _write_approved_tools(config.approved_tool_calls_path, {"test_tool": [{"a": 1}]})
    hook = ManualApprovalHook(config)
    hook_data = PreToolCallHook(tool_name="test_tool", arguments={"a": 1})

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.APPROVED


async def test_run_loads_pre_approved_tools_on_first_run_only(config: ManualApprovalConfig, fs_aiofiles: FakeFilesystem, mock_bus: AsyncMock) -> None:
    # Given
    _write_approved_tools(config.approved_tool_calls_path, {"test_tool": [{"a": 1}]})
    hook = ManualApprovalHook(config)
    first_call = PreToolCallHook(tool_name="test_tool", arguments={"a": 1})
    second_call = PreToolCallHook(tool_name="test_tool", arguments={"a": 1})

    # When
    await hook.run(first_call)
    await hook.run(second_call)

    # Then
    mock_bus.emit_and_handle.assert_not_called()


async def test_run_with_user_yes_sets_state_approved(config: ManualApprovalConfig, fs_aiofiles: FakeFilesystem, mock_bus: AsyncMock) -> None:
    # Given
    hook = ManualApprovalHook(config)
    hook_data = PreToolCallHook(tool_name="test_tool", arguments={"a": 1})
    mock_bus.emit_and_handle.side_effect = _respond_yes

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.APPROVED


async def test_run_with_user_always_sets_state_approved_and_saves(config: ManualApprovalConfig, fs_aiofiles: FakeFilesystem, mock_bus: AsyncMock) -> None:
    # Given
    hook = ManualApprovalHook(config)
    hook_data = PreToolCallHook(tool_name="test_tool", arguments={"a": 1})
    mock_bus.emit_and_handle.side_effect = _respond_always

    # When
    await hook.run(hook_data)

    # Then
    assert json.loads(config.approved_tool_calls_path.read_bytes()) == {"test_tool": [{"a": 1}]}


async def test_run_with_user_no_no_feedback_sets_state_denied(config: ManualApprovalConfig, fs_aiofiles: FakeFilesystem, mock_bus: AsyncMock) -> None:
    # Given
    hook = ManualApprovalHook(config)
    hook_data = PreToolCallHook(tool_name="test_tool", arguments={"a": 1})
    mock_bus.emit_and_handle.side_effect = _respond_denied

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.DENIED


async def test_run_with_user_no_with_feedback_sets_state_denied_with_reason(config: ManualApprovalConfig, fs_aiofiles: FakeFilesystem, mock_bus: AsyncMock) -> None:
    # Given
    hook = ManualApprovalHook(config)
    hook_data = PreToolCallHook(tool_name="test_tool", arguments={"a": 1})
    mock_bus.emit_and_handle.side_effect = _respond_denied_with_feedback

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.denied_reason == _FEEDBACK
