from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from frugalbot.config import AgentConfig, GeneralConfig, PromptsConfig
from frugalbot.hooks.base import Hooks
from frugalbot.skills import Skill, Skills
from frugalbot.tools.base import ToolBase, Tools
from frugalbot.utils.prompts import render_system_prompt, render_user_prompt


@pytest.fixture
def mock_general_config() -> GeneralConfig:
    return GeneralConfig(
        agents=["coder"],
        tool_output_format="yaml",
    )


@pytest.fixture
def mock_agent_config() -> AgentConfig:
    return AgentConfig(
        prompts=PromptsConfig(
            system_prompt="System: {{ tools }}",
            user_prompt="User: {{ user_message }}",
        ),
    )


@pytest.fixture
def mock_skills() -> Skills:
    return Skills([Skill(name="TestSkill", description="Test Description", location="test/SKILL.md", content="content")])


@pytest.fixture
def mock_hooks() -> MagicMock:
    hooks = MagicMock(spec=Hooks)
    hooks.run = AsyncMock()
    return hooks


@pytest.fixture
def mock_tool() -> MagicMock:
    tool = MagicMock(spec=ToolBase)
    tool.name = "read"
    tool.description = "Reads a file"
    tool.get_guidelines.return_value = ["Guideline 1"]
    return tool


@pytest.fixture
def mock_tools(mock_tool: MagicMock) -> MagicMock:
    tools = MagicMock(spec=Tools)
    tools.get_all.return_value = [mock_tool]
    return tools


@pytest.fixture
def mock_platform_info(mocker) -> MagicMock:
    return mocker.patch("frugalbot.utils.prompts.get_platform_info", return_value="Windows 11 x64")


@pytest.fixture
def mock_cwd(mocker) -> MagicMock:
    return mocker.patch("frugalbot.utils.prompts.Path.cwd", return_value=Path("/mock/cwd"))


@pytest.fixture
def mock_is_file(mocker) -> MagicMock:
    return mocker.patch("frugalbot.utils.prompts.Path.is_file", return_value=True)


@pytest.fixture
def mock_read_result() -> MagicMock:
    result = MagicMock()
    result.model_dump_json.return_value = '{"path": "test.txt", "number_of_lines_in_file": 1, "line_start": 1, "contents": "file content"}'
    return result


@pytest.fixture
def mock_read_instance(mock_read_result: MagicMock) -> AsyncMock:
    instance = AsyncMock()
    instance.run.return_value = mock_read_result
    return instance


@pytest.fixture
def mock_read_class(mocker, mock_read_instance: AsyncMock) -> MagicMock:
    return mocker.patch("frugalbot.utils.prompts.Read", return_value=mock_read_instance)


async def test_render_system_prompt_with_agents_md_returns_rendered_prompt(
    mocker,
    mock_general_config: GeneralConfig,
    mock_tools: MagicMock,
    mock_skills: Skills,
    mock_hooks: MagicMock,
    mock_platform_info: MagicMock,
) -> None:
    # Given
    mocker.patch("frugalbot.utils.prompts.Path.exists", return_value=True)
    mocker.patch("frugalbot.utils.prompts.Path.read_text", return_value="Agents content")
    mock_datetime = mocker.patch("frugalbot.utils.prompts.datetime")
    mock_datetime.now.return_value = datetime(2026, 5, 15)
    prompt_template = "System: {{ tools }}"

    # When
    result = await render_system_prompt(mock_general_config, mock_tools, mock_skills, mock_hooks, prompt_template)

    # Then
    assert "- read: Reads a file" in result


async def test_render_system_prompt_without_agents_md_returns_rendered_prompt(
    mocker,
    mock_general_config: GeneralConfig,
    mock_tools: MagicMock,
    mock_skills: Skills,
    mock_hooks: MagicMock,
    mock_platform_info: MagicMock,
) -> None:
    # Given
    mocker.patch("frugalbot.utils.prompts.Path.exists", return_value=False)
    prompt_template = "System: {{ tools }}"

    # When
    result = await render_system_prompt(mock_general_config, mock_tools, mock_skills, mock_hooks, prompt_template)

    # Then
    assert "- read: Reads a file" in result


