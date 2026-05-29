from pathlib import Path
from typing import Any

import aiofiles
import orjson as json

from frugalbot.events import QuestionResponse, QuestionType, UserChoiceInteractionEvent, UserCompositeInteractionEvent, bus
from frugalbot.hooks.base import ApprovalState, HookBase, HookConfig, HookPriority, PreToolCallHook
from frugalbot.utils.json import json_to_readable_yaml

_APPROVED_TOOLS_JSON_PATH = Path.home() / ".frugalbot/approved_tools.json"


class ManualApprovalConfig(HookConfig):
    approved_tool_calls_path: Path = _APPROVED_TOOLS_JSON_PATH


class ManualApprovalHook(HookBase[PreToolCallHook, ManualApprovalConfig]):
    def __init__(self, config: ManualApprovalConfig) -> None:
        self.lazy_init_completed = False
        super().__init__(config)

    async def _load_pre_approved_tools(self):
        self.pre_approved_tool_calls: dict[str, list[dict[str, Any]]] = {}
        if self.config.approved_tool_calls_path.exists():
            async with aiofiles.open(self.config.approved_tool_calls_path) as f:
                self.pre_approved_tool_calls = json.loads(await f.read())

    def _is_pre_approved(self, tool_name: str, args: dict[str, Any]) -> bool:
        if tool_name in self.pre_approved_tool_calls:
            return any(entry == args for entry in self.pre_approved_tool_calls[tool_name])
        return False

    async def _save_to_pre_approved_tools(self, tool_name: str, args: dict[str, Any]):
        approved_args = self.pre_approved_tool_calls.setdefault(tool_name, [])
        if args not in approved_args:
            approved_args.append(args)
            async with aiofiles.open(self.config.approved_tool_calls_path, "wb") as f:
                await f.write(json.dumps(self.pre_approved_tool_calls, option=json.OPT_INDENT_2))

    async def _do_manual_approval(self, hook_data: PreToolCallHook):
        choice_event = UserChoiceInteractionEvent(
            f"LLM wants to call tool '{hook_data.tool_name}' with arguments:\n```yaml\n{json_to_readable_yaml(hook_data.arguments)}\n```\n\nDo you want to execute this tool call?",
            QuestionType.YES_NO_ALWAYS,
        )
        await bus.emit_and_handle(choice_event)
        if choice_event.future.result() in (QuestionResponse.YES, QuestionResponse.ALWAYS):
            hook_data.state = ApprovalState.APPROVED

        if choice_event.future.result() == QuestionResponse.ALWAYS:
            await self._save_to_pre_approved_tools(hook_data.tool_name, hook_data.arguments)

        if hook_data.state != ApprovalState.APPROVED:
            hook_data.state = ApprovalState.DENIED
            composite_event = UserCompositeInteractionEvent(
                "Do you want to provide feedback to the LLM about why you refused to execute the tool call?",
                QuestionType.YES_NO,
                "Enter your feedback for the LLM:",
            )
            await bus.emit_and_handle(composite_event)
            response, feedback = composite_event.future.result()
            if response == QuestionResponse.YES and feedback:
                hook_data.denied_reason = feedback

    @property
    def priority(self) -> HookPriority:
        return HookPriority.LOW

    async def run(self, hook_data: PreToolCallHook) -> None:
        if not self.lazy_init_completed:
            await self._load_pre_approved_tools()
            self.lazy_init_completed = True

        if hook_data.state in (ApprovalState.APPROVED, ApprovalState.DENIED):
            return

        if self._is_pre_approved(hook_data.tool_name, hook_data.arguments):
            hook_data.state = ApprovalState.APPROVED
        else:
            await self._do_manual_approval(hook_data)
