import re
from datetime import datetime
from pathlib import Path

from jinja2 import Template
from pydantic import BaseModel

from frugalbot.config import AgentConfig, GeneralConfig
from frugalbot.hooks.base import Hooks, PreRenderSystemPromptHook, PreRenderUserPromptHook
from frugalbot.skills import Skills
from frugalbot.tools.base import Tools
from frugalbot.tools.hashline_config import HashlineConfig
from frugalbot.tools.read import Read
from frugalbot.utils.json import json_to_readable_yaml
from frugalbot.utils.platform import get_platform_info

_CLAUDE_MD_PATH = Path("CLAUDE.md")
_AGENTS_MD_PATH = Path("AGENTS.md")

USER_PROMPT_SUFFIX_FOR_ATTACHMENTS = "\n\nThe result of 'read' tool calls for the mentioned files is included below. No need to read them again to start the task.\n\n"


async def render_system_prompt(general_config: GeneralConfig, tools: Tools, skills: Skills, hooks: Hooks, prompt_template: str) -> str:
    tools_block = ""
    guidelines = ""
    for tool in tools.get_all():
        tools_block += f"- {tool.name}: {tool.description}\n"
        tool_guidelines_list = tool.get_guidelines()
        if tool_guidelines_list:
            guidelines += f"## '{tool.name}' Tool Guidelines:\n"
            guidelines += "\n".join(f"- {guideline}" for guideline in tool_guidelines_list)
            guidelines += "\n\n"
    if _CLAUDE_MD_PATH.exists():
        agents_md = _CLAUDE_MD_PATH.read_text(encoding="utf-8")
    elif _AGENTS_MD_PATH.exists():
        agents_md = _AGENTS_MD_PATH.read_text(encoding="utf-8")
    else:
        agents_md = ""
    hook_data = PreRenderSystemPromptHook(
        prompt_template=prompt_template,
        prompt_arguments=dict(
            tools=tools_block,
            tool_guidelines=guidelines,
            agents_md=agents_md,
            skills=skills.catalog(),
            current_date=datetime.now().strftime("%B %d, %Y"),
            platform_info=get_platform_info(),
            tool_output_format=general_config.tool_output_format,
        ),
    )
    await hooks.run(hook_data)
    return Template(hook_data.prompt_template).render(hook_data.prompt_arguments)


async def render_user_prompt(config: AgentConfig, hooks: Hooks, prompt: str) -> str:
    hook_data = PreRenderUserPromptHook(prompt_template=config.prompts.user_prompt, prompt_arguments=dict(user_message=prompt))
    await hooks.run(hook_data)
    prompt_rendered = Template(hook_data.prompt_template).render(hook_data.prompt_arguments)

    pattern = r"@(\S+?)(?=[.,!?;:]*(?:\s|$))"
    matches = re.findall(pattern, prompt_rendered)
    attachments = []
    unique_matches = sorted(set(matches))

    for file_path_str in unique_matches:
        clean_path_str = file_path_str.rstrip(".,!?;:")
        path = Path.cwd() / clean_path_str

        if path.is_file():
            read_tool = Read(HashlineConfig(hashline=False))
            try:
                result: BaseModel = await read_tool.run(**{"path": clean_path_str, "limit": -1})
                attachments.append(json_to_readable_yaml(result.model_dump_json()))
            except Exception:
                pass

    if not attachments:
        return prompt_rendered

    return prompt_rendered + USER_PROMPT_SUFFIX_FOR_ATTACHMENTS + "\n\n".join(attachments)
