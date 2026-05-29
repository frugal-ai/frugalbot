from pathlib import Path

import aiofiles
import orjson as json

HISTORY_FILE_PATH = Path(".frugalbot/history.json")


async def read_history() -> list[str]:
    history = None
    if HISTORY_FILE_PATH.exists():
        async with aiofiles.open(HISTORY_FILE_PATH, "rb") as f:
            contents = await f.read()
        history = json.loads(contents)
    if history and "user_prompts" in history:
        return history["user_prompts"]
    return []


async def write_history(history: list[str]) -> None:
    # Dedupe keeping last occurrence, take last 500, restore order
    unique_history_reversed = list(dict.fromkeys(reversed(history)))
    unique_history = list(reversed(unique_history_reversed[:500]))
    history_dict = {"user_prompts": unique_history}
    HISTORY_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(HISTORY_FILE_PATH, "wb") as f:
        await f.write(json.dumps(history_dict, option=json.OPT_INDENT_2))
