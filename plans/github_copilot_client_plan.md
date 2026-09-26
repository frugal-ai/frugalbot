# GitHub Copilot Client — Implementation Plan

## 1. Goal and Scope

Add a first-class frugalbot LLM client (`CopilotClient`) in
`src/frugalbot/clients/copilot.py`, selectable via `type = "copilot"` in `config.toml`,
that drives the **official** GitHub Copilot SDK (`github-copilot-sdk`, repo
`github/copilot-sdk`) as a *pure LLM transport* while frugalbot keeps ownership of the
agent loop, conversation, tools, hooks, approvals, telemetry, and session persistence.

Decisions taken (from clarification):

| # | Decision |
| --- | --- |
| Q1 | **Design A — pure LLM.** Copilot's built-in tools are excluded; frugalbot's tools are exposed as declaration-only external tools and surfaced back as `tool_calls`. |
| Q2 | The SDK has **no API to inject a whole message array** (see §3), so history is mirrored through a live Copilot session; details in §4. |
| Q3 | Auth: **GitHub token/PAT** read from an env var (`api_key_env_var`, consistent with other clients). |
| Q4 | **Pre-installed runtime required.** At start-up, if the Copilot client is configured/enabled and the runtime is missing, print install instructions and exit. |
| Q5 | Add `github-copilot-sdk` as a **core dependency**. |
| Q6 | Thinking map: `LOW→low`, `MEDIUM→high`, `HIGH→max`. Use `list_models()` for validation. Support `model = "auto"`. |
| Q7 | **Correction:** the SDK *does* expose usage — use `assistant.usage` events + `session.usage.getMetrics()` + `session.usage_info` events (this is what VS Code reads). Map to `CompletionUsage`. |
| Q8 | Moot under Design A; use `PermissionHandler.approve_all` defensively. |
| Q9 | Full parity: `Alt+P` client fallback, session save/load, multi-agent, `--one-shot`, `/resume`, `/thinking`, `/new`, `/reload`. |
| Q10 | Unit tests mock the SDK boundary only; **no smoke test**. |

Out of scope for v1: BYOK custom providers (`provider=`/`providers=`/`models=`), Azure,
in-process FFI transport, MCP servers wired through Copilot, Copilot sub-agents/skills,
and Copilot's own infinite-session compaction (disabled — frugalbot owns context).

## 2. Verified SDK Findings (github-copilot-sdk 1.0.14)

Verified by downloading and inspecting the wheel (`copilot/` package), not just the README.
Version `1.0.14`, `requires-python >=3.11` (project is `>=3.14`), runtime deps
`python-dateutil`, `pydantic>=2`, `httpx`. The heavy part is a downloaded CLI runtime.

- **What it is:** JSON-RPC control of the GitHub Copilot CLI. It runs **sessions**; the
  runtime owns the model conversation for a session.
- **Two configuration levels (verified signature `CopilotClient.__init__`):** the *client*
  constructor takes `mode`, `base_directory`, `github_token`, `working_directory` (for the
  runtime process), `env`, `use_logged_in_user`, `connection`, `log_level`, and
  `on_list_models`. **`create_session` does not accept `mode` or `base_directory`** — it
  reads the client's `self._options.mode`. Session-level options (`model`,
  `reasoning_effort`, `tools`, `system_message`, `available_tools`, `excluded_tools`,
  `streaming`, `infinite_sessions`, `capi`, `on_permission_request`, …) go to
  `create_session`. Do **not** pass `cwd=`; the parameter is `working_directory=`.
- **`mode="empty"`** (`copilot._mode`): an isolation mode that disables environment context,
  custom instructions, skills, file hooks, host git ops, session store, memory, plugins, and
  embedding retrieval. `mode="empty"` **requires** explicit `available_tools` and explicit
  storage (`base_directory`, `session_fs`, or a URI connection) at client construction. This
  is the mechanism that makes Design A possible.
- **`ToolSet`** builds source-qualified tool filters (`builtin:*`, `custom:*`, `mcp:*`).
  `available_tools=ToolSet().add_custom("*")` exposes **only** the custom tools we register
  and hides every built-in from the model.
- **Tools:** low-level `Tool(name, description, parameters, handler, defer=...)` or
  `@define_tool`. A tool with `handler=None` is **declaration-only**; the runtime emits
  `external_tool.requested` and the SDK does *not* auto-respond (verified in
  `CopilotSession._handle_broadcast_event`: it returns early when no handler is found).
  The client resolves it later via `session.rpc.tools.handle_pending_tool_call(...)`.
