import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from frugalbot.tools.bash import _run_bash


@pytest.fixture()
def mock_bus() -> Generator[MagicMock]:
    with patch("frugalbot.tools.bash.bus") as mock:
        mock.emit_and_handle = AsyncMock()
        yield mock


def _make_process(returncode: int = 0) -> MagicMock:
    reader = asyncio.StreamReader()
    reader.feed_eof()
    proc = MagicMock()
    proc.wait = AsyncMock(return_value=returncode)
    proc.returncode = returncode
    proc.pid = 1234
    proc.stdout = reader
    return proc


# _run_bash() environment tests


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("CI", "true"),
        ("NO_COLOR", "1"),
        ("TERM", "dumb"),
    ],
)
async def test_run_bash_with_any_command_defines_env_var_for_subprocess(mock_bus: MagicMock, name: str, value: str) -> None:
    # Given
    proc = _make_process()
    with patch("frugalbot.tools.bash.asyncio.create_subprocess_exec", return_value=proc) as create_process:
        # When
        await _run_bash("echo hello", 5)

    # Then
    assert create_process.call_args.kwargs["env"][name] == value
