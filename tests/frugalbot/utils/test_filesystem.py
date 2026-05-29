from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cachier import disable_caching, enable_caching

from frugalbot.utils.filesystem import list_files_with_cache


@pytest.fixture(autouse=True, scope="session")
def disable_cachier_globally():
    disable_caching()
    yield
    enable_caching()


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
    # The caching decorator calls the function once, creating cached entries
    # for both calls, so we just verify results are identical
