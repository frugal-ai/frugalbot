import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from frugalbot.skills import Skill, Skills, discover_skills

# =============================================================================
# Skill Tests
# =============================================================================


def test_to_catalog_format_with_valid_skill_returns_formatted_string() -> None:
    # Given
    skill = Skill(name="test-skill", description="test desc", location="path/to/skill", content="content")

    # When
    result = skill.to_catalog_format()

    # Then
    assert result == "test-skill @ path/to/skill: test desc"


def test_to_catalog_format_with_optional_fields_omits_optional_fields() -> None:
    # Given
    skill = Skill(
        name="full-skill",
        description="full desc",
        location="loc",
        content="c",
        license="MIT",
        compatibility="v1",
        metadata={"key": "value"},
        allowed_tools="bash,edit",
    )

    # When
    result = skill.to_catalog_format()

    # Then
    assert result == "full-skill @ loc: full desc"


# =============================================================================
# Skills Tests
# =============================================================================


def test_catalog_with_skills_returns_formatted_catalog() -> None:
    # Given
    skills = Skills([
        Skill(name="s1", description="d1", location="l1", content="c1"),
        Skill(name="s2", description="d2", location="l2", content="c2"),
    ])

    # When
    catalog = skills.catalog()

    # Then
    assert "# Skills" in catalog
    assert "- s1 @ l1: d1" in catalog
    assert "- s2 @ l2: d2" in catalog


def test_catalog_with_empty_list_returns_empty_string() -> None:
    # Given
    skills = Skills([])

    # When
    catalog = skills.catalog()

    # Then
    assert catalog == ""


def test_get_with_existing_name_returns_skill() -> None:
    # Given
    skill = Skill(name="test", description="d", location="l", content="c")
    skills = Skills([skill])

    # When
    result = skills.get("test")

    # Then
    assert result is skill


def test_get_with_missing_name_raises_key_error() -> None:
    # Given
    skills = Skills([])

    # When / Then
    with pytest.raises(KeyError, match="No skill named 'missing'"):
        skills.get("missing")


# =============================================================================
# discover_skills() Tests
# =============================================================================


def _create_skill_file(fs, path: str, frontmatter: str, content: str) -> None:
    """Helper to create a skill.md file with frontmatter and content in pyfakefs."""
    full_frontmatter = f"---\n{frontmatter}\n---\n{content}"
    fs.create_file(Path(path), contents=full_frontmatter)


def _mock_list_files(mocker: MockerFixture, file_paths: list[str]) -> MagicMock:
    """Helper to mock list_files to return the given file paths."""
    return mocker.patch("frugalbot.skills.list_files", return_value=[Path(p) for p in file_paths])


def test_discover_skills_with_valid_skill_returns_skill(fs, mocker: MockerFixture) -> None:
    # Given
    skill_md_path = ".frugalbot/skills/my-skill/skill.md"
    _create_skill_file(fs, skill_md_path, "name: My Skill\ndescription: My Skill Desc", "Skill content")
    _mock_list_files(mocker, [skill_md_path])

    # When
    skills = discover_skills()

    # Then
    assert len(skills.skills) == 1
    skill = skills.get("My Skill")
    assert skill.description == "My Skill Desc"
    assert skill.content == "Skill content"
    assert skill.location == skill_md_path


def test_discover_skills_with_missing_name_uses_folder_name(fs, mocker: MockerFixture) -> None:
    # Given
    skill_md_path = ".frugalbot/skills/fallback-skill/skill.md"
    _create_skill_file(fs, skill_md_path, "description: My Skill Desc", "Skill content")
    _mock_list_files(mocker, [skill_md_path])

    # When
    skills = discover_skills()

    # Then
    assert len(skills.skills) == 1
    skill = skills.get("fallback-skill")
    assert skill.description == "My Skill Desc"


def test_discover_skills_with_missing_description_uses_default(fs, mocker: MockerFixture) -> None:
    # Given
    skill_md_path = ".frugalbot/skills/no-desc-skill/skill.md"
    _create_skill_file(fs, skill_md_path, "name: No Desc Skill", "Skill content")
    _mock_list_files(mocker, [skill_md_path])

    # When
    skills = discover_skills()

    # Then
    assert len(skills.skills) == 1
    skill = skills.get("No Desc Skill")
    assert skill.description == "No description found"


def test_discover_skills_with_no_skill_directories_returns_empty_skills(fs, mocker: MockerFixture) -> None:
    # Given
    _mock_list_files(mocker, [])

    # When
    skills = discover_skills()

    # Then
    assert len(skills.skills) == 0


