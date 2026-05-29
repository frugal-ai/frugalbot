from pathlib import Path


def check_and_resolve_path(path: Path | str, must_exist: bool = True, must_not_exist: bool = False, dir_okay: bool = True, file_okay: bool = True, return_absolute: bool = False) -> Path:
    if must_exist and must_not_exist:
        raise ValueError("invalid parameters")
    if isinstance(path, str):
        path = Path(path)
    if not path.is_absolute():
        complete_path = Path.cwd() / path
    else:
        complete_path = path
    if not complete_path.resolve().is_relative_to(Path.cwd().resolve()):
        raise ValueError("path must resolve to a child of the current working directory")
    if must_exist and not complete_path.exists():
        raise ValueError("path must exist")
    if must_not_exist and complete_path.exists():
        raise ValueError("path already exists")
    if not dir_okay and complete_path.is_dir():
        raise ValueError("path is a directory")
    if not file_okay and complete_path.is_file():
        raise ValueError("path is a file")
    return complete_path.absolute() if return_absolute else complete_path
