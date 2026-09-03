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
[System.Management.Automation.Language.Parser]::ParseInput(
    $cmd,
    [ref]$tokens,
    [ref]$errors
) | Out-Null

if ($errors.Count -gt 0) {{
    $errors | ForEach-Object {{ Write-Error $_.Message }}
    exit 1
}}

{exempt_patterns_ps}

$all = [System.Collections.Generic.List[object]]::new()
$cur = [System.Collections.Generic.List[string]]::new()

foreach ($tok in $tokens) {{
    if ($tok.Kind -in @('NewLine', 'EndOfInput')) {{
        if ($cur.Count -gt 0) {{
            $all.Add($cur.ToArray())
            $cur = [System.Collections.Generic.List[string]]::new()
        }}
        continue
    }}

    if ($tok.Kind -in @('Semi', 'AndAnd', 'OrOr', 'Ampersand', 'Pipe')) {{
        if ($cur.Count -gt 0) {{
            $all.Add($cur.ToArray())
            $cur = [System.Collections.Generic.List[string]]::new()
        }}
        continue
    }}

    if ($tok.Kind -in @(
        'DollarParen',
        'AtParen',
        'LCurly',
        'StringExpandable',
        'HereStringExpandable'
    )) {{
        $is_exempt = $false

        if ($cur.Count -gt 0) {{
            foreach ($pattern in $exempt_patterns) {{
                if ($cur.Count -lt $pattern.Length) {{
                    continue
                }}

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

        if ($is_exempt) {{
            $cur.Add($tok.Text)
        }} else {{
            if ($cur.Count -gt 0) {{
                $all.Add($cur.ToArray())
                $cur = [System.Collections.Generic.List[string]]::new()
            }}

            # MUST_APPROVE is token zero so prefix allow rules cannot match it.
            $cur.Add('MUST_APPROVE')
            $cur.Add($tok.Text)
        }}

        continue
    }}

    $cur.Add($tok.Text)
}}

if ($cur.Count -gt 0) {{
    $all.Add($cur.ToArray())
}}

ConvertTo-Json -InputObject $all -Compress
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
