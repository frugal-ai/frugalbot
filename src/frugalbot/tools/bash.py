import asyncio
import os
import shutil
import sys
from pathlib import Path
from typing import Annotated

import psutil
import pydantic

from frugalbot.events import MessageEvent, MessageMarkup, MessageType, bus
from frugalbot.tools.base import ToolBase, ToolConfig, ToolError
from frugalbot.utils.process import read_stdout_and_stream_output_as_events


class BashResult(pydantic.BaseModel):
    returncode: int
    output: str


async def _run_bash(commands: str, timeout_in_seconds: int) -> BashResult:
    # Use a wrapper to ensure we can capture errors if desired,
    # although bash's set -e will make it exit on first error.
    wrapper_script = f"""
    set -e
    {commands}
    """

    child_env = os.environ.copy()
    child_env.pop("VIRTUAL_ENV", None)

    proc = await asyncio.create_subprocess_exec(
        "bash",
        "-c",
        wrapper_script,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=child_env,
        cwd=str(Path.cwd()),
    )

    try:
        await bus.emit_and_handle(MessageEvent(f"```bash\n{commands}\n```\n```\n", MessageType.TOOL_OUTPUT, MessageMarkup.MARKDOWN, is_stream=True))
        _, captured_output = await asyncio.wait_for(asyncio.gather(proc.wait(), read_stdout_and_stream_output_as_events(proc)), timeout=timeout_in_seconds)
        await bus.emit_and_handle(MessageEvent("\n```\n", MessageType.TOOL_OUTPUT, MessageMarkup.MARKDOWN, is_stream=True))
    except TimeoutError:
        try:
            parent = psutil.Process(proc.pid)
            for child in parent.children(recursive=True):
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            try:
                parent.kill()
            except psutil.NoSuchProcess:
                pass
        except Exception as e:
            await bus.emit_and_handle(MessageEvent(f"Bash command timed out and unable to kill process: {e}", MessageType.ERROR))
        await proc.wait()
        raise ToolError(f"Bash command timed out after {timeout_in_seconds} seconds.") from None

    return BashResult(returncode=proc.returncode if proc.returncode is not None else 1, output=captured_output)


class Bash(ToolBase[BashResult]):
    """Run a bash command and return the output."""

    def __init__(self, config: ToolConfig):
        super().__init__(config)
        config.enabled = sys.platform != "win32"

    def get_guidelines(self) -> list[str]:
        guidelines = [
            "Use this tool to execute commands. Only use this tool if another more specific tool doesn't provide the functionality you're looking for.",
            "Ensure correct command separators: Use ; or && when chaining commands.",
        ]
        if shutil.which("rg"):
            guidelines.insert(0, "Use this tool to execute 'rg' to search the contents of files.")
        else:
            guidelines.insert(0, "Use this tool to execute 'grep' to search the contents of files.")
        return guidelines

    async def run(
        self,
        command: Annotated[str, "The bash command(s) to execute."],
        timeout_in_seconds: Annotated[int, "Maximum time in seconds to allow for command execution."] = 20,
    ) -> BashResult:
        try:
            return await _run_bash(command, timeout_in_seconds)
        except FileNotFoundError:
            raise ToolError("bash not found.") from None
        except Exception as e:
            raise ToolError(f"An execution error occurred: {e!s}") from e