- **Built-in tool-name collisions:** the runtime rejects a custom tool whose name matches a
  registered built-in unless `overridesBuiltInTool: true` is sent. frugalbot's tool names
  include `bash` and `grep`, which collide. `Tool(..., overrides_built_in_tool=True)` is
  therefore required (harmless for non-colliding names).
- **`handle_pending_tool_call`** takes `HandlePendingToolCallRequest(request_id=...,
  result=ExternalToolTextResultForLlm(text_result_for_llm=..., result_type=...,
  error=..., ...))` (or `error=...`); helper
  `copilot.tools.tool_result_to_external_tool_text_result_for_llm(tool_result)` exists.
- **`external_tool.requested`** payload (`ExternalToolRequestedData`): `request_id`,
  `tool_call_id`, `tool_name`, `arguments`, `provider_id`, `working_directory`.
- **Streaming** (`streaming=True`): `assistant.message_delta` (`delta_content`),
  `assistant.reasoning_delta` (`delta_content`), plus terminal `assistant.message`
  (`content`, `tool_requests: list[AssistantMessageToolRequest]`, `output_tokens`) and
  `assistant.reasoning` (`content`). `assistant.tool_call_delta` also exists.
- **Turn boundary:** `assistant.turn_start` / `assistant.turn_end` and `session.idle`
  (`SessionIdleData`, with `aborted`). **However**, when the model requests external tools
  the turn is *suspended* awaiting tool results and `assistant.turn_end`/`session.idle` are
  **not** emitted until we resolve the pending calls (see §6).
- **Usage (answers Q7):**
  - `assistant.usage` → `AssistantUsageData` with `input_tokens`, `output_tokens`,
    `cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens`, `model`,
    `finish_reason`, `cost` (experimental), `max_prompt_tokens`, quotas.
  - `session.usage_info` → `SessionUsageInfoData` with `current_tokens`, `token_limit`,
    `system_tokens`, `tool_definitions_tokens`, `conversation_tokens`, `messages_length`.
  - `session.usage_checkpoint` → durable aggregate (`total_nano_aiu`).
  - `session.rpc.usage.get_metrics()` → accumulated session metrics (token counts, cost).
- **Models:** `CopilotClient.list_models() -> list[ModelInfo]` where `ModelInfo` has `id`,
  `name`, `capabilities.supports.reasoning_effort`, `capabilities.limits.max_prompt_tokens`,
  `capabilities.limits.max_context_window_tokens`, `supported_reasoning_efforts`,
  `default_reasoning_effort`.
- **`create_session(...)`** relevant kwargs: `model`, `reasoning_effort`
  (`low|medium|high|xhigh|max`), `reasoning_summary`, `tools`, `system_message`,
  `available_tools`, `excluded_tools`, `streaming`, `infinite_sessions`, `provider`,
  `capi` (`auto_tier` for `model="auto"`), `working_directory`, `github_token`,
  `on_permission_request`, `hooks`, `on_event`.
- **`system_message`** supports `{"mode": "replace", "content": ...}` — full control of the
  system prompt (removes SDK guardrails).
- **Lifecycle:** `CopilotClient` is an async context manager; `await client.start()` /
  `await client.stop()`, `__aenter__`/`__aexit__`. `CopilotSession` is also an async CM and
  has `disconnect()`, `abort()`, `set_model(model, reasoning_effort=...)` (history preserved),
  and `get_events()`.
- **No message-array injection:** `session.send(prompt: str)`, and
  `session.rpc.send_messages(SendMessagesRequest(messages=[SendMessageItem(prompt=...)]))`
  accept **user messages only** (no assistant/tool roles). `resume_session()` can only
  resume a runtime-owned session. There is no "here is the full `messages` array" call.
- **Runtime location:** `COPILOT_CLI_PATH` env override; otherwise a pinned runtime is
  cached at `%LOCALAPPDATA%\github-copilot-sdk\cli\<version>\...` (Windows). Install via
  `python -m copilot download-runtime`. `copilot._cli_download.get_cached_cli_path()`
  returns the cached path or `None` without downloading.

## 3. Core Architectural Constraint and Consequence

frugalbot's contract is stateless request/response:

```
Agent._run() ──► LLMClient.call(conversation, tools) -> ChatCompletion
                     ▲                                         │
                     └──── Agent executes tool_calls ◄──────────┘
```

The Copilot SDK is a stateful runtime: it owns the conversation for a session, and only
accepts *new user messages* or *pending tool-call resolutions* — never an arbitrary message
array. Therefore a literal `call(messages)` mapping is impossible. The consequence is that
the client must **mirror** frugalbot's conversation into a live Copilot session
incrementally (§4) while keeping frugalbot's `Conversation` as the canonical record for
display, persistence, cost, and status. This is the same pattern already used by the
`manual` client, which is also stateful (`self._initialized`) and only sends deltas.

