from typing import Annotated, Any

import pydantic
from pydantic import BaseModel, Field

from frugalbot.events import MessageEvent, MessageType, bus
from frugalbot.tools.base import ToolBase, ToolError
from frugalbot.tools.hashline_config import HashlineConfig
from frugalbot.utils.dict import normalize_alias_keys
from frugalbot.utils.path import check_and_resolve_path
from frugalbot.utils.pydantic import get_clean_tool_parameters_schema


class WriteResult(pydantic.BaseModel):
    success: bool


class WriteParams(BaseModel):
    path: str = Field(..., description="The path to the file to write.")
    contents: str = Field(..., description="The contents of the file.")

    @pydantic.model_validator(mode="before")
    @classmethod
    def _normalize_content_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            normalize_alias_keys(data, "contents", ("content",))
        return data


class Write(ToolBase[WriteResult, HashlineConfig]):
    @property
    def description(self) -> str:
        if self.config.hashline:
            desc = (
                "Writes or overwrites the contents of a file. Returns the new contents of the file. "
                "In the returned content, each line is prefixedwith `HASH|` where HASH is a 6-character hex string (e.g., `1ca3b9|this is the line contents`)."
            )
        else:
            desc = "Write or overwrite the contents of a file. Returns the new contents of the file."
        return desc

    def get_guidelines(self) -> list[str]:
        return [
            "Use this tool to create a new file.",
            "Use this tool to overwrite the existing content of a file when you need to replace more than half its content. Otherwise, always use the 'edit' tool.",
        ]

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": get_clean_tool_parameters_schema(WriteParams),
            },
        }

    def normalize_args(self, args: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(args)
        normalize_alias_keys(normalized, "contents", ("content",))
        return normalized

    async def run(
        self,
        path: Annotated[str, "The path to the file to write."],
        contents: Annotated[str, "The contents of the file."] = "",
        content: str | None = None,
        **kwargs: Any,
    ) -> WriteResult:
        file_contents = contents if contents else (content if content is not None else "")
        full_path = check_and_resolve_path(path, must_exist=False)

        try:
            if not full_path.parent.exists():
                full_path.parent.mkdir(parents=True)
            full_path.write_text(file_contents, encoding="utf-8")
        except Exception as e:
            raise ToolError(f"Unable to write {path}: {e!s}") from e
        await bus.emit_and_handle(MessageEvent(f"Wrote new file at {path}", MessageType.TOOL_OUTPUT))
        return WriteResult(success=True)
