from __future__ import annotations

from frugalbot.hooks.auto_approval_bash import split_bash_commands
from frugalbot.hooks.auto_approval_powershell import split_powershell_commands
from frugalbot.hooks.base import (
    ApprovalState,
    HookBase,
    HookConfig,
    HookError,
    PreToolCallHook,
)


class AutoApprovalConfig(HookConfig):
    # Command prefixes approved even if their command contains a shell
    # expansion, redirection, assignment, or other sensitive shell syntax.
    # Keep this list extremely narrow.
    exempted: list[list[str]]

    # Command prefixes that may be auto-approved only when no MUST_APPROVE
    # marker is present.
    allowed: list[list[str]]

    # (command-prefix, denial reason)
    denied: list[tuple[list[str], str]]


_SHELL_TOOLS = frozenset({"powershell", "bash"})


def _is_match(pattern: list[str], command: list[str]) -> bool:
    """Return True if pattern matches the leading tokens of command."""
    return len(command) >= len(pattern) and all(
        expected == "DONTCARE" or expected == actual
        for expected, actual in zip(
            pattern,
            command[: len(pattern)],
            strict=True,
        )
    )


async def _split_shell_commands(
    tool_name: str,
    cmd_string: str,
    exempt_commands: list[list[str]],
) -> list[list[str]]:
    if tool_name == "powershell":
        return await split_powershell_commands(cmd_string, exempt_commands)

    if tool_name == "bash":
        return await split_bash_commands(cmd_string, exempt_commands)

    raise HookError(f"Unsupported shell tool: {tool_name}")


class AutoApprovalHook(HookBase[PreToolCallHook, AutoApprovalConfig]):
    async def run(self, hook_data) -> None:
        if hook_data.state in (ApprovalState.APPROVED, ApprovalState.DENIED):
            return

        args = hook_data.arguments
        tool_name = hook_data.tool_name

        if tool_name == "listfiles":
            hook_data.state = ApprovalState.APPROVED
            return

        if "path" in args and isinstance(args.get("path"), str):
            path = args["path"].lstrip()

            if path.startswith(("/", "\\")):
                hook_data.state = ApprovalState.DENIED
                hook_data.denied_reason = "Absolute paths are not allowed"
            else:
                hook_data.state = ApprovalState.APPROVED

            return

        if tool_name not in _SHELL_TOOLS or not isinstance(args.get("command"), str):
            return

        commands = await _split_shell_commands(
            tool_name,
            args["command"],
            self.config.exempted,
        )

        # Denials always win, including for a nested command substitution.
        for command in commands:
            for denied_pattern, reason in self.config.denied:
                if _is_match(denied_pattern, command):
                    hook_data.state = ApprovalState.DENIED
                    hook_data.denied_reason = reason
                    return

            approved = False

        # A tool call is auto-approved only if every parsed command is allowed
        # or exempt. A leading MUST_APPROVE marker prevents normal prefix rules
        # from matching; only pre-marker exemption evaluation can waive it.
        for command in commands:
            approved = any(_is_match(pattern, command) for rules in (self.config.allowed, self.config.exempted) for pattern in rules)

            if not approved:
                return

        hook_data.state = ApprovalState.APPROVED
