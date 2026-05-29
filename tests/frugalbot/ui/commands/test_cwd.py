from pathlib import Path
from unittest.mock import Mock

import pytest
import typer
from pyfakefs.fake_filesystem import FakeFilesystem
from pytest_mock import MockerFixture

from frugalbot.ui.commands.cwd import cmd_cwd


@pytest.fixture
def mock_app() -> Mock:
    """Creates a mock Tui app."""
    return Mock()


@pytest.fixture
def mock_ctx(mock_app: Mock, mocker: MockerFixture) -> Mock:
    """Creates a mock typer.Context with app set in obj."""
    ctx = mocker.MagicMock(spec=typer.Context)
    ctx.obj = {"app": mock_app}
    return ctx


# --- Tests for os.chdir exit point (state change) ---


def test_cmd_cwd_with_subdirectory_relative_to_cwd_changes_directory(
    fs: FakeFilesystem,
    mock_ctx: Mock,
) -> None:
    # Given
    cwd = Path.cwd()
    subdir = cwd / "project" / "subdir"
    fs.create_dir(str(subdir))
    fs.cwd = str(cwd / "project")

    # When
    cmd_cwd(mock_ctx, subdir)

    # Then
    assert Path.cwd() == subdir


def test_cmd_cwd_with_directory_outside_cwd_changes_to_absolute_path(
    fs: FakeFilesystem,
    mock_ctx: Mock,
) -> None:
    # Given
    cwd = Path.cwd()
    project_dir = cwd / "project"
    other_dir = cwd / "other" / "dir"
    fs.create_dir(str(project_dir))
    fs.create_dir(str(other_dir))
    fs.cwd = str(project_dir)

    # When
    cmd_cwd(mock_ctx, other_dir)

    # Then
    assert Path.cwd() == other_dir


def test_cmd_cwd_with_path_equal_to_cwd_does_not_change_directory(
    fs: FakeFilesystem,
    mock_ctx: Mock,
) -> None:
    # Given
    cwd = Path.cwd()
    project_dir = cwd / "project"
    fs.create_dir(str(project_dir))
    fs.cwd = str(project_dir)

    # When
    cmd_cwd(mock_ctx, project_dir)

    # Then
    assert Path.cwd() == project_dir


def test_cmd_cwd_with_nested_subdirectory_relative_to_cwd_changes_directory(
    fs: FakeFilesystem,
    mock_ctx: Mock,
) -> None:
    # Given
    cwd = Path.cwd()
    nested_dir = cwd / "project" / "a" / "b" / "c"
    fs.create_dir(str(nested_dir))
    fs.cwd = str(cwd / "project")

    # When
    cmd_cwd(mock_ctx, nested_dir)

    # Then
    assert Path.cwd() == nested_dir


def test_cmd_cwd_with_parent_directory_changes_to_absolute_path(
    fs: FakeFilesystem,
    mock_ctx: Mock,
) -> None:
    # Given
    cwd = Path.cwd()
    project_dir = cwd / "project"
    nested_dir = project_dir / "sub" / "nested"
    fs.create_dir(str(nested_dir))
    fs.cwd = str(nested_dir)

    # When
    cmd_cwd(mock_ctx, project_dir)

    # Then
    assert Path.cwd() == project_dir


# --- Tests for app.notify exit point (third-party interaction) ---


def test_cmd_cwd_with_subdirectory_relative_to_cwd_notifies_with_relative_path(
    fs: FakeFilesystem,
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given
    cwd = Path.cwd()
    subdir = cwd / "project" / "subdir"
    fs.create_dir(str(subdir))
    fs.cwd = str(cwd / "project")

    # When
    cmd_cwd(mock_ctx, subdir)

    # Then
    mock_app.notify.assert_called_once_with("New cwd is subdir")


def test_cmd_cwd_with_directory_outside_cwd_notifies_with_absolute_path(
    fs: FakeFilesystem,
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given
    cwd = Path.cwd()
    project_dir = cwd / "project"
    other_dir = cwd / "other" / "dir"
    fs.create_dir(str(project_dir))
    fs.create_dir(str(other_dir))
    fs.cwd = str(project_dir)

    # When
    cmd_cwd(mock_ctx, other_dir)

    # Then
    mock_app.notify.assert_called_once_with(f"New cwd is {other_dir}")


def test_cmd_cwd_with_path_equal_to_cwd_notifies_with_dot(
    fs: FakeFilesystem,
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given
    cwd = Path.cwd()
    project_dir = cwd / "project"
    fs.create_dir(str(project_dir))
    fs.cwd = str(project_dir)

    # When
    cmd_cwd(mock_ctx, project_dir)

    # Then
    mock_app.notify.assert_called_once_with("New cwd is .")


def test_cmd_cwd_with_parent_directory_notifies_with_absolute_path(
    fs: FakeFilesystem,
    mock_ctx: Mock,
    mock_app: Mock,
) -> None:
    # Given
    cwd = Path.cwd()
    project_dir = cwd / "project"
    nested_dir = project_dir / "sub" / "nested"
    fs.create_dir(str(nested_dir))
    fs.cwd = str(nested_dir)

    # When
    cmd_cwd(mock_ctx, project_dir)

    # Then
    mock_app.notify.assert_called_once_with(f"New cwd is {project_dir}")
