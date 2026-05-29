from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from frugalbot.events import (
    QuestionResponse,
    UserChoiceInteractionEvent,
    UserCompositeInteractionEvent,
)
from frugalbot.hooks.base import ApprovalState, PreToolCallHook
from frugalbot.hooks.manual_approval import ManualApprovalConfig, ManualApprovalHook


class FakeFileSystem:
    def __init__(self) -> None:
        self.files: dict[str, Any] = {}

    def open(self, path: Any, mode: str = "r", **kwargs: Any) -> Any:
        path_str = str(path)
        if "r" in mode:
            content = self.files.get(path_str, b"{}")
            return FakeFile(content, "r", self, path_str)
        elif "w" in mode or "wb" in mode:
            return FakeFile(b"", mode, self, path_str)
        raise ValueError(f"Unsupported mode: {mode}")


class FakeFile:
    def __init__(self, content: Any, mode: str, fs: FakeFileSystem, path: str):
        self.content = content
        self.mode = mode
        self.fs = fs
        self.path = path

    async def read(self) -> str:
        return self.content.decode() if isinstance(self.content, bytes) else self.content

    async def write(self, data: Any) -> None:
        self.content = data
        self.fs.files[self.path] = data

    async def __aenter__(self) -> FakeFile:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


@pytest.fixture
def fake_fs() -> FakeFileSystem:
    return FakeFileSystem()


@pytest.fixture
def mock_bus():
    mock = AsyncMock()
    with patch("frugalbot.hooks.manual_approval.bus", mock):
        yield mock


@pytest.fixture
def config() -> ManualApprovalConfig:
    return ManualApprovalConfig(enabled=True, approved_tool_calls_path=Path("/fake/approved_tools.json"))


@pytest.fixture
async def hook(config: ManualApprovalConfig, mock_bus: Any, fake_fs: FakeFileSystem) -> AsyncGenerator[ManualApprovalHook]:
    with (
        patch("frugalbot.hooks.manual_approval.aiofiles.open", side_effect=fake_fs.open),
        patch("frugalbot.hooks.manual_approval.Path.exists", return_value=True),
    ):
        p = ManualApprovalHook(config)
        yield p


async def test_run_with_already_approved_state_does_nothing(hook: ManualApprovalHook, mock_bus: Any) -> None:
    # Given
    hook_data = PreToolCallHook(tool_name="test_tool", arguments={"a": 1}, state=ApprovalState.APPROVED)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.APPROVED
    mock_bus.emit_and_handle.assert_not_called()


async def test_run_with_already_denied_state_does_nothing(hook: ManualApprovalHook, mock_bus: Any) -> None:
    # Given
    hook_data = PreToolCallHook(tool_name="test_tool", arguments={"a": 1}, state=ApprovalState.DENIED)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.DENIED
    mock_bus.emit_and_handle.assert_not_called()


async def test_run_with_pre_approved_tool_sets_state_approved(hook: ManualApprovalHook, mock_bus: Any, fake_fs: FakeFileSystem) -> None:
    # Given
    tool_name = "test_tool"
    args = {"a": 1}
    import orjson as json

    fake_fs.files[str(hook.config.approved_tool_calls_path)] = json.dumps({tool_name: [args]})
    hook_data = PreToolCallHook(tool_name=tool_name, arguments=args)

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.APPROVED
    mock_bus.emit_and_handle.assert_not_called()


async def test_run_with_user_yes_sets_state_approved(hook: ManualApprovalHook, mock_bus: Any) -> None:
    # Given
    hook_data = PreToolCallHook(tool_name="test_tool", arguments={"a": 1})

    async def mock_emit_and_handle(e: Any) -> None:
        if isinstance(e, UserChoiceInteractionEvent):
            e.future.set_result(QuestionResponse.YES)

    mock_bus.emit_and_handle.side_effect = mock_emit_and_handle

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.APPROVED
    mock_bus.emit_and_handle.assert_called_once()


