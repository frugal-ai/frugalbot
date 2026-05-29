import asyncio
import base64
import os
import shutil
import sys
import weakref
from pathlib import Path
from typing import Annotated

import psutil
import pydantic

from frugalbot.events import MessageEvent, MessageMarkup, MessageType, bus
from frugalbot.tools.base import ToolBase, ToolConfig, ToolError
from frugalbot.utils.process import read_stdout_and_stream_output_as_events


class PowershellResult(pydantic.BaseModel):
    returncode: int
    output: str


# Store a lock per event loop to prevent "attached to a different loop" errors during testing
_powershell_locks = weakref.WeakKeyDictionary()


def _get_powershell_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    if loop not in _powershell_locks:
        _powershell_locks[loop] = asyncio.Lock()
    return _powershell_locks[loop]


async def _run_powershell(commands: str, timeout_in_seconds: float) -> PowershellResult:
    lock = _get_powershell_lock()
    async with lock:
        wrapper_script = f"""
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $ErrorActionPreference = 'Stop'
        try {{
            $ProgressPreference = 'SilentlyContinue';
            {commands}
            if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null) {{ exit $LASTEXITCODE }}
            if (-not $?) {{ exit 1 }}
        }} catch {{
            [Console]::Error.WriteLine($_.ToString())
            exit 1
        }}
        """

        child_env = os.environ.copy()
        child_env.pop("VIRTUAL_ENV", None)

        proc = await asyncio.create_subprocess_exec(
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-WorkingDirectory",
            str(Path.cwd()),
            "-EncodedCommand",
            base64.b64encode(wrapper_script.encode("utf-16-le")).decode("utf-8"),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=child_env,
        )

        try:
            await bus.emit_and_handle(MessageEvent(f"```powershell\n{commands}\n```\n```\n", MessageType.TOOL_OUTPUT, MessageMarkup.MARKDOWN, is_stream=True))
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
                await bus.emit_and_handle(MessageEvent(f"Powershell command timed out and unable to kill process: {e}", MessageType.ERROR))
            await proc.wait()
            raise ToolError(f"PowerShell command timed out after {timeout_in_seconds} seconds.") from None

        return PowershellResult(returncode=proc.returncode if proc.returncode is not None else 1, output=captured_output.replace("\r\n", "\n"))


class Powershell(ToolBase[PowershellResult]):
    def __init__(self, config: ToolConfig):
        super().__init__(config)
        config.enabled = sys.platform == "win32"

    @property
    def description(self) -> str:
        desc = "Run a Powershell command and returns its output."
        return desc

    def get_guidelines(self) -> list[str]:
        guidelines: list[str] = ["To read a file use `Get-Content`.", "You can use here-strings to declare blocks of text. They're declared just like regular strings except they have an @ on each end."]
        if shutil.which("rg"):
            guidelines.append("Use this tool to execute 'rg' to search the contents of files.")
        else:
            guidelines.append("Use this tool to execute 'Select-String' to search the contents of files.")
        if shutil.which("npx"):
            guidelines.append("If you need API documentation, use this tool to execute 'npx ctx7 library <library_name>' to identify the library then 'npx ctx7 docs <library_id> \"<question>\"'")
        guidelines.extend([
            "Use powershell commands only (eg. use 'Invoke-WebRequest' not 'curl' or 'wget').",
            "Ensure correct command separators: Use ; when chaining commands.",
            "Never use 'Write-Host'. Use 'Write-Output' instead.",
        ])
        return guidelines

    async def run(
        self,
        command: Annotated[str, "The PowerShell command(s) to execute."],
        timeout_in_seconds: Annotated[float, "Maximum time in seconds to allow for command execution."] = 45,
    ) -> PowershellResult:
        try:
            return await _run_powershell(command, timeout_in_seconds)
        except FileNotFoundError:
            raise ToolError("powershell.exe not found.") from None
        except Exception as e:
            raise ToolError(f"An execution error occurred: {e!s}") from e
