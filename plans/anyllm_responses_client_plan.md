# Any-LLM Responses Client — Implementation Plan

## 1. Goal and Scope

Add an opt-in `AnyLLMResponsesClient` that invokes `any-llm-sdk`'s Responses API (`aresponses`) instead of its Chat Completions API (`acompletion`). Keep `AnyLLMClient` and `type = "anyllm"` completely unchanged.

The new client must return a normalized `ChatCompletion` from `call(...) -> ChatCompletion` so that `Agent`, `Conversation`, `ToolCaller`, `ConversationCostCalculator`, and the Textual TUI operate without architectural changes. This document is a plan only; implementation is a separate task.

### Scope boundaries

- **In scope:** streamed assistant output, reasoning summaries (rendered via `MessageType.THINKING`), local and MCP function calls, token usage and cost accounting, stateless multi-turn replay that preserves encrypted reasoning, and durable session persistence.
- **Out of scope:** background responses, server-side conversation storage (`store=True`), server-side compaction/context management, hosted remote tools, a Responses-native conversation model, or any wholesale migration of existing clients.
- **Explicit rejection over silent loss:** unsupported semantic output (failed or unusable responses, incomplete function arguments) must raise/emit actionable errors, never be silently dropped or fabricated as success.

## 2. Verified Architecture and SDK Findings

Confirmed against the installed `any-llm-sdk` and `openai` packages (source under `.venv/Lib/site-packages/any_llm` and `.../openai/types/responses`):

- `AnyLLM.create(provider=..., api_key=..., api_base=...)` returns a provider instance exposing `SUPPORTS_RESPONSES: bool` and `await provider.aresponses(model=..., input_data=..., *, tools, stream, store, include, reasoning, extra_body, ...)`.
- `aresponses(input_data=...)` accepts `str | list[dict[str, Any]]` and passes item dicts through **without schema validation**, so provider reasoning/output items can be replayed verbatim in a stateless conversation.
- `any_llm.tools._flatten_responses_tool` privately flattens chat-format tools (`{"type": "function", "function": {...}}` → `{"type": "function", ...}`) but **does not set `strict`**. We must not call the private helper; we must control `strict` ourselves.
- Streaming returns `AsyncIterator[any_llm.types.responses.ResponseStreamEvent]`, an alias of `openai.types.responses.ResponseStreamEvent`. The event `type` strings used below are identical to the OpenResponses (`openresponses_types`) events for the cases we care about, so dispatch on the string `type` rather than on Python class identity.
- `ResponseUsage` fields are `input_tokens`, `input_tokens_details` (`cached_tokens`, `cache_write_tokens`), `output_tokens`, `output_tokens_details` (`reasoning_tokens`), `total_tokens` — **plural `tokens` in the detail names**, unlike the Chat Completions `prompt_tokens_details`/`completion_tokens_details`.
- **Correction to earlier assumptions:** `any_llm.types.completion.ChatCompletion` is a pydantic model with `model_config = {"extra": "allow"}` (not `extra="ignore"`), so a namespaced attribute set on a completion instance survives `model_dump()` → `model_validate()`. We still do **not** rely on this for persistence (see §4): the durable representation is explicit typed metadata on `Conversation`, and the extra attribute is only a transport bridge from `call()` to `append_assistant_message`.
- `Conversation` persists completions through `ChatCompletion.model_validate(item["data"])`; any pointer-based metadata must therefore be stored as an explicit entry field, not as an opaque in-memory subclass.
- `LLMClient.call(...) -> ChatCompletion` is consumed by `Agent._run` (`agent.py`) and mocked broadly in `tests/frugalbot/test_agent.py`; changing its return shape would be a large, needless contract break.

## 3. Architecture and Data Contracts