## 4. Conversation ↔ Session Model

```
frugalbot Conversation (canonical: display / save / cost)  ◄──── mirrored ────┐
   system, user, assistant(completion), tool, ...                             │
                                                                              │
CopilotClient (frugalbot)                                                     │
   ├─ WeakKeyDictionary[Conversation, _SessionState]                          │
   └─ single CopilotClient (SDK)  ── creates ──►  CopilotSession per Conversation
                                                   ├─ system_message = frugalbot prompt (replace)
                                                   ├─ tools = declaration-only frugalbot tools
                                                   ├─ available_tools = ToolSet().add_custom("*")
                                                   ├─ mode = "empty", infinite_sessions disabled
                                                   ├─ streaming = True
                                                   └─ reasoning_effort from thinking_level
```

### `_SessionState` per conversation

- `session: CopilotSession | None`
- `events: asyncio.Queue[SessionEvent]` and the `unsubscribe` handle from `session.on(...)`
  — a **long-lived** listener bound to the state (not a per-`call()` queue; see §6)
- `delivered_count: int` — high-water mark into `conversation.entries`
- `pending_tool_requests: dict[str, PendingToolRequest]` — keyed by `tool_call_id`,
  holding the SDK `request_id` and tool name
- `applied_reasoning_effort: str | None` and `applied_model: str` — what the live session
  currently has (used to reconcile mid-conversation changes)

### Lifecycle

- **Create:** first `call()` for a conversation lazily `await sdk_client.start()`s and creates
  the SDK session (client-level `mode="empty"`/`base_directory` come from the SDK client
  constructor — see §6), with the rendered system prompt, the configured model, the mapped
  reasoning effort, and `available_tools=ToolSet().add_custom("*")`.
- **Reuse:** subsequent `call()`s reuse the session and only deliver new entries.
- **New conversation (`/new`)** replaces `agent.conversation`, so the state is keyed by a
  new object; the old session is disconnected via a `weakref.finalize(conversation, ...)`
  callback (plus deterministic cleanup on close, §10).
- **Reload (`/reload`)** recreates clients; see §10 for explicit cleanup.
- **Thinking change (`/thinking`):** `LLMClient.thinking_level` is a **synchronous** property
  and `Agent.set_thinking_level` assigns it without awaiting (verified in
  `agent.py`/`agents.py`), so `call()` must reconcile lazily: at the start of each `call()`,
  if `state.session` exists and the desired effort differs from `state.applied_reasoning_effort`,
  `await session.set_model(self.model, reasoning_effort=<desired>)` (history is preserved).
  Do **not** attempt to `await` from the property setter.
- **Client switch (`Alt+P`) onto Copilot mid-conversation:** the conversation has no
  `_SessionState`, so history restoration applies (§5).
- **Model switch within the client** is not exposed by the UI (provider cycling swaps the
  whole client); `set_model` remains the documented path if it is added.

### Incremental delivery algorithm (`call`)

1. Resolve/create `_SessionState`; lazily `await sdk_client.start()`, create the session if
   needed, and register the long-lived event listener (§6).
2. Reconcile reasoning effort (above) and, if the model changed, `set_model`.
3. `new_entries = conversation.entries[delivered_count:]`.
4. Delivery, in order:
   - **Pending tool results:** for each new `role="tool"` entry whose `tool_call_id` is in
     `pending_tool_requests`, call `session.rpc.tools.handle_pending_tool_call(request_id,
     result=tool_result_to_external_tool_text_result_for_llm(ToolResult(
     text_result_for_llm=content, result_type=...)))`. Then remove from `pending_tool_requests`.
   - **New user messages:** `session.send(prompt)` (or `send_messages` batch when several).
   - **No new entries:** `send_messages(messages=[])` — the SDK runs one turn over existing
     history (this is exactly `/resume` semantics).
   - **Out-of-band history (i.e. `/load`, or a session created for an already-populated
     conversation):** see §5.
5. Drain stale queued events, then stream/collect until the turn-exit condition (§6). Return
   a normalized `ChatCompletion`.
6. Set `delivered_count = len(conversation.entries)`.

## 5. History Restoration (`/load` and `Alt+P`)

The SDK cannot ingest assistant/tool history, and `session.send(prompt)` **initiates a model
turn** — so the earlier idea of sending the transcript as a prompt would generate an
unwanted response before the user's real turn. Correct behaviour: when creating a session for
a conversation that already contains more than the system prompt, inject a rendered
transcript of the prior turns into the **system message** at creation time:

