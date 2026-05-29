import asyncio
import codecs

from frugalbot.events import MessageEvent, MessageMarkup, MessageType, bus


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
