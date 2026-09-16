#!/usr/bin/env python3
"""Convert LLM conversation JSON exports into clean, self-contained HTML transcripts.

Features:
- Complete tool JSON schema inspector (table + raw JSON)
- Thinking / reasoning blocks with token counts
- Collapsible cards for every message / tool turn
- Stop / finish reason badge display
- Offline client-side syntax highlighting (JSON, Python, XML, Diff, YAML, Bash)
- Interactive toolbar (search, mass toggle controls, copy buttons)

Requirements: Python 3.10+ (Standard Library only, no pip dependencies).
Usage:
    python convert_transcript.py input.json -o transcript.html
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Markdown & Text Formatting Helpers
# ---------------------------------------------------------------------------


def escape(text: Any) -> str:
    """Safely escape text for HTML output."""
    if text is None:
        return ""
    return html.escape(str(text))


def render_markdown(text: str) -> str:
    """Convert common markdown patterns to HTML safely without external libraries."""
    if not text:
        return ""

    parts = re.split(r"(```[\w-]*\n[\s\S]*?\n```)", text)
    html_out: list[str] = []

    for part in parts:
        if part.startswith("```"):
            match = re.match(r"^```([\w-]*)\n([\s\S]*?)\n```$", part)
            if match:
                lang, code = match.groups()
                lang_cls = f' class="language-{escape(lang)}"' if lang else ""
                html_out.append(f'<div class="code-wrapper"><button class="copy-btn" onclick="copyCode(this)">Copy</button><pre><code{lang_cls}>{escape(code)}</code></pre></div>')
            else:
                html_out.append(f"<pre><code>{escape(part)}</code></pre>")
            continue

        lines = part.split("\n")
        in_list = False
        p_buffer: list[str] = []

        def flush_p() -> None:
            if p_buffer:
                p_text = " ".join(p_buffer).strip()
                if p_text:
                    html_out.append(f"<p>{p_text}</p>")
                p_buffer.clear()

        for line in lines:
            line_str = line.strip()

            # Headers
            h_match = re.match(r"^(#{1,4})\s+(.*)$", line_str)
            if h_match:
                flush_p()
                if in_list:
                    html_out.append("</ul>")
                    in_list = False
                level = len(h_match.group(1))
                html_out.append(f"<h{level}>{format_inline(h_match.group(2))}</h{level}>")
                continue

            # Unordered lists
            ul_match = re.match(r"^[-*]\s+(.*)$", line_str)
            if ul_match:
                flush_p()
                if not in_list:
                    html_out.append("<ul>")
                    in_list = True
                html_out.append(f"<li>{format_inline(ul_match.group(1))}</li>")
                continue

            if in_list and not line_str:
                html_out.append("</ul>")
                in_list = False
                continue

            # Empty lines break paragraphs
            if not line_str:
                flush_p()
                continue

            p_buffer.append(format_inline(line))

        flush_p()
        if in_list:
            html_out.append("</ul>")

    return "\n".join(html_out)


def format_inline(text: str) -> str:
    """Format bold, italics, inline code, and URLs."""
    t = escape(text)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        t,
    )
    return t


# ---------------------------------------------------------------------------
# Schema & Tool Extraction
# ---------------------------------------------------------------------------


def extract_tools(raw_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Locate tool definitions from multiple LLM export standards."""
    candidates = raw_data.get("tools") or raw_data.get("tool_definitions") or raw_data.get("tools_schema") or raw_data.get("functions") or []

    normalized: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        # OpenAI style: {type: 'function', function: {...}}
        if "function" in item and isinstance(item["function"], dict):
            fn = item["function"]
            normalized.append({
                "name": fn.get("name", "unnamed_tool"),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters") or fn.get("input_schema") or {},
            })
        # Anthropic / Gemini / direct format
        elif "name" in item:
            normalized.append({
                "name": item.get("name", "unnamed_tool"),
                "description": item.get("description", ""),
                "parameters": item.get("parameters") or item.get("input_schema") or {},
            })
    return normalized


