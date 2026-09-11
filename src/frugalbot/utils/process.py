import asyncio
import codecs
import os

from frugalbot.events import MessageEvent, MessageMarkup, MessageType, bus


def build_child_process_env() -> dict[str, str]:
    """Build the environment used when spawning shell subprocesses.

    Removes VIRTUAL_ENV so that spawned tooling (e.g. uv) behaves consistently,
    and defines CI-friendly variables that disable interactive prompts and
    colored output for the commands we run.
    """
    child_env = os.environ.copy()
    child_env.pop("VIRTUAL_ENV", None)
    child_env["CI"] = "true"
    child_env["NO_COLOR"] = "1"
    child_env["TERM"] = "dumb"
    return child_env


async def read_stdout_and_stream_output_as_events(proc: asyncio.subprocess.Process) -> str:
    if not proc.stdout:
        return ""
    stream = proc.stdout
    buffer = bytearray()
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    while True:
        try:
            # Read up to 1024 bytes, but wait no longer than 'timeout'
            chunk = await asyncio.wait_for(stream.read(1024), timeout=0.5)
            if not chunk:  # EOF
                break
            buffer.extend(chunk)
            text = decoder.decode(chunk, final=False)
            await bus.emit_and_handle(MessageEvent(text, MessageType.TOOL_OUTPUT, MessageMarkup.MARKDOWN, is_stream=True))
        except TimeoutError:
            pass
    return buffer.decode(errors="replace")
