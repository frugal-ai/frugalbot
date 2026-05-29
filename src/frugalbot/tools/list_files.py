from pathlib import Path
from typing import Annotated

import pathspec
import pydantic

from frugalbot.events import MessageEvent, MessageType, bus
from frugalbot.tools.base import ToolBase, ToolError
from frugalbot.utils.filesystem import list_files


def _path_to_string(p: Path):
    path_as_posix = p.as_posix()
    return f"{path_as_posix}/" if p.is_dir() and not path_as_posix.endswith("/") else path_as_posix


class ListFilesResult(pydantic.BaseModel):
    files: list[str]


class ListFiles(ToolBase[ListFilesResult]):
    """List files in a directory"""

    def get_guidelines(self) -> list[str]:
        return [
            "Always use this tool (as opposed to shell commands) to discover the file structure of the project.",
            "By default, it respects .gitignore to avoid listing unnecessary files like .venv or build artifacts.",
            "By default, the listing is non-recursive. Set recursive to true to receive a recursive file listing.",
        ]

    async def run(
        self,
        path: Annotated[str, "The directory to list files from. Defaults to the current working directory. Must be a relative path."] = ".",
        respect_gitignore: Annotated[bool, "Whether to respect .gitignore when listing files."] = True,
        limit: Annotated[int, "The maximum number of files to return."] = 500,
        recursive: Annotated[bool, "Whether to list files in subdirectories."] = False,
    ) -> ListFilesResult:
        try:
            path_obj = Path(path)
            if not path_obj.exists():
                raise ToolError("path must exist")
            if not path_obj.is_dir():
                raise ToolError("path must be a directory")

            if recursive:
                all_paths = [p for p in list_files([path_obj], respect_gitignore=respect_gitignore, include_directories=True)]
            else:
                spec = None
                if respect_gitignore:
                    gitignore_path = Path.cwd() / ".gitignore"
                    if gitignore_path.exists():
                        lines = gitignore_path.read_text().splitlines()
                        lines.append(".git/")
                        spec = pathspec.PathSpec.from_lines("gitignore", lines)
                all_paths = [p for p in path_obj.glob("*") if (p.is_file() or p.is_dir()) and (spec is None or not spec.match_file(_path_to_string(p)))]
            formatted_paths = [_path_to_string(p) for p in all_paths if p.as_posix() != "."]
            if recursive:
                # filter out .git folder since list_files doesn't exclude it
                formatted_paths = [p for p in formatted_paths if ".git/" not in p]
            sorted_paths = sorted(formatted_paths)[:limit]
            await bus.emit_and_handle(
                MessageEvent(f"Listed {len(sorted_paths)} files {'recursively ' if recursive else ''}at {path}{' including .gitignored files' if not respect_gitignore else ''}", MessageType.TOOL_OUTPUT)
            )
            return ListFilesResult(files=sorted_paths)
        except Exception as e:
            if isinstance(e, ToolError):
                raise e
            raise ToolError(f"Unable to list files: {e!s}") from e