```
                       ┌────────────────────────────┐
                       │        Agent Loop          │
                       └─────────────┬──────────────┘
                                     │ call(conversation, tools) -> ChatCompletion
                                     ▼
                       ┌────────────────────────────┐
                       │  AnyLLMResponsesClient     │
                       └──────┬───────────────▲─────┘
        1. Adapt history      │               │ 4. Accumulate & normalize
                              ▼               │    to ChatCompletion (+ replay envelope
┌───────────────────────────────────────┐     │    attached as namespaced extra attr)
│       Conversation Adapter            │     │
│ - Native Replay: matching origin      │     │
│ - Fallback: normalized ChatCompletion │     │
└─────────────────────┬─────────────────┘     │
                      │ input_data            │
                      ▼                       │
┌─────────────────────────────────────────────┴─┐
│     any_llm Provider (aresponses Stream)      │
│  events: output_text, reasoning summaries,    │
│          function_call arguments, completed   │
└───────────────────────────────────────────────┘
```

### Component hierarchy

- **Module:** `src/frugalbot/clients/anyllm_responses.py`
- **Config class:** `AnyLLMResponsesConfig(LLMClientConfig)`
- **Client class:** `AnyLLMResponsesClient(LLMClient[AnyLLMResponsesConfig])` with a concretely annotated constructor so dynamic loading infers the config type.
- **Config type string:** `anyllmresponses` (the loader lowercases the class name and strips the `client` suffix: `AnyLLMResponsesClient` → `anyllmresponses`).

### Replay envelope schema

Stored under the entry metadata key `"responses_replay"`:

```python
class ResponsesOrigin(BaseModel):
    provider: str  # models.dev provider id, i.e. client.provider
    model: str
    base_url: str  # client.base_url ("" when unset)


class ResponsesReplayEnvelope(BaseModel):
    version: int = 1
    origin: ResponsesOrigin
    output_items: list[dict[str, Any]]
```

The envelope stores only output item dicts and non-secret origin identity. It must never contain API keys, headers, or credentials, and `encrypted_content` inside items must be treated as opaque bytes that are never rendered.

## 4. Conversation and Replay-Metadata Persistence

Native Responses items (item ids, output ordering, and encrypted reasoning) are required for a faithful next tool turn. Because `ChatCompletion.model_validate` is the loader's boundary and we will not depend on SDK extras for storage, `Conversation` gains explicit typed metadata support.

### `src/frugalbot/conversation.py` changes

1. **Type aliases and storage**

   ```python
   CompletionEntry = tuple[str, ChatCompletion, dict[str, Any] | None]
   MessageEntry = dict[str, Any]
   ConversationEntry = MessageEntry | CompletionEntry
   ```

   `_messages: list[ConversationEntry]`. Assistant entries are always appended as 3-tuples; accessors still index `[1]`, so `messages`, `latest_assistant_message()`, and `get_usage()` are unchanged.

2. **Append (default `metadata=None` keeps `Agent._run` and existing callers unchanged)**

   ```python
   def append_assistant_message(
       self,
       provider: str,
       completion: ChatCompletion,
       metadata: dict[str, Any] | None = None,
   ) -> None:
       if metadata is None:
           metadata = clear_responses_replay(completion)  # extract + remove transport attr
       self._messages.append((provider, completion, metadata))
   ```

3. **Serialization** — persist `metadata` alongside `data` when present, and never double-store the transport attribute:

   ```python
   if isinstance(entry, tuple):
       provider, completion = entry[0], entry[1]
       metadata = entry[2] if len(entry) > 2 else None
       serialized = {"type": "completion", "provider": provider, "data": completion.model_dump()}
       serialized["data"].pop(RESPONSES_REPLAY_ATTR, None)  # defensive; append() already clears it
       if metadata:
           serialized["metadata"] = metadata
       ... existing tool_call extra_content merge ...
   ```

4. **Deserialization** — read `item.get("metadata")` and append a 3-tuple. Tolerate legacy 2-tuples (`len(entry) == 2`) and legacy files without metadata.