```python
full_system_prompt = system_prompt
if restored_transcript:
    full_system_prompt += f"\n\n## Restored Conversation Context\n(Prior turns restored from a frugalbot session; treat as conversation history.)\n{restored_transcript}"
```

- Render with `Conversation.convert_into_web_chat_prompt()` (or a dedicated helper) and apply
  a token/size cap with a clear truncation notice.
- This triggers no model turn, keeps the live session clean, and guarantees the model sees
  prior context on turn 1.
- When a real new user message accompanies the same `call()` (the `Alt+P` case), that message
  still goes through the normal `send(...)` path after restoration.
- The alternative — `session.rpc.send_messages([SendMessageItem(transcript),
  SendMessageItem(user_prompt)])`, whose contract treats preceding messages as context and
  only the final message as the turn origin — can only carry *user-role* text and therefore
  cannot represent prior assistant/tool turns; it is a documented fallback, not the default.
- This is a best-effort degradation; it never fabricates assistant/tool structure that the
  SDK cannot represent.

## 6. Request Construction and Event Handling

### SDK client construction (client-level options)

```python
self._sdk_client = CopilotClient(
    mode="empty",  # isolation; requires base_directory
    base_directory=self.config.base_directory or str(Path.home() / ".frugalbot" / "copilot"),
    github_token=github_token,  # from api_key_env_var
    working_directory=str(Path.cwd()),  # NOT cwd=
)
```

`await self._sdk_client.start()` happens lazily on the first `call()`.

### Session creation (session-level options)

```python
session = await self._sdk_client.create_session(
    model=self.model,
    reasoning_effort=mapped_effort,  # omitted when thinking_level == "NONE" or model == "auto"
    reasoning_summary="none" if not reasoning else None,
    tools=[
        Tool(
            name=schema["name"],
            description=schema["description"],
            parameters=schema["parameters"],
            handler=None,  # declaration-only -> external_tool.requested
            defer="never",  # keep preloaded; avoid tool-search deferral
            overrides_built_in_tool=True,  # required for bash/grep; harmless otherwise
        )
        for schema in (tool.get_schema()["function"] for tool in tools.get_all())
    ],
    system_message={"mode": "replace", "content": full_system_prompt},
    available_tools=ToolSet().add_custom("*"),  # only our custom tools are visible
    streaming=True,
    infinite_sessions={"enabled": False},
    capi={"auto_tier": self.config.auto_tier} if self.model == "auto" and self.config.auto_tier else None,
    on_permission_request=PermissionHandler.approve_all,  # defensive; built-ins are excluded
    # enable_session_telemetry=True,  # only if usage events prove absent under mode="empty"
)
```

- `excluded_tools` is not needed when `available_tools` is set (it takes precedence).
- `working_directory` for the session is left to default (the process cwd is set on the
  client constructor).
- `github_token` is passed on the **client**, not `create_session`.
- `defer="never"` keeps every frugalbot tool preloaded (avoids tool-search deferral hiding
  tools in `mode="empty"`).
- `Tool.parameters` uses `tool.get_schema()["function"]["parameters"]`; `name`/`description`
  come from the same schema. Tool names already match `^[a-zA-Z0-9_-]+$`.
- `mode="empty"` + `available_tools=ToolSet().add_custom("*")` guarantees no built-in tool
  (`bash`, `edit_file`, `read_file`, …) is ever offered, so permission prompts are moot.

### Event listener and turn-exit condition

- **Long-lived listener.** `session.on(handler)` is registered **once** per session when the
  session is created, and the handler pushes every `SessionEvent` into the state's
  `events` queue. It must **not** be a queue created inside `call()` and discarded on return,
  or events emitted while frugalbot executes tools (`Agent._handle_tool_calls`) would be
  lost. At the start of each `call()`, drain any stale queued events; the listener is
  unsubscribed only when the session is disconnected.
- **Turn exit on tool calls (critical).** When the model requests external tools, the runtime
  **suspends** the turn awaiting `handle_pending_tool_call` and does *not* emit
  `assistant.turn_end` or `session.idle`. `call()` must therefore return as soon as
  **all** `external_tool.requested` events matching `assistant.message.tool_requests`
  (by `tool_call_id`) have been collected, with `finish_reason="tool_calls"`. Waiting for
  `turn_end`/`session.idle` would deadlock.
- **Text turn exit:** for a non-tool turn, exit on `assistant.turn_end` (or `session.idle` as
  a fallback). Treat `session.idle` with `aborted=True` as a cancellation/abort signal.

