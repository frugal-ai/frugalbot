import asyncio
import base64

import orjson as json

from frugalbot.hooks.base import ApprovalState, HookBase, HookConfig, HookError, PreToolCallHook


class AutoApprovalConfig(HookConfig):
    exempted: list[list[str]]  # list of commands automatically approved regardless of usage of expandable strings
    allowed: list[list[str]]
    denied: list[tuple[list[str], str]]  # tuple of command words and denied reason


def _make_ps_script(cmd_string: str, exempt_commands: list[list[str]]) -> str:
    # Build the .NET List of string arrays to prevent PowerShell from unrolling/flattening single-item lists
    exempt_init_lines = ["$exempt_patterns = [System.Collections.Generic.List[string[]]]::new()"]
    for pattern in exempt_commands:
        escaped_items = ", ".join(f"'{cmd.replace("'", "''")}'" for cmd in pattern)
        exempt_init_lines.append(f"$exempt_patterns.Add([string[]]@({escaped_items}))")

    exempt_patterns_ps = "\n".join(exempt_init_lines)
    b64 = base64.b64encode(cmd_string.encode("utf-16-le")).decode("ascii")

    return f"""
$cmd = [System.Text.Encoding]::Unicode.GetString([System.Convert]::FromBase64String('{b64}'))
$tokens = $null; $errors = $null
[System.Management.Automation.Language.Parser]::ParseInput($cmd, [ref]$tokens, [ref]$errors) | Out-Null

{exempt_patterns_ps}

$all = [System.Collections.Generic.List[object]]::new()
$cur = [System.Collections.Generic.List[string]]::new()

foreach ($tok in $tokens) {{
    if ($tok.Kind -in @('NewLine','EndOfInput')) {{
        if ($cur.Count -gt 0) {{ $all.Add($cur.ToArray()); $cur = [System.Collections.Generic.List[string]]::new() }}
        continue
    }}
    if ($tok.Kind -in @('Semi','AndAnd','OrOr','Ampersand','Pipe')) {{
        if ($cur.Count -gt 0) {{ $all.Add($cur.ToArray()); $cur = [System.Collections.Generic.List[string]]::new() }}
    }} elseif ($tok.Kind -in @('DollarParen','AtParen','LCurly','StringExpandable','HereStringExpandable')) {{
        
        # Check if the parsed tokens in $cur start with any of the exempt patterns
        $is_exempt = $false
        if ($cur.Count -gt 0) {{
            foreach ($pattern in $exempt_patterns) {{
                if ($cur.Count -ge $pattern.Length) {{
                    $matches = $true
                    for ($i = 0; $i -lt $pattern.Length; $i++) {{
                        if ($cur[$i] -ne $pattern[$i]) {{
                            $matches = $false
                            break
                        }}
                    }}
                    if ($matches) {{
                        $is_exempt = $true
                        break
                    }}
                }}
            }}
        }}

        if ($is_exempt) {{
            $cur.Add($tok.Text)
        }} else {{
            if ($cur.Count -gt 0) {{ $all.Add($cur.ToArray()); $cur = [System.Collections.Generic.List[string]]::new() }}
            $cur.Add('MUST_APPROVE')
            $cur.Add($tok.Text)
        }}
    }} else {{
        $cur.Add($tok.Text)
    }}
}}
if ($cur.Count -gt 0) {{ $all.Add($cur.ToArray()) }}
ConvertTo-Json -InputObject $all -Compress
"""


async def _split_powershell_commands(cmd_string: str, exempt_commands: list[list[str]]) -> list[list[str]]:
    proc = await asyncio.create_subprocess_exec(
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        _make_ps_script(cmd_string, exempt_commands),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise HookError(f"pwsh failed (exit {proc.returncode}): {stderr.decode()}")

    return json.loads(stdout.decode().strip())


def _is_match(a: list[str], b: list[str]):
    """Returns true if all elements of list a match the first len(a) elements of list b."""
    return len(b) >= len(a) and all(a == "DONTCARE" or a == b for a, b in zip(a, b[: len(a)], strict=True))


class AutoApprovalHook(HookBase[PreToolCallHook, AutoApprovalConfig]):
    async def run(self, hook_data) -> None:
        if hook_data.state in (ApprovalState.APPROVED, ApprovalState.DENIED):
            return
        args = hook_data.arguments
        if hook_data.tool_name == "listfiles":
            hook_data.state = ApprovalState.APPROVED
        if "path" in args and isinstance(args["path"], str):
            path = args["path"].lstrip()
            if not path.startswith("/") and not path.startswith("\\"):
                hook_data.state = ApprovalState.APPROVED
            else:
                hook_data.state = ApprovalState.DENIED
                hook_data.denied_reason = "Absolute paths are not allowed"
        elif hook_data.tool_name == "powershell" and "command" in args and isinstance(args["command"], str):
            commands = await _split_powershell_commands(args["command"], self.config.exempted)
            all_approved = True

            for command in commands:
                for denied, reason in self.config.denied:
                    if _is_match(denied, command):
                        hook_data.state = ApprovalState.DENIED
                        hook_data.denied_reason = reason
                        return

                approved = False
                allowed_lists = [self.config.allowed, self.config.exempted]
                for allowed_list in allowed_lists:
                    for allowed in allowed_list:
                        if _is_match(allowed, command):
                            approved = True
                            break
                    if approved:
                        break

                if not approved:
                    all_approved = False
                    break

            if all_approved:
                hook_data.state = ApprovalState.APPROVED