5. **Compatibility invariants** — existing tests assert `entry[0]`, `entry[1] is completion`, `isinstance(entry, tuple)`, and `ConversationCostCalculator` reads top-level `provider`/`data`; all continue to hold. `tests/frugalbot/test_agent.py` injects a 2-tuple into `_messages`; serialization must therefore handle 2-tuples (covered above) or that fixture is updated alongside.

### Transport bridge from `call()` to `Conversation`

`call()` must return a bare `ChatCompletion`, but the envelope is created inside the client. Bridge with one namespaced extra attribute:

```python
RESPONSES_REPLAY_ATTR = "frugalbot_responses_replay"


def attach_responses_replay(completion: ChatCompletion, envelope: ResponsesReplayEnvelope) -> None:
    setattr(completion, RESPONSES_REPLAY_ATTR, envelope.model_dump())


def clear_responses_replay(completion: ChatCompletion) -> dict[str, Any] | None:
    metadata = getattr(completion, RESPONSES_REPLAY_ATTR, None)
    if metadata is not None:
        delattr(completion, RESPONSES_REPLAY_ATTR)
    return metadata
```

- Relies on the verified `extra="allow"` behavior only as an in-process transport, and removes the attribute at append time so serialized `data` stays clean and SDK-version-independent.
- If a future SDK rejects the extra attribute, `setattr` can be replaced with `AnyLLMResponsesClient`-local storage keyed by `id(completion)` with no change to consumers; this is a fallback, not the primary design.
- Metadata is never placed on `ChatCompletionMessage`, so `conversation.messages` cannot leak Responses-only fields into chat clients.

## 5. Conversation-to-Responses Adapter

Define a pure function `convert_conversation_for_responses(conversation, client) -> list[dict[str, Any]]` that reads `conversation.entries` (so it can see per-entry metadata and provider) and returns a fresh list without mutating the conversation.

```
Input history entry                              Responses API input item
───────────────────                              ────────────────────────
System message (role: system)       ──────►  {"type": "message", "role": "system", "content": [{"type": "input_text", "text": ...}]}
User message (role: user)           ──────►  {"type": "message", "role": "user", "content": [{"type": "input_text", "text": ...}]}
Assistant, compatible native replay ──────►  replay envelope.output_items verbatim (reasoning, function_call, message, ids)
Assistant, fallback / foreign origin ─────►  content -> {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": ...}]}
                                              tool_calls -> one {"type": "function_call", "call_id": id, "name": name, "arguments": args} each
Tool result (role: tool)            ──────►  {"type": "function_call_output", "call_id": tool_call_id, "output": content}
```

### Dual-path rules

1. **Native Replay Path** — used when the assistant entry metadata contains a valid `ResponsesReplayEnvelope` and its `origin` matches the current client exactly on `provider`, `model`, and `base_url`. Emit `envelope.output_items` verbatim (preserving item order, item `id`s, reasoning `encrypted_content`, and function-call `call_id`s). Do not additionally reconstruct the same turn from the normalized message (no duplication).
2. **Normalized Fallback Path** — used when metadata is absent, the envelope is malformed/unknown-version, or origin differs (model switch via `Alt+P`, provider switch, `/reload`, or a session produced by another client). Reconstruct from the normalized `ChatCompletionMessage`:
   - assistant text → one `message` item with `output_text` content;
   - each `tool_calls` entry → one `function_call` item using the normalized tool-call id as `call_id`, the function name, and the unchanged argument string;
   - omit reasoning and provider-specific ids entirely. Never claim foreign encrypted reasoning transfers between providers.
3. **Ordering** — iterate entries in conversation order so assistant/tool items interleave correctly across multiple turns.
4. **Tool-result correlation** — maintain the set of `call_id`s introduced by replayed/fallback `function_call` items; every subsequent tool result must reference a known `call_id`. If an unlinked `function_call_output` is encountered, raise a clear `LLMClientError` (or `ValueError` surfaced as one) naming the dangling id.
5. **Edge cases to handle explicitly** — assistant turns with both text and multiple calls, tool-only turns, assistant with empty/`None` content, and dict messages without `tool_call_id`. Reject or clearly fail on content shapes frugalbot never produces (multimodal parts); never `str()` an arbitrary object silently.

