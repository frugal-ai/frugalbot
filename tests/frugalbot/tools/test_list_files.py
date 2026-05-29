from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from frugalbot.tools.base import ToolConfig, ToolError
from frugalbot.tools.list_files import ListFiles


@pytest.fixture
def tool() -> ListFiles:
    return ListFiles(ToolConfig())


async def test_run_with_valid_path_and_recursive_returns_files(tool: ListFiles) -> None:
    # Given
    path = "src"
    mock_file1 = MagicMock(spec=Path)
    mock_file1.as_posix.return_value = "src/main.py"
    mock_file1.is_dir.return_value = False

    mock_file2 = MagicMock(spec=Path)
    mock_file2.as_posix.return_value = "src/utils.py"
    mock_file2.is_dir.return_value = False

    with patch("frugalbot.tools.list_files.Path") as mock_path_class, patch("frugalbot.tools.list_files.list_files") as mock_list_files, patch("frugalbot.tools.list_files.bus.emit_and_handle"):
        mock_path_obj = mock_path_class.return_value
        mock_path_obj.exists.return_value = True
        mock_path_obj.is_dir.return_value = True
        mock_list_files.return_value = [mock_file1, mock_file2]

        # When
        result = await tool.run(path=path, recursive=True)

        # Then
        assert result.files == ["src/main.py", "src/utils.py"]


async def test_run_with_valid_path_and_non_recursive_returns_files(tool: ListFiles) -> None:
    # Given
    path = "src"
    mock_file = MagicMock(spec=Path)
    mock_file.as_posix.return_value = "src/main.py"
    mock_file.is_dir.return_value = False

    with patch("frugalbot.tools.list_files.Path") as mock_path_class, patch("frugalbot.tools.list_files.bus.emit_and_handle"):
        mock_path_obj = mock_path_class.return_value
        mock_path_obj.exists.return_value = True
        mock_path_obj.is_dir.return_value = True
        mock_path_obj.glob.return_value = [mock_file]

        # Mock Path.cwd() / ".gitignore" to not exist
        mock_cwd = MagicMock(spec=Path)
        mock_path_class.cwd.return_value = mock_cwd
        mock_gitignore_path = MagicMock(spec=Path)
        mock_cwd.__truediv__.return_value = mock_gitignore_path
        mock_gitignore_path.exists.return_value = False

        # When
        result = await tool.run(path=path, recursive=False, respect_gitignore=True)

        # Then
        assert result.files == ["src/main.py"]


async def test_run_with_non_existent_path_raises_tool_error(tool: ListFiles) -> None:
    # Given
    path = "non_existent"
    with patch("frugalbot.tools.list_files.Path") as mock_path_class:
        mock_path_obj = mock_path_class.return_value
        mock_path_obj.exists.return_value = False

        # When & Then
        with pytest.raises(ToolError, match="path must exist"):
            await tool.run(path=path)


async def test_run_with_file_path_raises_tool_error(tool: ListFiles) -> None:
    # Given
    path = "src/main.py"
    with patch("frugalbot.tools.list_files.Path") as mock_path_class:
        mock_path_obj = mock_path_class.return_value
        mock_path_obj.exists.return_value = True
        mock_path_obj.is_dir.return_value = False

        # When & Then
        with pytest.raises(ToolError, match="path must be a directory"):
            await tool.run(path=path)


async def test_run_with_limit_returns_truncated_files(tool: ListFiles) -> None:
    # Given
    path = "src"
    mock_files = []
    for i in range(5):
        m = MagicMock(spec=Path)
        m.as_posix.return_value = f"src/file{i}.py"
        m.is_dir.return_value = False
        mock_files.append(m)

    with patch("frugalbot.tools.list_files.Path") as mock_path_class, patch("frugalbot.tools.list_files.list_files") as mock_list_files, patch("frugalbot.tools.list_files.bus.emit_and_handle"):
        mock_path_obj = mock_path_class.return_value
        mock_path_obj.exists.return_value = True
        mock_path_obj.is_dir.return_value = True
        mock_list_files.return_value = mock_files

        # When
        result = await tool.run(path=path, recursive=True, limit=2)

        # Then
        assert len(result.files) == 2
        assert result.files == ["src/file0.py", "src/file1.py"]


async def test_run_with_respect_gitignore_false_and_non_recursive_returns_all_files(tool: ListFiles) -> None:
    # Given
    path = "src"
    mock_file1 = MagicMock(spec=Path)
    mock_file1.as_posix.return_value = "src/main.py"
    mock_file1.is_dir.return_value = False

    mock_file2 = MagicMock(spec=Path)
    mock_file2.as_posix.return_value = "src/debug.log"
    mock_file2.is_dir.return_value = False

    with patch("frugalbot.tools.list_files.Path") as mock_path_class, patch("frugalbot.tools.list_files.bus.emit_and_handle"):
        mock_path_obj = mock_path_class.return_value
        mock_path_obj.exists.return_value = True
        mock_path_obj.is_dir.return_value = True
        mock_path_obj.glob.return_value = [mock_file1, mock_file2]

        # When
        result = await tool.run(path=path, recursive=False, respect_gitignore=False)

        # Then
        assert result.files == ["src/debug.log", "src/main.py"]


async def test_run_with_respect_gitignore_true_and_non_recursive_filters_files(tool: ListFiles) -> None:
    # Given
    path = "src"
    mock_file1 = MagicMock(spec=Path)
    mock_file1.as_posix.return_value = "src/main.py"
    mock_file1.is_dir.return_value = False

    mock_file2 = MagicMock(spec=Path)
    mock_file2.as_posix.return_value = "src/debug.log"
    mock_file2.is_dir.return_value = False

    with patch("frugalbot.tools.list_files.Path") as mock_path_class, patch("frugalbot.tools.list_files.bus.emit_and_handle"):
        mock_path_obj = mock_path_class.return_value
        mock_path_obj.exists.return_value = True
        mock_path_obj.is_dir.return_value = True
        mock_path_obj.glob.return_value = [mock_file1, mock_file2]

        # Mock Path.cwd() / ".gitignore"
        mock_cwd = MagicMock(spec=Path)
        mock_path_class.cwd.return_value = mock_cwd
        mock_gitignore_path = MagicMock(spec=Path)
        mock_cwd.__truediv__.return_value = mock_gitignore_path
        mock_gitignore_path.exists.return_value = True
        mock_gitignore_path.read_text.return_value = "*.log"

        # When
        result = await tool.run(path=path, recursive=False, respect_gitignore=True)

        # Then
        assert result.files == ["src/main.py"]


async def test_list_files():
    lf = ListFiles(ToolConfig(enabled=True))
    result = await lf.run(recursive=True)
    print(result.files)
    assert ".git/" not in result.files