async def test_run_with_user_always_sets_state_approved_and_saves(hook: ManualApprovalHook, mock_bus: Any, fake_fs: FakeFileSystem) -> None:
    # Given
    tool_name = "test_tool"
    args = {"a": 1}
    hook_data = PreToolCallHook(tool_name=tool_name, arguments=args)

    async def mock_emit_and_handle(e: Any) -> None:
        if isinstance(e, UserChoiceInteractionEvent):
            e.future.set_result(QuestionResponse.ALWAYS)

    mock_bus.emit_and_handle.side_effect = mock_emit_and_handle

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.APPROVED

    import orjson as json

    saved_content = json.loads(fake_fs.files[str(hook.config.approved_tool_calls_path)])
    assert tool_name in saved_content
    assert saved_content[tool_name][0] == args


async def test_run_with_user_no_no_feedback_sets_state_denied(hook: ManualApprovalHook, mock_bus: Any) -> None:
    # Given
    hook_data = PreToolCallHook(tool_name="test_tool", arguments={"a": 1})

    async def mock_emit_and_handle(e: Any) -> None:
        if isinstance(e, UserChoiceInteractionEvent):
            e.future.set_result(QuestionResponse.NO)
        elif isinstance(e, UserCompositeInteractionEvent):
            e.future.set_result((QuestionResponse.NO, ""))

    mock_bus.emit_and_handle.side_effect = mock_emit_and_handle

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.DENIED
    assert not hook_data.denied_reason


async def test_run_with_user_no_with_feedback_sets_state_denied_with_reason(hook: ManualApprovalHook, mock_bus: Any) -> None:
    # Given
    hook_data = PreToolCallHook(tool_name="test_tool", arguments={"a": 1})
    feedback = "Don't do this"

    async def mock_emit_and_handle(e: Any) -> None:
        if isinstance(e, UserChoiceInteractionEvent):
            e.future.set_result(QuestionResponse.NO)
        elif isinstance(e, UserCompositeInteractionEvent):
            e.future.set_result((QuestionResponse.YES, feedback))

    mock_bus.emit_and_handle.side_effect = mock_emit_and_handle

    # When
    await hook.run(hook_data)

    # Then
    assert hook_data.state == ApprovalState.DENIED
    assert hook_data.denied_reason == feedback


async def test_run_with_user_always_saves_without_duplicates(hook: ManualApprovalHook, mock_bus: Any, fake_fs: FakeFileSystem) -> None:
    # Given
    tool_name = "test_tool"
    args = {"a": 1}
    hook_data = PreToolCallHook(tool_name=tool_name, arguments=args)

    async def mock_emit_and_handle(e: Any) -> None:
        if isinstance(e, UserChoiceInteractionEvent):
            e.future.set_result(QuestionResponse.ALWAYS)

    mock_bus.emit_and_handle.side_effect = mock_emit_and_handle

    # When
    await hook.run(hook_data)
    # Simulate another call for the same tool and args
    await hook.run(hook_data)

    # Then
    import orjson as json

    saved_content = json.loads(fake_fs.files[str(hook.config.approved_tool_calls_path)])
    assert len(saved_content[tool_name]) == 1


async def test_save_to_pre_approved_tools_does_not_write_file_if_no_change(hook: ManualApprovalHook, mock_bus: Any, fake_fs: FakeFileSystem) -> None:
    # Given
    tool_name = "test_tool"
    args = {"a": 1}
    # Pre-load the tool into the hook's memory
    hook.pre_approved_tool_calls = {tool_name: [args]}

    # Use a mock to track calls to aiofiles.open
    with patch("frugalbot.hooks.manual_approval.aiofiles.open", wraps=fake_fs.open) as mock_open:
        # When
        await hook._save_to_pre_approved_tools(tool_name, args)

        # Then
        mock_open.assert_not_called()


async def test_run_loads_pre_approved_tools_on_first_run_only(hook: ManualApprovalHook, mock_bus: Any, fake_fs: FakeFileSystem) -> None:
    # Given
    tool_name = "test_tool"
    args = {"a": 1}
    import orjson as json

    fake_fs.files[str(hook.config.approved_tool_calls_path)] = json.dumps({tool_name: [args]})

    hook_data_1 = PreToolCallHook(tool_name=tool_name, arguments=args)
    hook_data_2 = PreToolCallHook(tool_name=tool_name, arguments=args)

    # When
    await hook.run(hook_data_1)
    await hook.run(hook_data_2)

    # Then
    assert hook_data_1.state == ApprovalState.APPROVED
    assert hook_data_2.state == ApprovalState.APPROVED
    # bus.emit_and_handle should not be called for either (both pre-approved)
    mock_bus.emit_and_handle.assert_not_called()