| Event | Behaviour |
| --- | --- |
| `assistant.message_delta` | Append to content; emit `MessageEvent(delta, ASSISTANT, MARKDOWN, is_stream=True)`; set `streamed_content=True`; mark output emitted |
| `assistant.reasoning_delta` | Append to reasoning; emit `MessageEvent(delta, THINKING, MARKDOWN, is_stream=True)`; set `streamed_reasoning=True`; mark output emitted |
| `assistant.message` | Terminal content. Emit once **only if `not streamed_content`** (dedupe deltas vs. snapshot); capture `tool_requests`, `output_tokens`, message id |
| `assistant.reasoning` | Terminal reasoning. Emit once **only if `not streamed_reasoning`** |
| `assistant.usage` | Map to `CompletionUsage` (§7) |
| `external_tool.requested` | Record `{tool_call_id: request_id, name}`; emit `MessageType.TOOL_CALL` (name + YAML args); check turn-exit condition |
| `session.usage_info` | Cache context-window stats (§7) |
| `assistant.turn_end` | Text-turn finished |
| `session.idle` | Session quiescent (respect `aborted`) |
| `assistant.turn_retry` | Optional warning event |
| error / `session.error` | Raise after closing fences |

Finish-reason policy: any surfaced tool call → `"tool_calls"`; otherwise `"stop"`;
a `content_filter`/length signal → mapped accordingly. If the model emits `tool_requests`,
wait until the matching `external_tool.requested` events have arrived (matched by
`tool_call_id`) before returning, so parallel tool calls are surfaced together. The exact
event ordering between `assistant.message` and `external_tool.requested` must be confirmed
against the real runtime during implementation (tests encode whichever order the SDK
guarantees).

### Normalized result

Build `ChatCompletion(id=<turn/message id>, created=now, model=self.model,
object="chat.completion", choices=[Choice(index=0, finish_reason=..., message=
ChatCompletionMessage(role="assistant", content=..., reasoning=Reasoning(content=...), 
tool_calls=[ChatCompletionMessageFunctionToolCall(id=<tool_call_id>,
function=Function(name=..., arguments=json.dumps(arguments)), type="function")]))])`.

Tool-call `id` **must be the SDK `tool_call_id`** so `ToolCaller` appends a `role="tool"`
message whose `tool_call_id` matches the pending request on the next `call()`.

## 7. Usage, Cost, and Status (answers Q7)

Map `assistant.usage` (`AssistantUsageData`) into `CompletionUsage`:

```python
CompletionUsage(
    prompt_tokens=usage.input_tokens or 0,
    completion_tokens=usage.output_tokens or 0,
    total_tokens=(usage.input_tokens or 0) + (usage.output_tokens or 0),
    completion_tokens_details=CompletionTokensDetails(reasoning_tokens=usage.reasoning_tokens),
    prompt_tokens_details=PromptTokensDetails(cached_tokens=usage.cache_read_tokens),
)
```

- If no `assistant.usage` event arrives, fall back to `assistant.message.output_tokens` for
  completion tokens and a cached `session.usage_info.current_tokens` for prompt tokens; if
  still unknown, `usage=None` (matching other clients).
- Cost: `ConversationCostCalculator` derives cost from models.dev/OpenRouter pricing using
  `provider`/`model` and token counts. Set `provider = "github-copilot"` and
  `base_url = "https://api.githubcopilot.com"` so `get_provider_by_url`/`get_model` can
  resolve when models.dev has a matching entry; otherwise cost degrades to `0.0` exactly as
  with unknown models today. The SDK's experimental `AssistantUsageData.cost` is captured
  for diagnostics but is not currently part of frugalbot's cost pipeline.
- Context window: `session.usage_info.token_limit` and `current_tokens` are captured. The
  status bar's context size still comes from models.dev (`Agent._emit_status_update`); no
  agent change is planned. If models.dev lacks `github-copilot`, context size shows as
  unknown, consistent with other unknown models.

> **Verify:** `mode="empty"` defaults session telemetry to off. If `assistant.usage` events
> turn out to be suppressed by that, pass `enable_session_telemetry=True` explicitly (empty
> mode lets caller values win) rather than abandoning usage accounting.

### Model capability caching (`supports_thinking`)

`LLMClient.supports_thinking` is a **synchronous property** and cannot `await
list_models()`. Cache the capability once per session: `self._supports_thinking: bool = True`
by default, refreshed from `ModelInfo.capabilities.supports.reasoning_effort` (matched by
`model`, or `default_reasoning_effort`/`supported_reasoning_efforts` for `"auto"`) when the
model list is fetched during `call()`. `list_models()` is also the validation source for
the thinking-level mapping (§8). (Note: `supports_thinking` currently has no consumer in
frugalbot, but it must remain correct for API consistency.)