## 6. Tool Schema Conversion

The Responses API expects flat function tools with an explicit strictness flag. Use a pure helper so it is trivially testable and reusable:

```python
def convert_tools_for_responses(tools: Tools) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tools.get_all():
        function = tool.get_schema()["function"]
        converted.append({
            "type": "function",
            "name": function["name"],
            "description": function["description"],
            "parameters": function["parameters"],
            "strict": False,  # preserve optional/default parameter semantics
        })
    return converted
```

- `tools.get_all()` is the only public enumeration; `get_schema()` already returns the chat-format `function` payload.
- `strict: False` is mandatory: OpenAI defaults Responses function tools to strict, which would mark every property required and break tools with optional parameters (`read`, `edit`, etc.). Tests must assert the exact emitted dict.
- The flattened dicts pass through the SDK's `prepare_tools`/`_flatten_responses_tool` unchanged (no `function` key to flatten), so we never call the private helper.
- When there are no tools, pass `tools=None` (not `[]`) to keep the request body minimal.

## 7. Request Construction and Execution

`AnyLLMResponsesClient.call` performs, in order:

1. Validate inputs **outside** the retry loop (conversation adaptation, tool conversion, reasoning mapping).
2. Run the streamed request under per-call Tenacity retrying (§9).
3. Accumulate events (§8) and normalize into a `ChatCompletion` (§8/§9 finish-reason and usage mapping).
4. Attach the replay envelope via `attach_responses_replay`.

### Invocation parameters

```python
stream = await self.client.aresponses(
    model=self.model,
    input_data=input_items,
    tools=convert_tools_for_responses(tools) or None,
    stream=True,
    store=False,
    include=["reasoning.encrypted_content"] if reasoning_enabled else None,
    reasoning=self._build_reasoning_param(),
    extra_body=self._sanitize_extra_body(),
)
```

### Reasoning parameter mapping

| `thinking_level` | `reasoning` |
| --- | --- |
| `NONE` | omit the parameter (matches existing anyllm semantics; omission does not guarantee the provider disables its own default reasoning) |
| `LOW` | `{"effort": "low", "summary": "auto"}` |
| `MEDIUM` | `{"effort": "medium", "summary": "auto"}` |
| `HIGH` | `{"effort": "xhigh", "summary": "auto"}` when `use_xhigh_not_high` is set and `provider`/`model` are in `xhigh_provider_models`; otherwise `{"effort": "high", "summary": "auto"}` |

- Reuse the existing `xhigh_provider_models` allowlist and `use_xhigh_not_high` semantics from `AnyLLMConfig` verbatim.
- Request reasoning summaries only when supported; set `supports_thinking` honestly (model-level reasoning support is distinct from provider-level Responses support).
- Do not send `reasoning_effort` or `stream_options={"include_usage": True}` (Chat Completions only); read usage from terminal response metadata.

### Parameter precedence and `extra_body`

`stream=True`, `store=False`, adapted `input_data`, converted `tools`, and the computed `reasoning` take absolute precedence over `config.extra_body`. `_sanitize_extra_body()` strips/copies forbidden keys (`stream`, `store`, `input`/`input_data`, `tools`, `reasoning`, `include`, `previous_response_id`, `background`) and returns the remainder. Precedence is unit-tested.

## 8. Streaming Accumulator State Machine and UI Fencing

Accumulators are local to a single attempt (never instance attributes) so a shared client cannot leak partial state across agents.

### State variables

