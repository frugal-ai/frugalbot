import asyncio
import re
import shutil
from pathlib import Path
from typing import Annotated

import pydantic

from frugalbot.events import MessageEvent, MessageMarkup, MessageType, bus
from frugalbot.tools.base import ToolBase, ToolConfig, ToolError
from frugalbot.utils.process import read_stdout_and_stream_output_as_events


class GrepResult(pydantic.BaseModel):
    output: str
    method: str


async def _run_grep_subprocess(command: list[str], timeout_in_seconds: int, method_name: str) -> GrepResult:
    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    try:
        _, captured_output = await asyncio.wait_for(asyncio.gather(proc.wait(), read_stdout_and_stream_output_as_events(proc)), timeout=timeout_in_seconds)
    except TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        await proc.wait()
        raise ToolError(f"Grep command ({method_name}) timed out after {timeout_in_seconds} seconds.") from None

    return GrepResult(output=captured_output.replace("\r\n", "\n"), method=method_name)


async def _run_python_grep(pattern: str, path: Path, flags: str) -> GrepResult:
    await bus.emit_and_handle(MessageEvent("Grep output (python):\n```\n", MessageType.TOOL_OUTPUT, MessageMarkup.MARKDOWN, is_stream=True))

    results = []
    regex_flags = 0
    if "-i" in flags:
        regex_flags |= re.IGNORECASE

    try:
        regex = re.compile(pattern, flags=regex_flags)
    except re.error as e:
        await bus.emit_and_handle(MessageEvent("\n```", MessageType.TOOL_OUTPUT, MessageMarkup.MARKDOWN, is_stream=True))
        raise ToolError(f"Invalid regex pattern: {e}") from e

    files_to_search = []
    if path.is_file():
        files_to_search.append(path)
    elif path.is_dir():
        for p in path.rglob("*"):
            if p.is_file():
                files_to_search.append(p)
    else:
        output = f"Path {path} not found."
        await bus.emit_and_handle(MessageEvent(output, MessageType.TOOL_OUTPUT, MessageMarkup.MARKDOWN, is_stream=True))
        await bus.emit_and_handle(MessageEvent("\n```", MessageType.TOOL_OUTPUT, MessageMarkup.MARKDOWN, is_stream=True))
        return GrepResult(output=output, method="python")

    for file_path in files_to_search:
        try:
            with file_path.open(encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    if regex.search(line):
                        res = f"{file_path}:{line_num}:{line.strip()}"
                        results.append(res)
                        await bus.emit_and_handle(MessageEvent(res + "\n", MessageType.TOOL_OUTPUT, MessageMarkup.MARKDOWN, is_stream=True))
        except Exception as e:
            res = f"Could not read {file_path}: {e}"
            results.append(res)
            await bus.emit_and_handle(MessageEvent(res + "\n", MessageType.TOOL_OUTPUT, MessageMarkup.MARKDOWN, is_stream=True))

    await bus.emit_and_handle(MessageEvent("\n```", MessageType.TOOL_OUTPUT, MessageMarkup.MARKDOWN, is_stream=True))
    return GrepResult(output="\n".join(results), method="python")


class Grep(ToolBase[GrepResult]):
    """Search for a pattern in files."""

    def get_guidelines(self) -> list[str]:
        return [
            "Use this tool to search for text patterns within files or directories.",
            "The pattern can be a regular expression.",
        ]

    def __init__(self, config: ToolConfig):
        super().__init__(config)
        config.enabled = False  # this tool is untested and might not be needed

    async def run(
        self,
        pattern: Annotated[str, "The regex pattern to search for."],
        path: Annotated[str, "The file or directory to search in."],
        flags: Annotated[str, "Optional flags (e.g., '-i' for case-insensitive). Note: flags support varies by backend."] = "",
        timeout_in_seconds: Annotated[int, "Maximum time in seconds to allow for command execution."] = 20,
    ) -> GrepResult:
        # 1. Try 'rg'
        if shutil.which("rg"):
            cmd = ["rg"]
            if flags:
                cmd.extend(flags.split())
            cmd.extend([pattern, path])
            try:
                return await _run_grep_subprocess(cmd, timeout_in_seconds, "rg")
            except Exception as e:
                if isinstance(e, ToolError):
                    raise
                pass

        # 2. Try 'grep'
        if shutil.which("grep"):
            cmd = ["grep", "-r"]
            if flags:
                cmd.extend(flags.split())
            cmd.extend([pattern, path])
            try:
                return await _run_grep_subprocess(cmd, timeout_in_seconds, "grep")
            except Exception as e:
                if isinstance(e, ToolError):
                    raise
                pass

        # 3. Fallback to Python
        try:
            return await _run_python_grep(pattern, Path(path), flags)
        except Exception as e:
            if isinstance(e, ToolError):
                raise
            raise ToolError(f"An execution error occurred during Python grep: {e!s}") from e
