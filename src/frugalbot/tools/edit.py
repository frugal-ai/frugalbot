import difflib
from typing import Any

import pydantic
from pydantic import BaseModel, Field

from frugalbot.events import MessageEvent, MessageType, bus
from frugalbot.tools.base import ToolBase, ToolError
from frugalbot.tools.hashline_config import HashlineConfig
from frugalbot.utils.hashline import SingleHashlineEditParams, apply_hashline_edits
from frugalbot.utils.json import json_to_readable_yaml
from frugalbot.utils.path import check_and_resolve_path
from frugalbot.utils.pydantic import get_clean_tool_parameters_schema


class EditResult(pydantic.BaseModel):
    path: str
    diff: str


class HashlineEditParams(BaseModel):
    path: str = Field(..., description="The path of the file to edit")
    edits: list[SingleHashlineEditParams]


class ClassicEditParams(BaseModel):
    path: str = Field(..., description="The path of the file to edit")
    old_content: str = Field(..., description="The content to replace. Must appear only once in the file unless replace_all=true.")
    new_content: str = Field(..., description="The new content that will replace the old content. Can be an empty string but cannot be null.")
    replace_all: bool = Field(default=False, description="If false, only perform the replace operation if old_content is unique. If true, all occurrences of old_content will be replaced with new_content")


class Edit(ToolBase[EditResult, HashlineConfig]):
    @property
    def description(self) -> str:
        if self.config.hashline:
            desc = "Edit the contents of a file. Must specify the hexadecimal hash of the line(s) to edit."
        else:
            desc = "Edit the contents of a file. Returns a diff of the file before the edit vs after the edit."
        return desc

    def get_guidelines(self) -> list[str]:
        guidelines = [
            "If a file already exists, and you're changing less than half of the content, always use this tool to edit it.",
            "If a file already exists, and you're changing more than half of the content, use the `write`, `powershell` or `bash` tool depending on what's available.",
        ]
        if self.config.hashline:
            guidelines.extend([
                "Always provide all modifications to the edit tool within the edits array, even when performing only a single change.",
                "If the file is empty, use the read tool first to get the correct hash for the first line before attempting to edit.",
                "When replacing a single line, omit end_hash.",
                "Example of editing foo.txt to remove all lines from line 12a7c4 to line 15b2c3 (inclusive): edits=[path='foo.txt', start_hash='12a7c4', new_content='', end_hash='15b2c3']",
                "Example of editing foo.txt to replace a single line: edits=[path='foo.txt', start_hash='15b2c3', new_content='new text']",
                "Example of editing foo.txt to replace lines 15b2c3 to 17e2f3 (inclusive) with 2 lines: "
                "edits=[path='foo.txt', start_hash='15b2c3', end_hash='17e2f3', new_content='New content 1\\nNew content 2']",
                "Example of editing foo.txt to insert new lines after line 15b2c3: edits=[path='foo.txt', start_hash='15b2c3', new_content='New content 1\\nNew content 2', insert_after=True]",
            ])
        return guidelines

    def get_schema(self) -> dict[str, Any]:
        if self.config.hashline:
            return {
                "type": "function",
                "function": {"name": "edit", "description": "Applies edits to a file using line hashes", "parameters": get_clean_tool_parameters_schema(HashlineEditParams)},
            }
        return {
            "type": "function",
            "function": {"name": "edit", "description": "Applies edits to a file", "parameters": get_clean_tool_parameters_schema(ClassicEditParams)},
        }

    def _hashline_run(self, **kwargs) -> tuple[EditResult, str]:
        params = HashlineEditParams.model_validate(kwargs)
        try:
            full_path = check_and_resolve_path(params.path, dir_okay=False)
            old_content = full_path.read_text(encoding="utf-8")
            apply_hashline_edits(full_path, params.edits)
            new_content = full_path.read_text(encoding="utf-8")
        except Exception as e:
            raise ToolError(f"Unable to edit {params.path}: {e!s}") from e
        edit_result = EditResult(path=params.path, diff="\n".join(difflib.unified_diff(old_content.splitlines(), new_content.splitlines(), n=1)))
        return edit_result, f"Results of edits to {params.path}:\n\n{json_to_readable_yaml(edit_result.model_dump_json())}"

    def _classic_run(self, **kwargs) -> tuple[EditResult, str]:
        params = ClassicEditParams.model_validate(kwargs)
        try:
            full_path = check_and_resolve_path(params.path, dir_okay=False, must_exist=False)
            if not full_path.exists():
                full_path.write_text("", encoding="utf-8")
            original_file_text = full_path.read_text(encoding="utf-8").replace("\r\n", "\n")
            file_text = original_file_text

            params.old_content = params.old_content.replace("\r\n", "\n")
            params.new_content = params.new_content.replace("\r\n", "\n")
            if params.old_content == params.new_content:
                raise ValueError("old_content and new_content cannot be identical")

            old_content_first_occurrence_index = file_text.find(params.old_content)
            if old_content_first_occurrence_index == -1:
                # the output of the 'read' tool in yaml is indented by 2 extra spaces and confuses some models, so fix it for them
                params.old_content = "\n".join([line.removeprefix("  ") for line in params.old_content.splitlines()])
                params.new_content = "\n".join([line.removeprefix("  ") for line in params.new_content.splitlines()])
                old_content_first_occurrence_index = file_text.find(params.old_content)
                if old_content_first_occurrence_index == -1:
                    raise ValueError(f"old_content was not found in {params.path}.")

            if not params.replace_all and old_content_first_occurrence_index != file_text.rfind(params.old_content):
                raise ValueError(f"Old content '{params.old_content}' is not unique in {params.path}")

            file_text = file_text.replace(params.old_content, params.new_content)
            diff = "\n".join(difflib.unified_diff(original_file_text.splitlines(), file_text.splitlines(), n=1))

            full_path.write_text(file_text, encoding="utf-8")

            edit_result = EditResult(path=params.path, diff=diff)
        except Exception as e:
            raise ToolError(f"Edit failure: {e!s}") from e
        return edit_result, f"Results of edit:\n\n{json_to_readable_yaml(edit_result.model_dump_json())}"

    async def run(self, **kwargs) -> EditResult:
        if self.config.hashline:
            edit_result, readable_result = self._hashline_run(**kwargs)
        else:
            edit_result, readable_result = self._classic_run(**kwargs)
        await bus.emit_and_handle(MessageEvent(readable_result, MessageType.TOOL_OUTPUT))
        return edit_result