- `response_id: str`, `model: str`, `created: int`
- `full_content: str`, `full_reasoning_summary: str`
- `output_items: list[dict[str, Any]]` (ordered; authoritative from terminal response)
- `tool_calls: dict[int, ChatCompletionMessageFunctionToolCall]` keyed by `output_index`
- `call_ids_by_index: dict[int, str]` (the Responses `call_id`, distinct from the item `id`)
- `received_text_delta: bool`, `received_reasoning_delta: bool`, `received_arg_delta: set[int]`
- `streaming_tool_args: bool`, `active_tool_call_idx: int | None`
- `has_emitted_output: bool` (shared with the retry predicate, §9)

### Event handling

| Event `type` | Behavior |
| --- | --- |
| `response.created` / `response.in_progress` | Capture `response.id`, `model`, `created_at`; no UI output |
| `response.output_text.delta` | Append to `full_content`; emit `MessageEvent(delta, MessageType.ASSISTANT, MessageMarkup.MARKDOWN, is_stream=True)`; set `has_emitted_output = True`; mark `received_text_delta` |
| `response.output_text.done` | If no text delta was received for this part, emit the full `text` once instead of appending it to a stream |
| `response.reasoning_summary_text.delta` (and, where a provider emits it, `response.reasoning_text.delta` representing a summary) | Append to `full_reasoning_summary`; emit `MessageEvent(delta, MessageType.THINKING, MessageMarkup.MARKDOWN, is_stream=True)`; set `has_emitted_output = True`. **Never emit `encrypted_content` or raw hidden CoT** |
| `response.reasoning_summary_text.done` | If no summary delta was received, emit the full summary once |
| `response.reasoning_summary_part.added` | If a previous summary block is open, emit a separator before starting the next one |
| `response.output_item.added` (`item.type == "function_call"`) | Read `item.call_id`, `item.name`, `output_index`. If `streaming_tool_args` applies to a different index, close the open fence (newline + triple-backtick fence, `MessageType.TOOL_CALL`). Then emit the tool-name line followed by an opening JSON fence; set `streaming_tool_args = True`, `active_tool_call_idx = output_index`; record the call; `has_emitted_output = True` |
| `response.function_call_arguments.delta` | Append `delta` to the argument buffer for `output_index`; emit the delta as `MessageType.TOOL_CALL`; mark `received_arg_delta[index]` |
| `response.function_call_arguments.done` | If no delta was received for `output_index`, emit the full `arguments` once |
| `response.output_item.done` | Append the raw item dict (via `model_dump()`) to `output_items` in `output_index` order |
| `response.completed` | Authoritative: use `response.output`, `response.usage`, `response.status`, `response.incomplete_details` (fall back to accumulated `output_items` only if the terminal payload omits output) |
| `response.incomplete` | Terminal with `incomplete_details`; apply the finish-reason policy (§8) |
| `response.failed` / `error` | Terminal failure; raise/`LLMClientError` after closing fences; never fabricate success |
| Unknown/lifecycle events | Ignore harmlessly |

### Transition and cleanup guarantees

