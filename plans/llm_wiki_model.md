# LLM Wiki Model - Implementation Plan

## Goal

Add the LLM wiki pattern to frugalbot with **zero new Python code** - using only schema (instructions in `AGENTS.md`) and scaffolding (directories and initial files). The existing tools (`read`, `write`, `edit`, `grep`, `powershell`) are already sufficient for all wiki operations.

## Rationale

The LLM wiki pattern is fundamentally a **convention**, not a code feature. The LLM already has all the tools needed to create, read, update, and delete markdown files. What is missing is the instructions telling the LLM *how* to organize and maintain the wiki. That belongs in the schema layer (`AGENTS.md`), which is already injected into the system prompt via `{{agents_md}}`.

## Plan

### 1. Add wiki schema to `AGENTS.md` (schema layer)

Append a `# LLM Wiki` section to `AGENTS.md` describing the pattern as defined in the `@micuintus/llm-wiki` specification:

- **Directory Structure**:
  ```
  llm-wiki/
  ├── SCHEMA.md            # Project-specific conventions (read first)
  ├── index.md             # Canonical catalog of compiled pages
  ├── log.md               # Append-only operation log
  ├── raw-sources/         # Immutable; append-only
  │   ├── index.md         # Registry of every source
  │   └── <bucket>/        # Copies of ad-hoc sources
  └── <topic>/             # Compiled pages (distilled knowledge)
  ```
- **Ingest Workflow**: Ingest = **Register** + **Compile** + **Log**.
  1. **Register**: List source in `raw-sources/index.md` with a stable identifier. Copy mutable/walled sources into `raw-sources/<bucket>/`.
  2. **Compile**: Distill source into pages in `<topic>/`. Merge with targeted edits; append to `sources:`; bump `updated:`. Annotate contradictions inline.
  3. **Log**: Update `index.md` and append to `log.md` using precise verbs (`ingest` or `register`).
- **Frontmatter**: Mandatory fields for all pages: `title`, `type`, `updated`, `sources`.
  - Types: `concept`, `decision`, `bug`, `open-question`, `source`, `reference`, `synthesis`, `stub`.
- **Query Workflow**: Read `index.md`, follow links, synthesize answer with citations. If answer connects $\ge 2$ pages, offer to file as `type: synthesis`.
- **Lint Workflow**:
  - **Deterministic (auto-fix)**: Index sync, Internal link validation, Anchor link validation, Raw-source reference check, See Also bidirectionality, Frontmatter type check, Stub aging.
  - **Heuristic (report only)**: Contradictions, Stale claims, Orphans, Missing concepts, Reliability check.
- **Navigation & Quality**:
  - Use `index.md` as the canonical browse location.
  - Long pages (>200 lines) must have an inline `## Contents` block.
  - Survey pages must open with a "short answer" lede and end with a decision table.
  - Every page must have a `## See also` section with 2-4 related links.
- **Special Sources Recipes**:
  - **Code repositories**: Use grep + cite-by-line conventions.
  - **Agent sessions**: Use specific templates for Pi (JSONL) and Claude Code/Gemini CLI transcripts.
  - **Web LLM chats**: Use dedicated ingestion patterns for Claude.ai, ChatGPT, etc.
  - **Binaries/PDFs**: Pair with companion `.md` files; extract PDF to text first.

### 2. Create directory scaffolding

Create the following directory structure (using `.gitkeep` to track empty folders):

```
llm-wiki/.gitkeep
llm-wiki/raw-sources/.gitkeep
```

### 3. Create initial wiki files

Create the following seed files:

- **`llm-wiki/SCHEMA.md`**: Initial project conventions.
- **`llm-wiki/index.md`**: Minimal catalog with sections for Sources, Entities, and Concepts.
- **`llm-wiki/log.md`**: Empty log with header.
- **`llm-wiki/raw-sources/index.md`**: Empty registry.

### 4. Update `.gitignore` if needed

Ensure `llm-wiki/` is not git-ignored.

## Interaction Examples

Since the wiki is implemented as a set of conventions in the system prompt rather than as a dedicated tool, all interactions are conversational.

### Example 1: Ingesting a new source
**User**: "I found this paper on LLM reasoning: `https://arxiv.org/abs/example`. Add it to the wiki."

**LLM (Internal Process)**:
1. `write`: Add the URL to `llm-wiki/raw-sources/index.md`.
2. `read`: Fetch and analyze the paper content.
3. `edit/write`: Update or create pages in `llm-wiki/reasoning/` (e.g., `chain-of-thought.md`), updating the `sources` list and `updated` date in YAML frontmatter.
4. `edit`: Add the new pages to `llm-wiki/index.md`.
5. `write`: Append `## [2026-05-12] ingest | LLM Reasoning Paper` to `llm-wiki/log.md`.

