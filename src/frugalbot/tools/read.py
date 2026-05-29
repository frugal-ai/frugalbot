from typing import Annotated

import pydantic

from frugalbot.events import MessageEvent, MessageType, bus
from frugalbot.tools.base import ToolBase, ToolError
from frugalbot.tools.hashline_config import HashlineConfig
from frugalbot.utils.hashline import get_contents_with_line_hashes
from frugalbot.utils.path import check_and_resolve_path


class ReadResult(pydantic.BaseModel):
    path: str
    number_of_lines_in_file: int
    line_start: int
    contents: str


class Read(ToolBase[ReadResult, HashlineConfig]):
    @property
    def description(self) -> str:
        if self.config.hashline:
            desc = (
                "Read the contents of a file and return it. Each line is prefixed with `HASH|` where HASH is a 6-character hex string "
                "(e.g., `1ca3b9|this is the line contents`). Also returns the path of the file, the total number of lines in the file and the "
                "start line number (1-indexed) of the returned contents."
            )
        else:
            desc = "Read the contents of a file and return it."
        return desc

    def get_guidelines(self) -> list[str]:
        return [
            "Use this tool to read part of a file or an entire file.",
            "The first time you read a file, read its entire contents by setting the limit parameter to -1.",
            "The tool returns a max of 1000 lines by default, but you can adjust this with the 'limit' parameter if you want to read more or fewer lines.",
        ]

    async def run(
        self,
        path: Annotated[str, "The path to the file to read."],
        line_start: Annotated[int, "The line number to start reading from (1-indexed)"] = 1,
        limit: Annotated[int, "Maximum number of lines to read. Set to -1 for unlimited."] = 1000,
    ) -> ReadResult:
        if line_start <= 0:
            raise ToolError("Line number must be a positive integer (the first line is line number 1)")
        if limit <= 0 and limit != -1:
            raise ToolError("The maximum number of lines to read must be a positive integer or -1")
        try:
            full_path = check_and_resolve_path(path, dir_okay=False)
            contents = full_path.read_text(encoding="utf-8")
            lines = contents.splitlines()
            number_of_lines = len(lines)
            if self.config.hashline:
                lines = get_contents_with_line_hashes(full_path)
            end_index = line_start - 1 + limit if limit > 0 else None
            lines = lines[line_start - 1 : end_index]
            read_result = ReadResult(contents="\n".join(lines), line_start=line_start, number_of_lines_in_file=number_of_lines, path=path)
        except Exception as e:
            raise ToolError(f"Unable to read {path}: {e!s}") from e
        await bus.emit_and_handle(MessageEvent(f"Read {path} from line {line_start}, max {limit if limit > 0 else 'unlimited'} lines ({number_of_lines} total lines in file)", MessageType.TOOL_OUTPUT))
        return read_result
