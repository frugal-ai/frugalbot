from __future__ import annotations

import asyncio
import base64

import orjson as json

from frugalbot.hooks.base import HookError


def _ps_single_quote(value: str) -> str:
    """Render value as a PowerShell single-quoted string literal."""
    return "'" + value.replace("'", "''") + "'"


def _make_ps_script(cmd_string: str, exempt_commands: list[list[str]]) -> str:
    """Build a PowerShell parser script that emits command-token arrays."""
    exempt_init_lines = ["$exempt_patterns = [System.Collections.Generic.List[string[]]]::new()"]

    for pattern in exempt_commands:
        escaped_items = ", ".join(_ps_single_quote(item) for item in pattern)
        exempt_init_lines.append(f"$exempt_patterns.Add([string[]]@({escaped_items}))")

    exempt_patterns_ps = "\n".join(exempt_init_lines)
    encoded_command = base64.b64encode(cmd_string.encode("utf-16-le")).decode("ascii")

    return f"""
$cmd = [System.Text.Encoding]::Unicode.GetString(
    [System.Convert]::FromBase64String('{encoded_command}')
)

$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput(
    $cmd,
    [ref]$tokens,
    [ref]$errors
)

if ($errors.Count -gt 0) {{
    $errors | ForEach-Object {{ Write-Error $_.Message }}
    exit 1
}}

{exempt_patterns_ps}

function Test-Exempt($cmdTokens) {{
    if ($cmdTokens.Count -eq 0 -or $exempt_patterns.Count -eq 0) {{
        return $false
    }}
    foreach ($pattern in $exempt_patterns) {{
        if ($cmdTokens.Count -lt $pattern.Length) {{ continue }}
        $matches = $true
        for ($i = 0; $i -lt $pattern.Length; $i++) {{
            if ($cmdTokens[$i] -ne $pattern[$i]) {{
                $matches = $false
                break
            }}
        }}
        if ($matches) {{ return $true }}
    }}
    return $false
}}

$commands = $ast.FindAll({{
    param($node)
    $node -is [System.Management.Automation.Language.CommandAst]
}}, $true)

$all = [System.Collections.Generic.List[object]]::new()

foreach ($command in $commands) {{
    $cur = [System.Collections.Generic.List[string]]::new()

    foreach ($el in $command.CommandElements) {{
        # 1. Skip subexpressions / parens whose inner commands are already picked up by FindAll
        if ($el -is [System.Management.Automation.Language.SubExpressionAst] -or
            $el -is [System.Management.Automation.Language.ParenExpressionAst] -or
            $el -is [System.Management.Automation.Language.ArrayExpressionAst]) {{
            continue
        }}

        # 2. Tag non-exempt expandable strings or script blocks with MUST_APPROVE
        if ($el -is [System.Management.Automation.Language.ExpandableStringExpressionAst] -or
            $el -is [System.Management.Automation.Language.ScriptBlockExpressionAst]) {{
            if (-not (Test-Exempt $cur)) {{
                if ($cur.Count -gt 0) {{
                    $all.Add($cur.ToArray())
                    $cur = [System.Collections.Generic.List[string]]::new()
                }}
                $cur.Add('MUST_APPROVE')
                $cur.Add($el.Extent.Text)
                continue
            }}
        }}

        $cur.Add($el.Extent.Text)
    }}

    if ($cur.Count -gt 0) {{
        $all.Add($cur.ToArray())
    }}
}}

if ($all.Count -eq 0) {{
    "[]"
}} else {{
    ConvertTo-Json -InputObject $all -Compress
}}
"""


async def split_powershell_commands(
    cmd_string: str,
    exempt_commands: list[list[str]],
) -> list[list[str]]:
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
        raise HookError(f"PowerShell parsing failed (exit {proc.returncode}): {stderr.decode(errors='replace')}")

    output = stdout.decode().strip()
    return json.loads(output) if output else []