- Switching from tool-argument streaming back to text/reasoning, from one tool to another, or reaching completion closes the open ```` ```json ```` fence exactly once.
- A `try ... finally` around stream consumption guarantees any open fence is closed on success, failure, cancellation (`Ctrl+A`), or a provider that ends the stream without a terminal event.
- Each text/argument stream is appended from **either** deltas **or** a final snapshot, never both, preventing duplicated text in the TUI.
- Tool arguments are assembled in full (from the accumulated buffer) before normalization so `ToolCaller` only ever sees a complete, valid argument string.

### Finish reason and status normalization

- Successful response with any function call → `finish_reason = "tool_calls"`.
- Successful text-only response → `finish_reason = "stop"`.
- `incomplete_details.reason == "max_output_tokens"` → `"length"`.
- `incomplete_details.reason == "content_filter"` → `"content_filter"`.
- `status == "failed"`, an `error` event, or an incomplete response whose function-call arguments are truncated → raise `LLMClientError` (close fences first). Never return incomplete arguments for execution.
- A stream that ends without a terminal response and without usable output → raise `LLMClientError`.

### Normalized result

Build and return a `ChatCompletion` with:

- `id = response.id`, `created = response.created_at`, `model = response.model`, `object = "chat.completion"`;
- a single `Choice(index=0, finish_reason=..., message=ChatCompletionMessage(role="assistant", content=full_content or None, reasoning=Reasoning(content=full_reasoning_summary) if any else None, tool_calls=[...] or None))`;
- normalized tool calls whose `id` is the Responses `call_id` so `ToolCaller`'s `tool_call_id` correlates on the next turn.

### Usage normalization

```python
CompletionUsage(
    prompt_tokens=usage.input_tokens,
    completion_tokens=usage.output_tokens,
    total_tokens=usage.total_tokens,
    prompt_tokens_details=PromptTokensDetails(
        cached_tokens=usage.input_tokens_details.cached_tokens,
    ),
    completion_tokens_details=CompletionTokensDetails(
        reasoning_tokens=usage.output_tokens_details.reasoning_tokens,
    ),
)
```

- Import `CompletionTokensDetails`/`PromptTokensDetails` from `openai.types.completion_usage` (as `google.py` already does).
- Use the **plural** `input_tokens_details`/`output_tokens_details`. Keep `usage=None` when the provider omits it, and leave optional detail fields absent/zero as appropriate. Verify `Conversation.get_usage()`, status updates, and `ConversationCostCalculator` consume the normalized result unchanged.

## 9. Error, Retry, and Cancellation Policy

Retry behavior must depend on *attempt-local* state, so the existing fixed `@retry` decorator (which cannot see per-call state and would force shared mutable state onto a client shared across agents) is replaced with a per-call `AsyncRetrying` loop built inside `call()`:

```python
class AttemptState:
    def __init__(self) -> None:
        self.has_emitted_output = False

def _can_retry(state: AttemptState):
    def predicate(exc: BaseException) -> bool:
        if isinstance(exc, asyncio.CancelledError):
            return False
        if state.has_emitted_output:
            # Output already reached the TUI bus; retrying would duplicate text/tool previews.
            return False
        return True
    return predicate


async def call(self, conversation: Conversation, tools: Tools) -> ChatCompletion:
    input_items = ...   # validated outside the loop
    tools_payload = ...
    state = AttemptState()

    async def _before_sleep(retry_state: RetryCallState) -> None:
        await log_retry(retry_state, self.output_traceback_on_error)

    async for attempt in AsyncRetrying(
        retry=retry_if_exception(_can_retry(state)),
        stop=stop_after_attempt(20),
        wait=wait_exponential(multiplier=1, min=1, max=90),
        before_sleep=_before_sleep,
        reraise=True,
    ):
        with attempt:
            state.has_emitted_output = False  # reset per attempt
            ... build fresh accumulators, stream, normalize ...
    return completion
