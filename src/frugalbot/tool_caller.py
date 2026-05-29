import orjson as json
from any_llm.types.completion import ChatCompletionMessageFunctionToolCall
from pydantic import BaseModel

from frugalbot.config import ToolOutputFormat
from frugalbot.conversation import Conversation
from frugalbot.events import (
    MessageEvent,
    MessageMarkup,
    MessageType,
    bus,
)
from frugalbot.hooks.base import ApprovalState, Hooks, PostToolCallHook, PreToolCallHook
from frugalbot.tools.base import Tools
from frugalbot.utils.json import json_to_readable_yaml


class ToolCaller:
    def __init__(self, conversation: Conversation, hooks: Hooks, tools: Tools, tool_call: ChatCompletionMessageFunctionToolCall, tool_output_format: ToolOutputFormat):
        self.conversation = conversation
        self.hooks = hooks
        self.tools = tools
        self.tool_call = tool_call
        self.tool_output_format = tool_output_format
        self.raw_args_str = tool_call.function.arguments

    async def _report_tool_error(self, e: Exception):
        exception_string = f"{type(e).__name__}: {e!s}"
        await self.conversation.append_tool_message(
            content=exception_string,
            content_format="text",
            tool_call_id=self.tool_call.id,
            extra_content=getattr(self.tool_call, "extra_content", None),
            name=self.tool_call.function.name,
        )
        await bus.emit_and_handle(MessageEvent(exception_string, MessageType.TOOL_OUTPUT, MessageMarkup.NONE))

    async def call(self):
        try:
            args_dict = json.loads(self.raw_args_str)
            self.tools.get(self.tool_call.function.name).validate_args(args_dict)

            pre_tc_hook_data = PreToolCallHook(tool_name=self.tool_call.function.name, arguments=args_dict)
            await self.hooks.run(pre_tc_hook_data)

            if pre_tc_hook_data.state in (ApprovalState.DENIED, ApprovalState.NOT_SET):
                if pre_tc_hook_data.denied_reason:
                    denied_message = f"The user refused to execute the tool call for the following reason: {pre_tc_hook_data.denied_reason}"
                elif pre_tc_hook_data.state == ApprovalState.NOT_SET:
                    denied_message = "The user didn't explicitly approve or deny the tool call. The tool call wasn't executed as a safety measure."
                else:
                    denied_message = "The user refused to execute the tool call without providing a reason"
                await self.conversation.append_tool_message(
                    content=denied_message,
                    content_format="text",
                    tool_call_id=self.tool_call.id,
                    extra_content=getattr(self.tool_call, "extra_content", None),
                    name=self.tool_call.function.name,
                )
                await bus.emit_and_handle(MessageEvent(denied_message, MessageType.TOOL_OUTPUT, MessageMarkup.NONE))
                return

            if pre_tc_hook_data.state == ApprovalState.APPROVED:
                result: BaseModel = await self.tools.get(pre_tc_hook_data.tool_name).run(**pre_tc_hook_data.arguments)
                result_json = result.model_dump_json()
                post_tc_hook_data = PostToolCallHook(self.tool_call.function.name, result_json)
                await self.hooks.run(post_tc_hook_data)
                await self.conversation.append_tool_message(
                    content=json_to_readable_yaml(post_tc_hook_data.result_json) if self.tool_output_format == "yaml" else post_tc_hook_data.result_json,
                    content_format="yaml" if self.tool_output_format == "yaml" else "json",
                    tool_call_id=self.tool_call.id,
                    extra_content=getattr(self.tool_call, "extra_content", None),
                    name=post_tc_hook_data.tool_name,
                )
                return

            raise ValueError("The tool call is in an unsupported state")

        except Exception as e:
            await self._report_tool_error(e)