## 8. Configuration and Template

```toml
[clients.copilot]
type = "copilot"
model = "gpt-5"                              # or "auto"
api_key_env_var = "COPILOT_GITHUB_TOKEN"     # env var holding a GitHub token/PAT
# Optional:
# output_traceback_on_error = false
# cli_path = "C:\\path\\to\\copilot-runtime"  # pre-installed runtime; else COPILOT_CLI_PATH
# base_directory = "~/.frugalbot/copilot"     # SDK state; required by mode="empty"
# auto_tier = "balance"                        # only with model = "auto"
# reasoning_effort = "high"                    # explicit override of the thinking-level map
```

`CopilotClientConfig(LLMClientConfig)`: `model: str`, `api_key_env_var: str`,
`output_traceback_on_error: bool = False`, `cli_path: str | None = None`,
`base_directory: str | None = None`,
`auto_tier: Literal["efficiency","balance","intelligence","fast"] | None = None`.
`reasoning_effort` override is optional (may be omitted to keep the mapping authoritative).

### Thinking-level mapping and validation (answers Q6/Q5)

| `thinking_level` | `reasoning_effort` |
| --- | --- |
| `NONE` | omit the parameter (and set `reasoning_summary="none"`) |
| `LOW` | `low` |
| `MEDIUM` | `high` |
| `HIGH` | `max` |

- Fetch `list_models()` once (cached) and validate the mapped effort against the selected
  model's `supported_reasoning_efforts` (and `capabilities.supports.reasoning_effort`).
- **Clamp and warn** (do not raise): if the mapped effort is unsupported, pick the nearest
  supported level and emit a `MessageType.WARNING` event. Rationale: the default
  `thinking_level = "HIGH"` maps to `max`, and many models cap at `high`; raising would break
  default setups.
- If the configured model is not in `list_models()` at all, raise `LLMClientError` with the
  available model ids.
- `model = "auto"`: skip effort validation and pass `capi={"auto_tier": ...}` (when
  configured); omit `reasoning_effort`.

`config_template.toml` gains a commented opt-in block plus guidance: how to install the
runtime, that the model must be one offered by Copilot, and how to map thinking levels.

## 9. Start-up Runtime Preflight (answers Q4)

A module helper `ensure_copilot_runtime(config) -> str | None` returns the runtime path or
raises `LLMClientError` with install instructions. Resolution order:

1. `config.cli_path` (must exist).
2. `COPILOT_CLI_PATH` env var (must exist).
3. `shutil.which("copilot-runtime")` and `shutil.which("copilot")` on `PATH` (covers npm,
   Homebrew, or `gh extension install github/gh-copilot` installs).
4. `copilot._cli_download.get_cached_cli_path()` (guarded import; `None` when absent).

`CopilotClient.__init__` calls it. On failure it raises `LLMClientError` with instructions
such as:

```
The GitHub Copilot runtime is not installed.
Install it with:  python -m copilot download-runtime
or set COPILOT_CLI_PATH / clients.copilot.cli_path to an existing runtime.
```

`app.py::_app_init` catches `LLMClientError`, prints the message with the Rich console, and
raises `typer.Exit(code=1)` (clean message, no traceback). Auto-download is intentionally
**not** triggered (`COPILOT_SKIP_CLI_DOWNLOAD=1` is set defensively so the SDK cannot
silently fetch a runtime).

Also emit a `MessageType.WARNING` if the resolved runtime is outside the SDK's pinned cache
version, since protocol drift is possible.

## 10. Error, Retry, Cancellation, and Cleanup

- **Retry:** Copilot's runtime already retries internally. Wrap only session creation and
  the initial `send`/`handle_pending_tool_call` in a small Tenacity retry that stops once
  any output has been emitted to the bus (mirror the `anyllm_responses` policy). Never retry
  `asyncio.CancelledError` or auth/config errors.
- **Cancellation (`Ctrl+A`):** catch `asyncio.CancelledError`, call `await session.abort()`,
  close any open tool-call fence, then re-raise. Reset `_SessionState` bookkeeping so the
  next `call()` does not try to resolve stale pending requests.
- **Errors:** raise `LLMClientError` with actionable text; never fabricate a successful
  completion for a failed/incomplete turn.
