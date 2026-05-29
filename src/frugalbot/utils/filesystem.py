from datetime import timedelta
from pathlib import Path

import cachier
import ignore

from frugalbot.utils.path import check_and_resolve_path


def list_files(
    paths: list[Path],
    respect_ignore: bool = False,
    respect_gitignore: bool = False,
    respect_parent_gitignore: bool = False,
    respect_git_global: bool = False,
    respect_git_exclude: bool = False,
    exclude_hidden: bool = False,
    include_directories: bool = False,
    validate_path: bool = True,
) -> list[Path]:
    """
    Efficiently list files recursively using the high-performance 'ignore' module.
    """
    has_git_folder = [(path / ".git").exists() for path in paths]
    files = []
    for has_git, path in zip(has_git_folder, paths, strict=True):
        builder = ignore.WalkBuilder(check_and_resolve_path(path, return_absolute=True) if validate_path else path.absolute())
        builder.ignore(respect_ignore)
        builder.git_ignore(respect_gitignore)
        builder.parents(respect_parent_gitignore)
        builder.git_global(respect_git_global)
        builder.git_exclude(respect_git_exclude)
        builder.hidden(exclude_hidden)
        builder.require_git(has_git)
        files.extend([
            entry.path().relative_to(Path.cwd()) if entry.path().is_relative_to(Path.cwd()) else entry.path()
            for entry in builder.build()
            if entry.path().is_file() or (include_directories and entry.path().is_dir())
        ])
    return files


@cachier.cachier(stale_after=timedelta(seconds=5), next_time=True, backend="memory")
def list_files_with_cache(paths: Path | list[Path]) -> list[Path]:
    return list_files([paths] if isinstance(paths, Path) else paths)
