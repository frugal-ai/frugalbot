from frugalbot.hooks.base import AgentStopHook, HookBase, HookConfig
from frugalbot.utils.prompts import USER_PROMPT_SUFFIX_FOR_ATTACHMENTS

_VERIFICATION_MESSAGE_PREFIX = "Are you sure you have completed all requested work? As a reminder, this is what the user requested:\n\n---\n"


class ValidateFinished(HookBase[AgentStopHook, HookConfig]):
    async def run(self, hook_data) -> None:
        for message in reversed(hook_data.conversation.messages):
            if not isinstance(message, dict):
                assistant_msg_content = message.content
                if not assistant_msg_content:
                    continue
                assistant_msg_content = assistant_msg_content.strip().upper()
                if assistant_msg_content == "YES" or (len(assistant_msg_content) == 5 and assistant_msg_content[1:4] == "YES"):
                    break
                continue

            if "role" not in message or "content" not in message or message["role"] != "user":
                continue

            user_msg_content: str = message["content"]

            if user_msg_content.startswith(_VERIFICATION_MESSAGE_PREFIX):
                continue

            attachments_suffix_index = user_msg_content.find(USER_PROMPT_SUFFIX_FOR_ATTACHMENTS)
            if attachments_suffix_index >= 0:
                user_msg_content = user_msg_content[:attachments_suffix_index]

            hook_data.continue_conversation = True
            await hook_data.conversation.append_user_message(f"{_VERIFICATION_MESSAGE_PREFIX}{user_msg_content}\n---\n\nIf you have completed all requested work, reply with 'YES' and nothing else.")
            break
