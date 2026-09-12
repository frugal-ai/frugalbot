from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, cast
from unittest.mock import MagicMock, patch

import pytest
from cachier import disable_caching, enable_caching
from pytest_mock import MockerFixture

from frugalbot.utils.filesystem import list_files_with_cache


@pytest.fixture(autouse=True, scope="session")
def disable_cachier_globally() -> Generator[None]:
    disable_caching()
    yield
    enable_caching()


class _ControlledDateTime(datetime):
    """Stand-in for ``datetime.datetime`` that lets a test freeze time."""

    current: ClassVar[datetime] = datetime(2020, 1, 1, 0, 0, 0)

    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        return cls.current


@pytest.fixture
def cache_with_controlled_clock(mocker: MockerFixture) -> Generator[None]:
    enable_caching()
    cast(Any, list_files_with_cache).clear_cache()
    mocker.patch("cachier.core.datetime", _ControlledDateTime)
    mocker.patch("cachier.cores.memory.datetime", _ControlledDateTime)
    _ControlledDateTime.current = datetime(2020, 1, 1, 0, 0, 0)
    yield
    cast(Any, list_files_with_cache).clear_cache()
    disable_caching()


@patch("frugalbot.utils.filesystem.list_files")
def test_calls_list_files_with_cwd(mock_list_files: MagicMock) -> None:
    # Given
    path = Path.cwd()
    mock_list_files.return_value = [Path("file1.py"), Path("file2.py")]

    # When
    result = list_files_with_cache(path)

    # Then
    mock_list_files.assert_called_once_with([path])
    assert result == [Path("file1.py"), Path("file2.py")]


@patch("frugalbot.utils.filesystem.list_files")
def test_multiple_calls_return_same_result(mock_list_files: MagicMock) -> None:
    # Given
    path = Path.cwd()
    mock_list_files.return_value = [Path("file1.py")]

    # When
    result1 = list_files_with_cache(path)
    result2 = list_files_with_cache(path)

    # Then - both calls return the same value
    assert result1 == result2


def test_list_files_with_cache_entry_stale_returns_updated_files(mocker: MockerFixture, cache_with_controlled_clock: None) -> None:
    # Given
    path = Path.cwd()
    mocked_list_files = mocker.patch("frugalbot.utils.filesystem.list_files", side_effect=lambda _paths: [Path("old.py")])
    list_files_with_cache(path)
    mocked_list_files.side_effect = lambda _paths: [Path("new.py")]
    _ControlledDateTime.current = datetime(2020, 1, 1, 0, 0, 6)

    # When
    result = list_files_with_cache(path)

    # Then
    assert result == [Path("new.py")]
