from pydantic import BaseModel, Field, field_validator


class MCPServerConfig(BaseModel):
    """Config for a single MCP server, parsed from TOML."""

    command: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None
    enabled: bool = True
    connection_timeout: float = 60.0  # seconds, can be overridden per-server
    execution_timeout: float = 300.0  # seconds, timeout for individual tool calls
    enabled_tools: list[str] = Field(default_factory=list)

    @field_validator("command")
    @classmethod
    def validate_command_has_executable(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("The mcp 'command' field must specify at least an executable path (cannot be empty).")
        return v