async def test_render_system_prompt_with_tools_includes_guidelines(
    mocker,
    mock_general_config: GeneralConfig,
    mock_tools: MagicMock,
    mock_skills: Skills,
    mock_hooks: MagicMock,
    mock_platform_info: MagicMock,
) -> None:
    # Given
    mocker.patch("frugalbot.utils.prompts.Path.exists", return_value=False)
    prompt_template = "Guidelines: {{ tool_guidelines }}"

    # When
    result = await render_system_prompt(mock_general_config, mock_tools, mock_skills, mock_hooks, prompt_template)

    # Then
    assert "Guideline 1" in result


async def test_render_system_prompt_includes_skills(
    mocker,
    mock_general_config: GeneralConfig,
    mock_tools: MagicMock,
    mock_skills: Skills,
    mock_hooks: MagicMock,
    mock_platform_info: MagicMock,
) -> None:
    # Given
    mocker.patch("frugalbot.utils.prompts.Path.exists", return_value=False)
    prompt_template = "Skills: {{ skills }}"

    # When
    result = await render_system_prompt(mock_general_config, mock_tools, mock_skills, mock_hooks, prompt_template)

    # Then
    assert "TestSkill" in result


async def test_render_user_prompt_without_attachments_returns_rendered_prompt(
    mock_hooks: MagicMock,
    mock_agent_config: AgentConfig,
) -> None:
    # Given
    prompt = "Hello world"

    # When
    result = await render_user_prompt(mock_agent_config, mock_hooks, prompt)

    # Then
    assert result == "User: Hello world"


async def test_render_user_prompt_with_valid_attachments_appends_file_contents(
    mock_hooks: MagicMock,
    mock_cwd: MagicMock,
    mock_is_file: MagicMock,
    mock_read_class: MagicMock,
    mock_agent_config: AgentConfig,
) -> None:
    # Given
    prompt = "Read @test.txt"

    # When
    result = await render_user_prompt(mock_agent_config, mock_hooks, prompt)

    # Then
    assert "file content" in result
    assert "The result of 'read' tool calls" in result


async def test_render_user_prompt_with_invalid_attachments_ignores_them(
    mocker,
    mock_hooks: MagicMock,
    mock_cwd: MagicMock,
    mock_agent_config: AgentConfig,
) -> None:
    # Given
    prompt = "Read @missing.txt"
    mocker.patch("frugalbot.utils.prompts.Path.is_file", return_value=False)

    # When
    result = await render_user_prompt(mock_agent_config, mock_hooks, prompt)

    # Then
    assert result == "User: Read @missing.txt"


async def test_render_user_prompt_strips_punctuation_from_attachments(
    mock_hooks: MagicMock,
    mock_cwd: MagicMock,
    mock_is_file: MagicMock,
    mock_read_instance: AsyncMock,
    mock_read_class: MagicMock,
    mock_agent_config: AgentConfig,
) -> None:
    # Given
    prompt = "Check @test.txt, and @other.txt!"

    # When
    await render_user_prompt(mock_agent_config, mock_hooks, prompt)

    # Then
    assert mock_read_instance.run.call_count == 2
    calls = [call.kwargs["path"] for call in mock_read_instance.run.call_args_list]
    assert "test.txt" in calls
    assert "other.txt" in calls


async def test_render_user_prompt_handles_duplicate_attachments(
    mock_hooks: MagicMock,
    mock_cwd: MagicMock,
    mock_is_file: MagicMock,
    mock_read_instance: AsyncMock,
    mock_read_class: MagicMock,
    mock_agent_config: AgentConfig,
) -> None:
    # Given
    prompt = "Check @test.txt and @test.txt"

    # When
    await render_user_prompt(mock_agent_config, mock_hooks, prompt)

    # Then
    assert mock_read_instance.run.call_count == 1


async def test_render_user_prompt_ignores_read_tool_exceptions(
    mock_hooks: MagicMock,
    mock_cwd: MagicMock,
    mock_is_file: MagicMock,
    mock_read_instance: AsyncMock,
    mock_read_class: MagicMock,
    mock_agent_config: AgentConfig,
) -> None:
    # Given
    prompt = "Check @test.txt"
    mock_read_instance.run.side_effect = Exception("Read error")

    # When
    result = await render_user_prompt(mock_agent_config, mock_hooks, prompt)

    # Then
    assert result == "User: Check @test.txt"