def render_tool_schemas(tools: list[dict[str, Any]]) -> str:
    """Render tool declarations and JSON schema parameters into HTML."""
    if not tools:
        return ""

    cards_html: list[str] = []
    for tool in tools:
        name = escape(tool.get("name", ""))
        desc = escape(tool.get("description", "No description provided."))
        params = tool.get("parameters", {})

        props = params.get("properties", {}) if isinstance(params, dict) else {}
        required = set(params.get("required", [])) if isinstance(params, dict) else set()

        rows_html: list[str] = []
        if props:
            for p_name, p_info in props.items():
                p_type = p_info.get("type", "any") if isinstance(p_info, dict) else "any"
                p_desc = p_info.get("description", "") if isinstance(p_info, dict) else ""
                is_req = p_name in required
                req_badge = '<span class="badge req">required</span>' if is_req else '<span class="badge opt">optional</span>'
                rows_html.append(f'<tr><td><code>{escape(p_name)}</code></td><td><span class="type-pill">{escape(p_type)}</span></td><td>{req_badge}</td><td>{escape(p_desc)}</td></tr>')

        table_section = ""
        if rows_html:
            table_section = (
                f'<div class="table-responsive">'
                f'<table class="schema-table">'
                f"<thead><tr><th>Property</th><th>Type</th><th>Presence</th><th>Description</th></tr></thead>"
                f"<tbody>{''.join(rows_html)}</tbody>"
                f"</table>"
                f"</div>"
            )

        schema_json = json.dumps(params, indent=2)
        cards_html.append(
            f"""
            <div class="tool-schema-card">
              <div class="tool-card-header">
                <span class="tool-badge-pill">tool</span>
                <span class="tool-name">{name}</span>
              </div>
              <p class="tool-desc">{desc}</p>
              {table_section}
              <details class="nested-details">
                <summary>View Raw JSON Schema</summary>
                <div class="code-wrapper">
                  <button class="copy-btn" onclick="copyCode(this)">Copy</button>
                  <pre><code class="language-json">{escape(schema_json)}</code></pre>
                </div>
              </details>
            </div>
            """
        )

    return f"""
    <section class="tools-container">
      <details open class="main-details">
        <summary class="section-summary">
          <span>🛠️ Tool Definitions &amp; JSON Schemas ({len(tools)})</span>
          <span class="meta">Declarations available to model</span>
        </summary>
        <div class="tools-grid">
          {"".join(cards_html)}
        </div>
      </details>
    </section>
    """


# ---------------------------------------------------------------------------
# Message & Completion Extraction
# ---------------------------------------------------------------------------


def extract_thinking(msg_data: dict[str, Any]) -> str | None:
    """Extract reasoning/thinking blocks from various LLM payload formats."""
    # 1. Reasoning field (dict or string)
    reasoning = msg_data.get("reasoning")
    if isinstance(reasoning, dict):
        content = reasoning.get("content") or reasoning.get("text")
        if content and str(content).strip():
            return str(content).strip()
    elif isinstance(reasoning, str) and reasoning.strip():
        return reasoning.strip()

    # 2. DeepSeek reasoning_content
    rc = msg_data.get("reasoning_content")
    if isinstance(rc, str) and rc.strip():
        return rc.strip()

    # 3. Anthropic thinking
    thinking = msg_data.get("thinking")
    if isinstance(thinking, dict):
        text = thinking.get("text") or thinking.get("content")
        if text and str(text).strip():
            return str(text).strip()
    elif isinstance(thinking, str) and thinking.strip():
        return thinking.strip()

    return None


