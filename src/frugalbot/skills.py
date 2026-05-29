from dataclasses import dataclass
from pathlib import Path

import frontmatter

from frugalbot.utils.filesystem import list_files

_SUB_FOLDERS = [".frugalbot/skills", ".agents/skills", ".claude/skills"]


@dataclass(slots=True)
class Skill:
    name: str
    description: str
    location: str
    content: str
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] | None = None
    allowed_tools: str | None = None

    def to_catalog_format(self) -> str:
        return f"{self.name} @ {self.location}: {self.description}"


class Skills:
    def __init__(self, skills: list[Skill]):
        self.skills = skills

    def catalog(self) -> str:
        skills = [f"- {skill.to_catalog_format()}" for skill in self.skills]
        if not skills:
            return ""
        return (
            "# Skills\nTo activate a skill, read and follow the instructions in the corresponding SKILL.md file. "
            "If one ore more skills below seem relevant to your task, you must activate them. "
            f"If you're not sure if the skill is relevant, you must activate it anyway.\nAvailable skills:\n{'\n'.join(skills)}"
        )

    def get(self, name) -> Skill:
        for skill in self.skills:
            if skill.name == name:
                return skill
        raise KeyError(f"No skill named '{name}'")

    def get_all(self) -> list[Skill]:
        return self.skills


def discover_skills() -> Skills:
    paths = [path for base_path in [Path.cwd(), Path.home()] for sub_path in _SUB_FOLDERS if (path := base_path / sub_path).exists()]
    files = list_files(paths, respect_gitignore=True, validate_path=False)
    raw_skills_map: dict[str, Path] = {file.parent.name: file for file in files if file.name.lower() == "skill.md"}
    skills: list[Skill] = []
    for parent_folder_name, skill_md_file_path in raw_skills_map.items():
        parsed_skill_md = frontmatter.load(str(skill_md_file_path))
        skill_name = parsed_skill_md.get("name") or parent_folder_name
        description = str(parsed_skill_md.get("description", "No description found"))
        location_path = skill_md_file_path.resolve().absolute()
        if location_path.is_relative_to(Path.cwd()):
            location = location_path.relative_to(Path.cwd()).as_posix()
        else:
            location = location_path.as_posix()
        skills.append(Skill(name=str(skill_name), description=description, location=location, content=parsed_skill_md.content))
    return Skills(skills)