```

- **Retry** transient request/iteration failures only while `has_emitted_output is False`.
- **Do not retry** `asyncio.CancelledError`, parameter-validation errors, unsupported-capability/`NotImplementedError`, authentication failures, or any failure after the first bus emission. On an unretryable mid-stream failure, close open fences and raise `LLMClientError` with an explanatory message.
- `before_sleep` is a local closure because `AsyncRetrying`'s `RetryCallState.args` does not carry the client (`log_retry(retry_state, include_traceback)` is the shared helper).
- Keep accumulators and `AttemptState` local to each `call()` invocation; close the SDK stream via its supported cleanup mechanism (async `aclose`/context handling) in a `finally`.
- Never execute tools until a fully normalized, validated `ChatCompletion` is returned.
- Cover both request-time (await `aresponses`) and iteration-time (during `async for`) exceptions.

## 10. Configuration and Load-Time Integration

Reuse the existing anyllm configuration semantics so no new global config field is required:

- `provider`, `model`, `api_key_env_var`, optional `base_url`;
- `extra_body`;
- `xhigh_provider_models`, `use_xhigh_not_high`;
- `output_traceback_on_error`.

`AnyLLMResponsesConfig(LLMClientConfig)` mirrors `AnyLLMConfig` for these fields. Construction:

- `AnyLLM.create(provider=config.provider, api_key=os.getenv(config.api_key_env_var), api_base=config.base_url)`;
- store `client.base_url` for origin comparison (empty string when unset);
- set `provider` via the existing `_convert_any_llm_provider_to_models_dev_provider` mapping;
- check `getattr(self.client, "SUPPORTS_RESPONSES", False)` and raise `LLMClientError` with an actionable message (provider name, endpoint) when unsupported, before entering the retry loop. A custom `base_url` does not prove the remote endpoint supports Responses; never fall back to `acompletion`.

Trace the full path: config loading and `[clients.all]` merging (`config.py`) → `LLMClients.load` → constructor → request parameters, and preserve `Agents.load` propagation of `general.thinking_level` plus runtime `/thinking` updates. Extraction of shared helpers from `anyllm.py` (provider→models.dev mapping, xhigh resolution, retry logging) should live in a non-client utility module with mirrored tests; avoid new registered base clients or import/reload-order dependencies.

### `src/frugalbot/config_template.toml`

Add a commented, opt-in example (existing default client untouched):

```toml
# Opt-in client using the OpenAI Responses API
# [clients.openai_responses]
# type = "anyllmresponses"
# provider = "openai"
# model = "gpt-4.1-mini"
# api_key_env_var = "OPENAI_API_KEY"
```

Document that the example model must support the requested reasoning settings (use `NONE` for non-reasoning models) and how to add the name to an agent's explicit `clients` list.

## 11. Documentation

Update `README.md` to:

- list `anyllmresponses` alongside `anyllm` and `google`;
- note verified provider support (OpenAI) and the distinction between provider Responses support and model reasoning support;
- explain reasoning-effort configuration and `extra_body` precedence;
- clarify that frugalbot manages multi-turn history client-side (stateless replay, `store=False`) and what happens when switching providers/models.

## 12. Test Plan

Follow `docs/testing_guidelines.md`: fully annotated tests/fixtures/helpers, Given–When–Then, one public entry point and one observable exit point per test, parametrized cases, in-memory isolation, pyfakefs for persistence, and 100% branch coverage of new/modified code. Use real SDK/OpenAI event models where possible, mock only the SDK/network boundary, and add type annotations to every fixture and helper.

### A. `tests/frugalbot/clients/test_anyllm_responses.py` (new)

1. `test_init_with_valid_config_configures_properties` — provider, model, base_url, `supports_thinking`.
2. `test_init_with_unsupported_provider_raises_client_error` — fail fast via `SUPPORTS_RESPONSES`.
3. `test_convert_tools_for_responses_sets_strict_false_and_flattens_schema` — exact flat dict, optional params preserved, empty tools → `None`.
4. `test_convert_conversation_with_system_and_user_messages_builds_wire_format_items`.
5. `test_convert_conversation_with_matching_native_envelope_replays_output_items` — reasoning items, ids, and `call_id`s replayed verbatim.
6. `test_convert_conversation_with_mismatched_origin_falls_back_to_normalized_items` — strips foreign encrypted reasoning and provider ids.
7. `test_convert_conversation_with_unmatched_tool_result_raises_client_error`.
8. `test_call_with_text_stream_emits_assistant_events_and_returns_stop_completion`.
9. `test_call_with_reasoning_summary_emits_thinking_events_without_leaking_ciphertext`.
10. `test_call_with_multiple_tool_calls_maintains_separate_argument_streams` — fence transition between concurrent/sequential calls.
11. `test_call_with_final_only_output_item_emits_content_once` — dedup of delta vs. snapshot.
12. `test_call_with_usage_metadata_maps_token_details_correctly` — cached + reasoning tokens via plural detail fields.
13. `test_call_request_shape_sets_stream_store_and_input_precedence` — `extra_body` cannot override stateless/streaming invariants.
14. `test_call_with_transient_error_before_output_retries`.
15. `test_call_with_error_after_output_aborts_without_retry`.
16. `test_call_when_cancelled_propagates_cancellation_and_closes_fence`.
17. `test_call_with_incomplete_max_tokens_maps_to_length` and `test_call_with_incomplete_truncated_function_call_raises_client_error`.
18. `test_call_with_failed_status_raises_client_error`.
19. `test_call_attaches_replay_envelope_and_clears_transport_attribute`.

### B. Integration and system coverage

- **`tests/frugalbot/test_conversation.py`** — serialization/deserialization of entries with `metadata={"responses_replay": ...}`; round-trip of mixed legacy (2-tuple / no metadata) and new entries; accessors (`messages`, `latest_assistant_message`, `get_usage`) unaffected.
- **`tests/frugalbot/clients/test_clients_base.py`** — discovery via `type = "anyllmresponses"`; coexistence and ordering with `anyllm`; multiple named configurations; unload/reload without duplicate clients.
- **`tests/frugalbot/test_config.py` / `tests/frugalbot/test_agents.py`** — `[clients.all]` inheritance and per-client overrides; thinking-level propagation; explicit agent client selection; config template containing `[clients.openai_responses]` parses.
- **`tests/frugalbot/test_agent.py`** — streamed response → normalized function call → tool result → next request replaying the native envelope → final answer; multiple tools; invalid/incomplete arguments never reach execution; two agents sharing one client must not leak replay state.
- **Adapter/replay** — resumed reasoning/tool turns, provider/model/endpoint switching, and switching away and back (no hidden reasoning transfer claimed). Mirror helper tests beside the owning module's test path.

Add an optional, explicitly credentialed manual smoke test against a verified provider; normal tests must never make live API calls.

## 13. Expected File Changes

| File | Planned change |
| --- | --- |
| `src/frugalbot/clients/anyllm_responses.py` | New config, adapter, tool converter, streaming client, normalization, replay envelope |
| `src/frugalbot/conversation.py` | Explicit typed replay-metadata entry, serializer/loader support, backward-compatible accessors |
| `src/frugalbot/clients/anyllm.py` | Only minimal shared-helper/config refactoring if needed; behavior unchanged |
| `src/frugalbot/config_template.toml` | Commented opt-in example and settings/capability guidance |
| `README.md` | Client selection, provider limitations, stateless history, migration |
| Mirrored test modules above | New behavior and regression tests |
| `pyproject.toml`, `uv.lock` | Only if the verified API requires a newer minimum SDK |

No changes to generic client loading, the agent loop, or tool execution are expected unless tests reveal a concrete compatibility requirement; any such change must include regression coverage.

## 14. Validation and Acceptance Criteria

1. **Loader integration:** `LLMClients().load({"test": {"type": "anyllmresponses", ...}})` instantiates and registers `AnyLLMResponsesClient`.
2. **Network protocol:** all outbound calls route through `provider.aresponses(...)`; `acompletion` is never called.
3. **UI streaming:** assistant text deltas emit `MessageType.ASSISTANT`, reasoning summaries emit `MessageType.THINKING` (never ciphertext), and tool arguments are fenced cleanly and closed on every transition/failure/cancellation.
4. **Session durability:** sessions with reasoning and function calls survive `Conversation.serialize_to_file`/`load_from_file` round-trips with replay metadata intact; legacy sessions still load.
5. **Cross-model switching:** switching providers/models (or loading a foreign session) degrades gracefully to normalized history.
6. **Safety:** failures and cancellation cannot execute partial/incomplete tool calls or contaminate another conversation; retries never duplicate already-emitted output.
7. **No regressions:** existing `anyllm` and `google` client configurations and tests pass unchanged.
8. **Code quality:** run, in order, fixing errors without ignore comments and rerunning:

   ```powershell
   uv run ruff format
   uv run ruff check --fix
   uv run pyright
   uv run pytest -q
   ```