- **Cleanup:** add `async def close(self) -> None: ...` (default no-op) to `LLMClient`, and
  an `async def aclose(self) -> None` to `LLMClients` that awaits each client's `close()`.
  `Agents.reload()` awaits `clients.aclose()` before `clients.unload()`. `app.py` must also
  close clients on shutdown — `tui.run()` currently returns without shutting anything down,
  leaving the spawned Copilot CLI process orphaned:

  ```python
  try:
      msg = tui.run(loop=loop)
  finally:
      if tui.agents and tui.agents.clients:
          loop.run_until_complete(tui.agents.clients.aclose())
  ```

  `CopilotClient.close()` disconnects all live sessions, finalizes the weak-ref states, and
  `await sdk_client.stop()`. It must be idempotent and safe to call when never started.

## 11. Changes to Shared Code

| Area | Change | Rationale |
| --- | --- | --- |
| `src/frugalbot/clients/base.py` | Add `async def close(self) -> None` (no-op) and `LLMClients.aclose()` | Transport-holding client needs deterministic shutdown |
| `src/frugalbot/agents.py` | `reload()` awaits `clients.aclose()` | Cleanup on `/reload` |
| `src/frugalbot/app.py` | Catch `LLMClientError` from `Agents.load`, print + exit; `finally: close clients` after `tui.run()` | Q4 behaviour + stop orphaned CLI processes |
| `src/frugalbot/config_template.toml` | Commented `[clients.copilot]` example | Discoverability |
| `README.md` | Document client, prerequisites, auth, limitations | Docs |
| `pyproject.toml`, `uv.lock` | Add `github-copilot-sdk` core dependency | Q5 |

No changes to the generic loader, agent loop, or tool execution are expected.

## 12. Test Plan

Follow `docs/testing_guidelines.md`: GWT, one entry/exit point, strict typing, 100% coverage
of new code, all SDK interaction mocked (no runtime, no CLI process, no network). Introduce a
single injection seam (`_create_sdk_client()` / constructor-injectable SDK client) so tests
substitute a fake `CopilotClient`/`CopilotSession`; use real `copilot` event dataclasses as
fixtures where practical.

### `tests/frugalbot/clients/test_copilot.py` (new)

1. `test_init_with_valid_config_sets_provider_model_and_base_url`
2. `test_init_with_missing_runtime_raises_client_error_with_instructions`
3. `test_init_when_runtime_on_path_resolves_without_download`
4. `test_call_when_thinking_level_none_omits_reasoning_effort`
5. `test_call_maps_thinking_levels_low_medium_high_to_low_high_max` (parametrized)
6. `test_call_when_model_unsupported_by_list_models_raises_client_error`
7. `test_call_when_mapped_effort_unsupported_clamps_and_warns`
8. `test_call_when_model_is_auto_skips_effort_and_passes_auto_tier`
9. `test_call_creates_sdk_client_with_empty_mode_and_session_with_replace_prompt`
10. `test_call_converts_frugalbot_tools_to_declaration_only_copilot_tools`
11. `test_call_sets_overrides_built_in_tool_true_on_all_registered_tools`
12. `test_call_registers_long_lived_event_listener_bound_to_session_state`
13. `test_call_with_text_stream_emits_assistant_events_and_returns_stop_completion`
14. `test_call_with_reasoning_stream_emits_thinking_events`
15. `test_call_with_final_message_emits_content_once_when_not_streamed` and
    `test_call_with_delta_then_final_does_not_duplicate_content` (delta/snapshot dedupe)
16. `test_call_with_tool_request_returns_tool_calls_without_waiting_for_turn_end`
17. `test_call_with_parallel_tool_requests_surfaces_all_of_them`
18. `test_call_delivers_tool_result_via_handle_pending_tool_call`
19. `test_call_with_no_new_entries_sends_empty_message_batch` (`/resume`)
20. `test_call_after_new_conversation_creates_new_session`
21. `test_call_with_loaded_conversation_injects_transcript_into_system_message`
22. `test_call_when_switching_client_mid_conversation_restores_prior_turns`
23. `test_call_when_thinking_level_changed_applies_set_model_on_next_call`
24. `test_call_maps_assistant_usage_to_completion_usage` (tokens, cached, reasoning)
25. `test_call_with_failed_turn_raises_client_error`
26. `test_call_when_cancelled_aborts_session_and_propagates`
27. `test_close_disconnects_sessions_is_idempotent_and_stops_sdk_client`
28. `test_supports_thinking_returns_cached_capability_without_await`

### Integration/regression

- `tests/frugalbot/clients/test_clients_base.py` — discovery via `type = "copilot"`,
  coexistence/ordering with other clients, named configs, unload/reload without duplicates.
