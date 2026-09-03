import sys
from pathlib import Path

import pytest
from pyfakefs.fake_filesystem import FakeFilesystem

from frugalbot.utils.path import check_and_resolve_path


@pytest.fixture(autouse=True)
def _setup_fs(fs: FakeFilesystem) -> None:
    if sys.platform != "win32":
        fs.create_dir("/basefolder")
        fs.cwd = "/basefolder"
    cwd = Path.cwd()
    fs.create_dir(cwd / "subdir")
    fs.create_file(cwd / "file.txt")
    fs.create_dir(cwd / "nested/deep")
    fs.create_file(cwd / "nested/deep/leaf.txt")


def test_check_and_resolve_path_with_both_exist_flags_raises_value_error() -> None:
    # Given
    path = Path("subdir")

    # When / Then
    with pytest.raises(ValueError, match="invalid parameters"):
        check_and_resolve_path(path, must_exist=True, must_not_exist=True)


def test_check_and_resolve_path_with_string_input_converts_to_path(fs: FakeFilesystem) -> None:
    # Given
    path_str = "file.txt"

    # When
    result = check_and_resolve_path(path_str)

    # Then
    assert isinstance(result, Path)
    assert result.name == "file.txt"


def test_check_and_resolve_path_with_relative_path_resolves_against_cwd() -> None:
    # Given
    path = Path("subdir")

    # When
    result = check_and_resolve_path(path)

    # Then
    assert result == Path.cwd() / "subdir"


def test_check_and_resolve_path_with_absolute_path_returns_as_is(fs: FakeFilesystem) -> None:
    # Given
    abs_path = Path.cwd() / "subdir"

    # When
    result = check_and_resolve_path(abs_path)

    # Then
    assert result == abs_path


@pytest.mark.skipif(sys.platform != "win32", reason="Drive-relative paths are only meaningful on Windows")
def test_check_and_resolve_path_with_path_outside_cwd_raises_value_error(fs: FakeFilesystem) -> None:
    # Given
    fs.create_dir("D:/outside")
    path = Path("D:/outside")

    # When / Then
    with pytest.raises(ValueError, match="path must resolve to a child of the current working directory"):
        check_and_resolve_path(path)


def test_check_and_resolve_path_with_path_outside_cwd_on_posix_raises_value_error(fs: FakeFilesystem) -> None:
    # Given
    fs.create_dir("/outside")
    path = Path("/outside")

    # When / Then
    with pytest.raises(ValueError, match="path must resolve to a child of the current working directory"):
        check_and_resolve_path(path)


def test_check_and_resolve_path_with_must_exist_and_missing_path_raises_value_error() -> None:
    # Given
    path = Path("nonexistent")

    # When / Then
    with pytest.raises(ValueError, match="path must exist"):
        check_and_resolve_path(path, must_exist=True)


def test_check_and_resolve_path_with_must_exist_and_existing_path_returns_path() -> None:
    # Given
    path = Path("subdir")

    # When
    result = check_and_resolve_path(path, must_exist=True)

    # Then
    assert result == Path.cwd() / "subdir"


def test_check_and_resolve_path_with_must_not_exist_and_existing_path_raises_value_error() -> None:
    # Given
    path = Path("file.txt")

    # When / Then
    with pytest.raises(ValueError, match="path already exists"):
        check_and_resolve_path(path, must_exist=False, must_not_exist=True)


def test_check_and_resolve_path_with_must_not_exist_and_missing_path_returns_path() -> None:
    # Given
    path = Path("new_file.txt")

    # When
    result = check_and_resolve_path(path, must_exist=False, must_not_exist=True)

    # Then
    assert result == Path.cwd() / "new_file.txt"


def test_check_and_resolve_path_with_dir_okay_false_and_directory_raises_value_error() -> None:
    # Given
    path = Path("subdir")

    # When / Then
    with pytest.raises(ValueError, match="path is a directory"):
        check_and_resolve_path(path, dir_okay=False)


def test_check_and_resolve_path_with_dir_okay_false_and_file_returns_path() -> None:
    # Given
    path = Path("file.txt")

    # When
    result = check_and_resolve_path(path, dir_okay=False)

    # Then
    assert result == Path.cwd() / "file.txt"


def test_check_and_resolve_path_with_file_okay_false_and_file_raises_value_error() -> None:
    # Given
    path = Path("file.txt")

    # When / Then
    with pytest.raises(ValueError, match="path is a file"):
        check_and_resolve_path(path, file_okay=False)


def test_check_and_resolve_path_with_file_okay_false_and_directory_returns_path() -> None:
    # Given
    path = Path("subdir")

    # When
    result = check_and_resolve_path(path, file_okay=False)

    # Then
    assert result == Path.cwd() / "subdir"


def test_check_and_resolve_path_with_return_absolute_true_returns_absolute_path() -> None:
    # Given
    path = Path("subdir")

    # When
    result = check_and_resolve_path(path, return_absolute=True)

    # Then
    assert result.is_absolute()
    assert result == (Path.cwd() / "subdir").absolute()


def test_check_and_resolve_path_with_return_absolute_false_returns_path_as_is() -> None:
    # Given
    path = Path("subdir")

    # When
    result = check_and_resolve_path(path, return_absolute=False)

    # Then
    assert result == Path.cwd() / "subdir"


def test_check_and_resolve_path_with_default_parameters_returns_resolved_path() -> None:
    # Given
    path = Path("nested/deep/leaf.txt")

    # When
    result = check_and_resolve_path(path)

    # Then
    assert result == Path.cwd() / "nested/deep/leaf.txt"


@pytest.mark.parametrize(
    ("input_path", "expected_suffix"),
    [
        ("subdir", "subdir"),
        ("file.txt", "file.txt"),
        ("nested/deep/leaf.txt", "nested/deep/leaf.txt"),
    ],
)
def test_check_and_resolve_path_with_various_valid_paths_returns_correct_path(
    input_path: str,
    expected_suffix: str,
) -> None:
    # Given
    path = Path(input_path)

    # When
    result = check_and_resolve_path(path)

    # Then
    assert str(result).replace("\\", "/").endswith(expected_suffix)


def test_check_and_resolve_path_with_nonexistent_parent_directory_raises_value_error() -> None:
    # Given
    path = Path("nonexistent_dir/file.txt")

    # When / Then
    with pytest.raises(ValueError, match="path must exist"):
        check_and_resolve_path(path, must_exist=True)


@pytest.mark.skipif(sys.platform != "win32", reason="Different-drive paths are only meaningful on Windows")
def test_check_and_resolve_path_with_path_on_different_drive_raises_value_error(fs: FakeFilesystem) -> None:
    # Given
    fs.create_dir("D:/sibling")
    path = Path("D:/sibling")

    # When / Then
    with pytest.raises(ValueError, match="path must resolve to a child of the current working directory"):
        check_and_resolve_path(path)