def test_discover_skills_with_multiple_skills_returns_all(fs, mocker: MockerFixture) -> None:
    # Given
    skill1_path = ".frugalbot/skills/alpha/skill.md"
    skill2_path = ".frugalbot/skills/beta/skill.md"
    _create_skill_file(fs, skill1_path, "name: Alpha\ndescription: Alpha desc", "Alpha content")
    _create_skill_file(fs, skill2_path, "name: Beta\ndescription: Beta desc", "Beta content")
    _mock_list_files(mocker, [skill1_path, skill2_path])

    # When
    skills = discover_skills()

    # Then
    assert len(skills.skills) == 2
    assert skills.get("Alpha").description == "Alpha desc"
    assert skills.get("Beta").description == "Beta desc"


def test_discover_skills_with_agents_skills_folder_finds_skills(fs, mocker: MockerFixture) -> None:
    # Given
    skill_md_path = ".agents/skills/agent-skill/skill.md"
    _create_skill_file(fs, skill_md_path, "name: Agent Skill\ndescription: Agent desc", "Agent content")
    _mock_list_files(mocker, [skill_md_path])

    # When
    skills = discover_skills()

    # Then
    assert len(skills.skills) == 1
    assert skills.get("Agent Skill").description == "Agent desc"


def test_discover_skills_with_claude_skills_folder_finds_skills(fs, mocker: MockerFixture) -> None:
    # Given
    skill_md_path = ".claude/skills/claude-skill/skill.md"
    _create_skill_file(fs, skill_md_path, "name: Claude Skill\ndescription: Claude desc", "Claude content")
    _mock_list_files(mocker, [skill_md_path])

    # When
    skills = discover_skills()

    # Then
    assert len(skills.skills) == 1
    assert skills.get("Claude Skill").description == "Claude desc"


def test_discover_skills_with_empty_name_string_uses_folder_name(fs, mocker: MockerFixture) -> None:
    # Given
    skill_md_path = ".frugalbot/skills/empty-name-skill/skill.md"
    _create_skill_file(fs, skill_md_path, 'name: ""\ndescription: Has empty name', "Content")
    _mock_list_files(mocker, [skill_md_path])

    # When
    skills = discover_skills()

    # Then
    assert len(skills.skills) == 1
    skill = skills.get("empty-name-skill")
    assert skill.description == "Has empty name"


def test_discover_skills_with_file_not_named_skill_md_ignores_file(fs, mocker: MockerFixture) -> None:
    # Given
    other_file_path = ".frugalbot/skills/my-skill/readme.md"
    fs.create_file(Path(other_file_path), contents="# Readme")
    _mock_list_files(mocker, [other_file_path])

    # When
    skills = discover_skills()

    # Then
    assert len(skills.skills) == 0


def test_discover_skills_with_uppercase_skill_md_name_finds_skill(fs, mocker: MockerFixture) -> None:
    # Given
    skill_md_path = ".frugalbot/skills/upper-skill/SKILL.md"
    _create_skill_file(fs, skill_md_path, "name: Upper Skill\ndescription: Upper desc", "Content")
    _mock_list_files(mocker, [skill_md_path])

    # When
    skills = discover_skills()

    # Then
    assert len(skills.skills) == 1
    assert skills.get("Upper Skill").description == "Upper desc"


def test_discover_skills_with_duplicate_folder_names_uses_last(fs, mocker: MockerFixture) -> None:
    # Given
    skill1_path = ".frugalbot/skills/dup/skill.md"
    skill2_path = ".agents/skills/dup/skill.md"
    _create_skill_file(fs, skill1_path, "name: Dup\ndescription: First", "First content")
    _create_skill_file(fs, skill2_path, "name: Dup\ndescription: Second", "Second content")
    _mock_list_files(mocker, [skill1_path, skill2_path])

    # When
    skills = discover_skills()

    # Then
    assert len(skills.skills) == 1
    assert skills.get("Dup").description == "Second"


def test_discover_skills_with_skill_location_outside_cwd_uses_absolute_path(fs, mocker: MockerFixture) -> None:
    # Given
    skill_md_path = "/home/user/.frugalbot/skills/external-skill/skill.md"
    _create_skill_file(fs, skill_md_path, "name: External\ndescription: External desc", "Content")
    _mock_list_files(mocker, [skill_md_path])
    # Create a separate cwd directory so the skill path is not under cwd
    fs.create_dir("/project")
    os.chdir("/project")

    # When
    skills = discover_skills()

    # Then
    assert len(skills.skills) == 1
    skill = skills.get("External")
    # When the skill is outside cwd, location is an absolute path (not relative to cwd)
    assert Path(skill.location).is_absolute()