**LLM**: "I've registered the paper and updated the 'LLM Reasoning' and 'Chain-of-Thought' pages in the wiki."

### Example 2: Querying the Wiki
**User**: "What do I know about the current state of LLM reasoning?"

**LLM (Internal Process)**:
1. `read`: `llm-wiki/index.md` to find relevant pages.
2. `read`: `llm-wiki/reasoning/state-of-the-art.md` and other linked pages.
3. Synthesize the answer using citations.

**LLM**: "Based on the wiki, LLM reasoning has evolved from basic Chain-of-Thought to Tree-of-Thoughts [Source: Reasoning Paper]. However, there is still a known gap in symbolic logic [Source: Logic Gap Note]. Would you like me to synthesize these into a 'Current State' summary page?"

### Example 3: Correcting a contradiction
**User**: "Wait, the new paper actually contradicts the previous one on the efficiency of Tree-of-Thoughts. Fix the wiki."

**LLM (Internal Process)**:
1. `read`: Both conflicting pages.
2. `edit`: Add a `### Contradiction:` block to the relevant page, citing both sources.
3. `edit`: Bump the `updated` date.
4. `write`: Log the correction in `llm-wiki/log.md`.

**LLM**: "I've noted the contradiction between the two papers on the 'Tree-of-Thoughts' page and updated the log."

### Example 4: Wiki Audit (Linting)
**User**: "Can you audit the wiki for any broken links or orphan pages?"

**LLM (Internal Process)**:
1. `read`: `llm-wiki/index.md` and all files in `llm-wiki/`.
2. Validate all `[text](path.md)` links against the filesystem.
3. Check for pages not listed in `index.md` (orphans).
4. `edit`: Auto-fix broken paths if a matching filename is found.
5. `write`: Append audit results to `llm-wiki/log.md`.

**LLM**: "Audit complete. I found and fixed 3 broken internal links and identified 1 orphan page ('old-concept.md'), which I've now added to the index."

## Challenges & Risks

Since this implementation relies entirely on LLM discipline rather than code enforcement, several risks emerge:

- **Index Decay**: If the LLM fails to update `index.md` during ingest, the wiki becomes fragmented.
- **Context Window Pressure**: Large indexes or reading multiple pages for one query increases token usage.
- **Search Reliance**: The LLM must explicitly fallback to `grep` if the index is insufficient.
- **Log Bloat**: `log.md` will eventually become too large to read efficiently.
- **Structural Drift**: Without code enforcement, frontmatter or styles may drift.
- **Contradiction Management**: Depends on the LLM's ability to cross-reference and the user's adjudication.

## Mitigation Strategies (via `AGENTS.md`)

- **Strict Indexing Rules**: Define "Atomic Updates" where every page edit *must* be followed by an index update in the same turn.
- **Log Rotation**: Instruct the LLM to archive logs (e.g., `log_2026_05.md`) when they exceed a certain size.
- **Page Templates**: Provide strict Markdown templates in `AGENTS.md` or `SCHEMA.md`.
- **Explicit Search Fallback**: Codify the "Query workflow" to include a `grep` step if index search fails.
- **Pruning Workflow**: Add a "Pruning" step to Lint to merge redundant pages or archive stale info.

## What we are NOT doing (by design)

- **No new tools.** The existing `read`, `write`, `edit`, `grep`, `powershell` tools are sufficient.
- **No new Python modules.** No `wiki.py` or `WikiManager` classes.
- **No config.toml changes.** Wiki paths are hardcoded in `AGENTS.md` as `llm-wiki/`.
- **No CLI commands.** Operations are performed conversationally.
- **No search engine or RAG.** The `index.md` file is the primary navigation hub.
- **No Obsidian/Marp/Dataview-specific changes.** The wiki remains plain markdown.

## Total changes

| File | Action |
|------|--------|
| `AGENTS.md` | Append detailed LLM Wiki schema instructions |
| `llm-wiki/.gitkeep` | Create |
| `llm-wiki/raw-sources/.gitkeep` | Create |
| `llm-wiki/SCHEMA.md` | Create |
| `llm-wiki/index.md` | Create |
| `llm-wiki/log.md` | Create |
| `llm-wiki/raw-sources/index.md` | Create |
| `.gitignore` | Possibly update |

No other files touched.