def format_tool_content(content: str) -> str:
    """Format and determine the language class for tool output."""
    if not content:
        return "<em>(empty output)</em>"

    lang = "text"
    cleaned = content.strip()

    # Check for diffs
    if re.search(r"(?m)^(---|\+\+\+|@@ -\d+,\d+ \+\d+,\d+ @@)", cleaned):
        lang = "diff"
    # Check for JSON
    elif (cleaned.startswith("{") and cleaned.endswith("}")) or (cleaned.startswith("[") and cleaned.endswith("]")):
        try:
            parsed = json.loads(cleaned)
            content = json.dumps(parsed, indent=2)
            lang = "json"
        except Exception:
            pass
    # Check for XML/HTML
    elif cleaned.startswith("<") and cleaned.endswith(">"):
        lang = "xml"
    # Check for YAML/Structured text
    elif ":" in cleaned and ("\n  " in cleaned or "\n- " in cleaned):
        lang = "yaml"

    return f'<div class="code-wrapper"><button class="copy-btn" onclick="copyCode(this)">Copy</button><pre><code class="language-{lang}">{escape(content)}</code></pre></div>'


def parse_events(
    raw_data: dict[str, Any],
) -> tuple[list[str], dict[str, int]]:
    """Parse messages into structured HTML components and compute metrics."""
    elements: list[str] = []
    metrics = {
        "messages": 0,
        "tool_calls": 0,
        "tool_results": 0,
        "reasoning_tokens": 0,
    }

    messages = raw_data.get("messages", [])

    for idx, item in enumerate(messages):
        item_type = item.get("type")
        data = item.get("data", {})

        if item_type == "message":
            role = data.get("role", "unknown")
            content = data.get("content", "")

            # Tool execution result
            if role == "tool":
                metrics["tool_results"] += 1
                tool_name = data.get("name", "tool")
                call_id = data.get("tool_call_id", "")
                is_error = "Error" in content or "error" in content.lower() or "failed" in content.lower()
                status_badge = '<span class="status-badge error">ERROR</span>' if is_error else '<span class="status-badge success">SUCCESS</span>'

                elements.append(
                    f"""
                    <details class="message role-tool" open data-role="tool">
                      <summary class="msg-header">
                        <div class="role-badge">
                          <span>⚡</span> Output: <strong>{escape(tool_name)}</strong>
                          {status_badge}
                        </div>
                        <div class="msg-header-right">
                          <span class="meta mono">{escape(call_id)}</span>
                          <span class="chevron-icon">▾</span>
                        </div>
                      </summary>
                      <div class="msg-body">
                        {format_tool_content(content)}
                      </div>
                    </details>
                    """
                )
                continue

            # Standard User or System messages
            metrics["messages"] += 1
            avatar = "👤" if role == "user" else "⚙️"
            elements.append(
                f"""
                <details class="message role-{role}" open data-role="{role}">
                  <summary class="msg-header">
                    <div class="role-badge">
                      <span>{avatar}</span>
                      <strong>{role.upper()}</strong>
                    </div>
                    <div class="msg-header-right">
                      <span class="meta mono">msg #{idx + 1}</span>
                      <span class="chevron-icon">▾</span>
                    </div>
                  </summary>
                  <div class="msg-body">
                    {render_markdown(content)}
                  </div>
                </details>
                """
            )

        elif item_type == "completion":
            metrics["messages"] += 1
            usage = data.get("usage", {})
            r_tokens = usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
            metrics["reasoning_tokens"] += r_tokens

            choices = data.get("choices", [])
            for choice in choices:
                msg = choice.get("message", {})
                content = msg.get("content")
                tool_calls = msg.get("tool_calls") or []
                thinking = extract_thinking(msg)

                # Stop / Finish reason
                stop_reason = choice.get("finish_reason") or choice.get("stop_reason") or data.get("stop_reason") or data.get("finish_reason")
                stop_pill = f'<span class="stop-reason-pill mono" title="Stop / Finish reason">stop: {escape(stop_reason)}</span>' if stop_reason else ""

                body_parts: list[str] = []

                # Thinking / Reasoning Block
                if thinking:
                    r_badge = f'<span class="token-pill">{r_tokens} tokens</span>' if r_tokens else ""
                    body_parts.append(
                        f"""
                        <details class="thinking-block" open>
                          <summary class="thinking-summary">
                            <span>💭 Thought Process / Reasoning</span>
                            {r_badge}
                          </summary>
                          <div class="thinking-content">
                            {render_markdown(thinking)}
                          </div>
                        </details>
                        """
                    )

                # Tool Calls made by Assistant
                if tool_calls:
                    for call in tool_calls:
                        metrics["tool_calls"] += 1
                        fn = call.get("function", {})
                        fn_name = fn.get("name", "unknown")
                        fn_args = fn.get("arguments", "{}")
                        call_id = call.get("id", "")

                        formatted_args = fn_args
                        try:
                            if isinstance(fn_args, str):
                                formatted_args = json.dumps(json.loads(fn_args), indent=2)
                        except Exception:
                            pass

                        body_parts.append(
                            f"""
                            <div class="tool-call-block">
                              <div class="tool-call-header">
                                <span class="tool-call-tag">Tool Call</span>
                                <span class="tool-call-name">{escape(fn_name)}</span>
                                <span class="meta mono">({escape(call_id)})</span>
                              </div>
                              <div class="code-wrapper">
                                <button class="copy-btn" onclick="copyCode(this)">Copy</button>
                                <pre><code class="language-json">{escape(formatted_args)}</code></pre>
                              </div>
                            </div>
                            """
                        )

                # Regular assistant reply text
                if content:
                    body_parts.append(f'<div class="assistant-content">{render_markdown(content)}</div>')

                if body_parts:
                    elements.append(
                        f"""
                        <details class="message role-assistant" open data-role="assistant">
                          <summary class="msg-header">
                            <div class="role-badge">
                              <span>🤖</span>
                              <strong>ASSISTANT</strong>
                            </div>
                            <div class="msg-header-right">
                              {stop_pill}
                              <span class="meta mono">turn #{idx + 1}</span>
                              <span class="chevron-icon">▾</span>
                            </div>
                          </summary>
                          <div class="msg-body">
                            {"".join(body_parts)}
                          </div>
                        </details>
                        """
                    )

    return elements, metrics