- `tests/frugalbot/test_agents.py` — `aclose()` called on `reload()`.
- `tests/frugalbot/test_app.py` — `LLMClientError` during load prints and exits non-zero.
- `tests/frugalbot/test_agent.py` — full loop: tool request → tool result → next request
  through a fake SDK; two agents sharing one client must not leak session state.
- `tests/frugalbot/test_config.py` — template containing `[clients.copilot]` parses.

## 13. Resolved Decisions (review feedback applied)

All items below are settled; the plan above reflects them.

1. **Session-backed mirror (Q2 re-framed). Resolved: accept.** The SDK cannot accept a full
   message array, so frugalbot's conversation is mirrored into one live Copilot session per
   conversation via incremental sends + pending-tool RPCs, with `Conversation` canonical.
   A fresh-session-per-call alternative is fragile and token-expensive.
2. **History restoration (`/load` and `Alt+P`). Resolved: inject into `system_message`** at
   session creation (never `session.send()`, which would start a spurious turn). See §5.
3. **Cleanup hook. Resolved: accept.** Add `LLMClient.close()` (no-op) + `LLMClients.aclose()`,
   wire into `Agents.reload()` and `app.py` shutdown; deterministic, no orphaned CLI processes.
4. **Config key. Resolved: reuse `api_key_env_var`** for the GitHub PAT (consistent with
   `google`/`anyllm`; required for `write_default()` to populate `.env`).
5. **Unsupported reasoning effort. Resolved: clamp and warn** (do not raise), because the
   default `thinking_level = "HIGH"` maps to `max` and many models cap at `high`.
6. **`model = "auto"`. Resolved: accept.** Pass `capi={"auto_tier": ...}` and skip effort
   validation/`reasoning_effort` for `"auto"`.

### Corrections folded in from review

| Review item | Verdict | Plan change |
| --- | --- | --- |
| `mode`/`base_directory` on `create_session` | **Correct** | Moved to `CopilotClient.__init__` (§6) |
| `overrides_built_in_tool=True` needed | **Correct** | Added to all tool defs (§2, §6) |
| `/load` via `session.send()` triggers a turn | **Correct** | Injected via `system_message` (§5) |
| `supports_thinking` cannot await | **Correct** | Cached capability (§7) |
| `thinking_level` setter cannot await | **Correct** | Reconciled lazily in `call()` (§4) |
| Turn exit on tool requests | **Correct** | Explicit exit condition, no `turn_end` wait (§6) |
| Long-lived event listener | **Correct** | Bound to `_SessionState` (§4, §6) |
| Client cycling (`Alt+P`) restoration | **Correct** | Covered by §5 |
| App shutdown cleanup | **Correct** | `finally` around `tui.run()` (§10, §11) |
| `shutil.which("copilot")` fallback | **Correct** (+ `copilot-runtime`) | Added (§9) |
| `cwd=str(Path.cwd())` | **Incorrect** | Parameter is `working_directory=` (§2, §6) |

## 14. Acceptance Criteria

1. `LLMClients().load({"test": {"type": "copilot", "model": "gpt-5",
   "api_key_env_var": "COPILOT_GITHUB_TOKEN"}})` registers `CopilotClient` without a live
   runtime (SDK mocked).
2. With the runtime absent and the client configured, start-up prints install instructions
   and exits non-zero. A runtime on `PATH`, `COPILOT_CLI_PATH`, or the SDK cache resolves
   without triggering a download.
3. A streamed text turn emits `MessageType.ASSISTANT`; reasoning emits
   `MessageType.THINKING`; deltas are never duplicated by the terminal message.
4. A tool turn returns normalized `tool_calls` whose ids match the runtime
   `tool_call_id`s **without waiting for `turn_end`/`session.idle`**, and the following tool
   result is delivered back via `handle_pending_tool_call`.
5. `assistant.usage` populates `CompletionUsage` (prompt/completion/total, cached, reasoning).
6. Pre-existing history (`/load`, `Alt+P` mid-conversation) is restored via the system
   message and never triggers a spurious model turn.
7. `/thinking` takes effect on the next `call()` via `set_model(reasoning_effort=...)`;
   `supports_thinking` is served from cache without awaiting.
8. `provider`, `model`, `base_url`, and `thinking_level` behave consistently with the other
   clients; `/new`, `/resume`, `/thinking`, `/reload`, `Alt+P`, multi-agent, and `--one-shot`
   work; client shutdown leaves no orphaned CLI process.
9. No regressions in existing clients; all quality gates pass:
   `uv run ruff format` → `uv run ruff check --fix` → `uv run pyright` → `uv run pytest -q`.