# ---------------------------------------------------------------------------
# HTML Page Template with Self-Contained Styles & Syntax Highlighter
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{page_title}</title>
  <style>
    :root {{
      --bg: #0d1117;
      --card-bg: #161b22;
      --card-bg-subtle: #1c2128;
      --border: #30363d;
      --border-accent: #388bfd33;
      --text: #c9d1d9;
      --text-muted: #8b949e;
      --code-bg: #0b0e14;
      --code-text: #e6edf3;

      --accent-system: #d29922;
      --accent-user: #58a6ff;
      --accent-assistant: #bc8cff;
      --accent-tool: #3fb950;
      --accent-error: #f85149;
      --thinking-border: #f0883e;
      --thinking-bg: #16191f;

      --font-mono: "JetBrains Mono", "Fira Code", SFMono-Regular, Consolas, Menlo, monospace;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Helvetica, Arial, sans-serif;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background-color: var(--bg);
      color: var(--text);
      font-family: var(--font-sans);
      font-size: 14.5px;
      line-height: 1.6;
      padding: 1.5rem 1rem 4rem;
    }}

    .container {{
      max-width: 980px;
      margin: 0 auto;
    }}

    header {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1.25rem 1.5rem;
      margin-bottom: 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }}

    .header-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1rem;
    }}

    h1 {{
      font-size: 1.25rem;
      color: #fff;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }}

    .metrics-bar {{
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
    }}

    .metric-pill {{
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border);
      padding: 0.2rem 0.6rem;
      border-radius: 20px;
      font-size: 0.75rem;
      font-family: var(--font-mono);
      color: var(--text-muted);
    }}

    .metric-pill strong {{
      color: #fff;
    }}

    .toolbar {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.6rem 1rem;
      margin-bottom: 1.5rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.75rem;
      position: sticky;
      top: 10px;
      z-index: 100;
      box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    }}

    .btn-group {{
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
    }}

    .btn {{
      background: #21262d;
      border: 1px solid var(--border);
      color: var(--text);
      padding: 0.35rem 0.75rem;
      border-radius: 6px;
      font-size: 0.8rem;
      cursor: pointer;
      font-weight: 500;
      transition: all 0.15s ease;
    }}

    .btn:hover {{
      background: #30363d;
      color: #fff;
      border-color: #8b949e;
    }}

    .search-box {{
      background: #0d1117;
      border: 1px solid var(--border);
      color: #fff;
      padding: 0.35rem 0.75rem;
      border-radius: 6px;
      font-size: 0.8rem;
      outline: none;
      width: 220px;
    }}

    .search-box:focus {{
      border-color: var(--accent-user);
    }}

    .tools-container {{
      margin-bottom: 1.5rem;
    }}

    .main-details {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
    }}

    .section-summary {{
      padding: 0.85rem 1.25rem;
      font-weight: 600;
      font-size: 0.95rem;
      cursor: pointer;
      user-select: none;
      background: rgba(255, 255, 255, 0.02);
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}

    .section-summary:hover {{
      background: rgba(255, 255, 255, 0.04);
    }}

    .tools-grid {{
      padding: 1.25rem;
      display: grid;
      grid-template-columns: 1fr;
      gap: 1.25rem;
    }}

    .tool-schema-card {{
      background: var(--card-bg-subtle);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1rem;
    }}

    .tool-card-header {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 0.5rem;
    }}

    .tool-badge-pill {{
      font-size: 0.7rem;
      text-transform: uppercase;
      font-weight: 700;
      background: rgba(56, 139, 253, 0.15);
      color: var(--accent-user);
      border: 1px solid rgba(56, 139, 253, 0.3);
      padding: 1px 6px;
      border-radius: 4px;
    }}

    .tool-name {{
      font-family: var(--font-mono);
      font-weight: 600;
      color: #79c0ff;
      font-size: 1rem;
    }}

    .tool-desc {{
      color: var(--text-muted);
      font-size: 0.85rem;
      margin-bottom: 0.75rem;
    }}

    .table-responsive {{
      overflow-x: auto;
      margin: 0.5rem 0;
    }}

    .schema-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
      text-align: left;
    }}

    .schema-table th, .schema-table td {{
      padding: 0.4rem 0.6rem;
      border: 1px solid var(--border);
    }}

    .schema-table th {{
      background: rgba(255, 255, 255, 0.03);
      color: var(--text-muted);
    }}

    .type-pill {{
      color: #bc8cff;
      font-family: var(--font-mono);
      font-size: 0.75rem;
    }}

    .badge {{
      font-size: 0.65rem;
      padding: 1px 5px;
      border-radius: 3px;
      text-transform: uppercase;
      font-weight: 600;
    }}

    .badge.req {{ background: rgba(248, 81, 73, 0.2); color: #ff7b72; }}
    .badge.opt {{ background: rgba(139, 148, 158, 0.2); color: #8b949e; }}

    .timeline {{
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }}

    .message {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }}

    .msg-header {{
      padding: 0.5rem 1rem;
      font-size: 0.8rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: rgba(255, 255, 255, 0.02);
      border-bottom: 1px solid var(--border);
    }}

    summary.msg-header {{
      cursor: pointer;
      user-select: none;
      list-style: none;
    }}

    summary.msg-header::-webkit-details-marker {{
      display: none;
    }}

    details.message:not([open]) .msg-header {{
      border-bottom: none;
    }}

    .msg-header-right {{
      display: flex;
      align-items: center;
      gap: 0.6rem;
    }}

    .chevron-icon {{
      color: var(--text-muted);
      font-size: 0.75rem;
      transition: transform 0.15s ease;
      display: inline-block;
    }}

    details[open] > summary .chevron-icon {{
      transform: rotate(0deg);
    }}

    details:not([open]) > summary .chevron-icon {{
      transform: rotate(-90deg);
    }}

    .stop-reason-pill {{
      font-size: 0.7rem;
      background: rgba(188, 140, 255, 0.15);
      border: 1px solid rgba(188, 140, 255, 0.3);
      color: #d2a8ff;
      padding: 1px 6px;
      border-radius: 4px;
      font-family: var(--font-mono);
    }}

    .role-badge {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
    }}

    .role-system {{ border-top: 3px solid var(--accent-system); }}
    .role-system .msg-header {{ color: var(--accent-system); }}
    .role-user {{ border-top: 3px solid var(--accent-user); }}
    .role-user .msg-header {{ color: var(--accent-user); }}
    .role-assistant {{ border-top: 3px solid var(--accent-assistant); }}
    .role-assistant .msg-header {{ color: var(--accent-assistant); }}
    .role-tool {{ border-top: 3px solid var(--accent-tool); }}
    .role-tool .msg-header {{ color: var(--accent-tool); }}

    .msg-body {{
      padding: 1rem 1.25rem;
    }}

    .msg-body p {{ margin-bottom: 0.75rem; }}
    .msg-body p:last-child {{ margin-bottom: 0; }}
    .msg-body ul {{ margin-left: 1.5rem; margin-bottom: 0.75rem; }}
    .msg-body h1, .msg-body h2, .msg-body h3 {{
      color: #fff;
      margin: 1rem 0 0.5rem;
    }}

    .thinking-block {{
      background: var(--thinking-bg);
      border: 1px solid rgba(240, 136, 62, 0.3);
      border-left: 3px solid var(--thinking-border);
      border-radius: 6px;
      margin-bottom: 1rem;
      overflow: hidden;
    }}

    .thinking-summary {{
      padding: 0.5rem 0.85rem;
      font-size: 0.82rem;
      font-weight: 600;
      color: #f0883e;
      cursor: pointer;
      user-select: none;
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: rgba(240, 136, 62, 0.05);
    }}

    .thinking-content {{
      padding: 0.85rem 1rem;
      font-size: 0.88rem;
      color: #d0d7de;
      border-top: 1px solid rgba(240, 136, 62, 0.15);
    }}

    .token-pill {{
      font-size: 0.7rem;
      background: rgba(240, 136, 62, 0.2);
      padding: 2px 6px;
      border-radius: 12px;
      color: #ffa657;
      font-family: var(--font-mono);
    }}

    .tool-call-block {{
      background: var(--card-bg-subtle);
      border: 1px solid var(--border);
      border-radius: 6px;
      margin: 0.75rem 0;
      overflow: hidden;
    }}

    .tool-call-header {{
      padding: 0.4rem 0.75rem;
      background: rgba(56, 139, 253, 0.08);
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      gap: 0.6rem;
      font-size: 0.8rem;
    }}

    .tool-call-tag {{
      background: #1f6feb;
      color: #fff;
      font-size: 0.65rem;
      padding: 1px 5px;
      border-radius: 3px;
      font-weight: bold;
      text-transform: uppercase;
    }}

    .tool-call-name {{
      font-family: var(--font-mono);
      font-weight: 600;
      color: #79c0ff;
    }}

    .status-badge {{
      font-size: 0.65rem;
      padding: 1px 6px;
      border-radius: 3px;
      font-weight: 700;
    }}
    .status-badge.success {{ background: rgba(63, 185, 80, 0.2); color: #3fb950; }}
    .status-badge.error {{ background: rgba(248, 81, 73, 0.2); color: #f85149; }}

    details.nested-details {{
      margin-top: 0.5rem;
    }}

    details.nested-details summary {{
      font-size: 0.78rem;
      color: var(--text-muted);
      cursor: pointer;
      user-select: none;
    }}

    .code-wrapper {{
      position: relative;
      margin: 0.5rem 0;
    }}

    .copy-btn {{
      position: absolute;
      top: 6px;
      right: 6px;
      background: #21262d;
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 2px 7px;
      font-size: 0.72rem;
      border-radius: 4px;
      cursor: pointer;
      opacity: 0.7;
      transition: all 0.15s ease;
      z-index: 5;
    }}

    .copy-btn:hover {{
      opacity: 1;
      color: #fff;
      background: #30363d;
    }}

    pre {{
      margin: 0;
      padding: 0.85rem;
      background: var(--code-bg);
      color: var(--code-text);
      font-family: var(--font-mono);
      font-size: 0.83rem;
      line-height: 1.45;
      overflow-x: auto;
      border-radius: 6px;
      border: 1px solid var(--border);
    }}

    code {{
      font-family: var(--font-mono);
      font-size: 0.88em;
    }}

    p code, li code {{
      background: rgba(110, 118, 129, 0.2);
      padding: 0.15em 0.35em;
      border-radius: 4px;
      color: #e6edf3;
    }}

    .mono {{ font-family: var(--font-mono); }}
    .meta {{ font-size: 0.75rem; color: var(--text-muted); }}

    /* Offline Syntax Highlighting */
    .tok-kw {{ color: #ff7b72; font-weight: 600; }}
    .tok-str {{ color: #a5d6ff; }}
    .tok-num {{ color: #79c0ff; }}
    .tok-bool {{ color: #ff7b72; font-weight: 600; }}
    .tok-null {{ color: #79c0ff; font-style: italic; }}
    .tok-key {{ color: #7ee787; }}
    .tok-com {{ color: #8b949e; font-style: italic; }}
    .tok-tag {{ color: #7ee787; }}
    .tok-attr {{ color: #79c0ff; }}

    /* Diff lines */
    .diff-add {{ background: rgba(46, 160, 67, 0.15); color: #7ee787; display: block; }}
    .diff-del {{ background: rgba(248, 81, 73, 0.15); color: #ffa198; display: block; }}
    .diff-hunk {{ background: rgba(56, 139, 253, 0.15); color: #79c0ff; display: block; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="header-top">
        <h1><span>💬</span> {page_title}</h1>
        <span class="meta">{timestamp_info}</span>
      </div>
      <div class="metrics-bar">
        <span class="metric-pill">Messages: <strong>{total_messages}</strong></span>
        <span class="metric-pill">Tool Calls: <strong>{total_tool_calls}</strong></span>
        <span class="metric-pill">Tool Outputs: <strong>{total_tool_results}</strong></span>
        {reasoning_pill}
      </div>
    </header>

    <div class="toolbar">
      <div class="btn-group">
        <button class="btn" onclick="toggleAllDetails('details.message')">💬 Toggle Panels</button>
        <button class="btn" onclick="toggleAllDetails('.thinking-block')">💭 Toggle Thinking</button>
        <button class="btn" onclick="toggleAllDetails('.message.role-tool')">⚡ Toggle Outputs</button>
        <button class="btn" onclick="toggleAllDetails('details')">↕️ Expand/Collapse All</button>
      </div>
      <input type="text" class="search-box" placeholder="Filter conversation..." oninput="filterTranscript(this.value)">
    </div>

    {tool_schemas_section}

    <main class="timeline">
      {transcript_html}
    </main>
  </div>

  <script>
    function copyCode(btn) {{
      const pre = btn.nextElementSibling;
      if (!pre) return;
      const text = pre.innerText;
      navigator.clipboard.writeText(text).then(() => {{
        const orig = btn.innerText;
        btn.innerText = 'Copied!';
        setTimeout(() => btn.innerText = orig, 1500);
      }});
    }}

    function toggleAllDetails(selector) {{
      const elements = document.querySelectorAll(selector);
      if (!elements.length) return;
      const anyOpen = Array.from(elements).some(el => el.hasAttribute('open'));
      elements.forEach(el => {{
        if (el.tagName === 'DETAILS') {{
          if (anyOpen) el.removeAttribute('open');
          else el.setAttribute('open', '');
        }} else {{
          el.style.display = anyOpen ? 'none' : '';
        }}
      }});
    }}

    function filterTranscript(term) {{
      const filter = term.toLowerCase().trim();
      const messages = document.querySelectorAll('.timeline .message');
      messages.forEach(msg => {{
        if (!filter) {{
          msg.style.display = '';
          return;
        }}
        const text = msg.innerText.toLowerCase();
        const matches = text.includes(filter);
        msg.style.display = matches ? '' : 'none';
        if (matches) msg.setAttribute('open', '');
      }});
    }}

    function highlightAllCode() {{
      document.querySelectorAll('code[class*="language-"]').forEach(block => {{
        const lang = (block.className.match(/language-(\\w+)/) || [])[1];
        if (!lang) return;

        let code = block.innerHTML;

        if (lang === 'json') {{
          code = code.replace(/"(\\\\u[a-zA-Z0-9]{{4}}|\\\\[^u]|[^\\\\"])*"(\\s*:)?|\\b(true|false|null)\\b|-?\\d+(?:\\.\\d*)?(?:[eE][+\\-]?\\d+)?/g, function (match) {{
            let cls = 'tok-num';
            if (/^"/.test(match)) {{
              cls = /:$/.test(match) ? 'tok-key' : 'tok-str';
            }} else if (/true|false/.test(match)) {{
              cls = 'tok-bool';
            }} else if (/null/.test(match)) {{
              cls = 'tok-null';
            }}
            return '<span class="' + cls + '">' + match + '</span>';
          }});
        }} else if (lang === 'diff') {{
          const lines = block.innerText.split('\\n');
          const styled = lines.map(l => {{
            const esc = l.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            if (l.startsWith('+')) return '<span class="diff-add">' + esc + '</span>';
            if (l.startsWith('-')) return '<span class="diff-del">' + esc + '</span>';
            if (l.startsWith('@@')) return '<span class="diff-hunk">' + esc + '</span>';
            return esc;
          }});
          block.innerHTML = styled.join('\\n');
          return;
        }} else if (lang === 'xml' || lang === 'html') {{
          code = code
            .replace(/(&lt;!--[\\s\\S]*?--&gt;)/g, '<span class="tok-com">$1</span>')
            .replace(/(&lt;\\/?)([a-zA-Z0-9:-]+)/g, '$1<span class="tok-tag">$2</span>')
            .replace(/([a-zA-Z:-]+)(=)(&quot;.*?&quot;|'.*?')/g, '<span class="tok-attr">$1</span>$2<span class="tok-str">$3</span>');
        }} else if (lang === 'python') {{
          code = code
            .replace(/(#.*$)/gm, '<span class="tok-com">$1</span>')
            .replace(/(&quot;[\\s\\S]*?&quot;|'[^']*')/g, '<span class="tok-str">$1</span>')
            .replace(/\\b(def|class|return|if|elif|else|for|while|try|except|finally|with|as|import|from|async|await|pass|raise|break|continue|None|True|False|self)\\b/g, '<span class="tok-kw">$1</span>')
            .replace(/\\b(\\d+)\\b/g, '<span class="tok-num">$1</span>');
        }}

        block.innerHTML = code;
      }});
    }}

    document.addEventListener('DOMContentLoaded', highlightAllCode);
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Main Controller
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert LLM JSON transcript to clean, readable HTML.")
    parser.add_argument("input", type=Path, help="Input JSON file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("transcript.html"),
        help="Destination HTML file (default: transcript.html)",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Error: file '{args.input}' does not exist.", file=sys.stderr)
        sys.exit(1)

    try:
        raw_data = json.loads(args.input.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error parsing JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # 1. Extract Tools and JSON Schemas
    tools = extract_tools(raw_data)
    tool_schemas_html = render_tool_schemas(tools)

    # 2. Parse Messages and Completions
    elements, metrics = parse_events(raw_data)

    reasoning_pill = ""
    if metrics["reasoning_tokens"] > 0:
        reasoning_pill = f'<span class="metric-pill">Thinking Tokens: <strong>{metrics["reasoning_tokens"]}</strong></span>'

    # 3. Assemble Standalone HTML
    rendered_html = HTML_TEMPLATE.format(
        page_title=f"Transcript - {args.input.stem}",
        timestamp_info=f"Source: {escape(args.input.name)}",
        total_messages=metrics["messages"],
        total_tool_calls=metrics["tool_calls"],
        total_tool_results=metrics["tool_results"],
        reasoning_pill=reasoning_pill,
        tool_schemas_section=tool_schemas_html,
        transcript_html="\n".join(elements),
    )

    args.output.write_text(rendered_html, encoding="utf-8")
    print(f"✔ Successfully generated standalone transcript: {args.output.resolve()}")


if __name__ == "__main__":
    main()
