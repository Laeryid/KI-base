---
name: ki-manager-create-adr
description: Document architectural decisions, logic transitions, or abandoned paths (ADR)
metadata:
  author: ki-manager
  version: "1.1"
<!-- if-compact -->
allowed-tools: ki_instructions ki_read ki_search ki_tools ki_call ki_mutate
<!-- else-compact -->
allowed-tools: read_know_file write_know_file ki_instructions create_adr sync_agents_md
<!-- /if-compact -->
---

# /create-adr — Architectural Decision Records (ADR / Retrospective)

Triggered on user demand when it's necessary to document a significant architectural transition, fix a complex bug, or record an "erroneous path" that was abandoned. **ADRs (Architecture Decision Records) are strictly time-bound** — they reflect the trade-offs that were relevant at the moment the decision was made.

## General AI Instructions
- **Never modify old ADRs.** If a decision is revisited, create a new ADR with a reference to the old one.
- The internal structure of an ADR should be a chronological log (append-only).

## Safety & Tooling Rules (Mandatory)
> [!IMPORTANT]
> When working with this workflow, it is **STRICTLY PROHIBITED** to use general file editing tools (e.g., `filesystem.edit_file`) for files inside the <knowledge_root> directory.
> 
<!-- if-compact -->
> You **MUST** use the following MCP tools from the `ki-manager` server:
> - `ki_mutate(tool="create_adr", ...)` — to create and register a new ADR.
> - `ki_read` — to read existing ADRs.
> - `ki_mutate(tool="sync_agents_md")` — to synchronize ADR tables in AGENTS.md.
> - `ki_mutate(tool="write_know_file", ...)` — to create or fully overwrite a file.
> - `ki_mutate(tool="edit_know_file", ...)` — for precise text replacement.
<!-- else-compact -->
> You **MUST** use the following MCP tools from the `ki-manager` server:
> - `create_adr` — to create and register a new ADR.
> - `read_know_file` / `ki_read` — to read existing ADRs.
> - `sync_agents_md` — to synchronize ADR tables in AGENTS.md.
> - `write_know_file` — to create or fully overwrite a file.
> - `edit_know_file` — for precise text replacement.
<!-- /if-compact -->
> 
> This ensures that ADRs and documentation changes remain isolated within the knowledge sandbox and do not accidentally affect the project's source code.

## Step 0 — Discovery Phase
Before writing the document, the AI must analyze the context of recent changes to "infer" the problem independently:
1. **Git History**: Run `git log --since="3 days ago" -p` (or another reasonable period) to see code changes and commits.
2. **Analytics**: Match "fix" messages with logic changes. Look for patterns: reverted changes, data type shifts, addition of new protective mechanisms.
3. **Proposal**: Formulate a list of ADR candidates (e.g., "Abandoning FP16", "Switching to explicit Parquet schemas").
4. **Validation**: Present this list to the user. If the user approves, proceed to Step 1.

## Step 1 — Create and Register ADR
Use the dedicated `create_adr` tool. It automatically:
- Assigns the next sequential numeric ID prefix (`XXX`).
- Collects **Git Provenance** (commit, branch, author) and **Environment Snapshot** (OS, Python version).
- Detects **Scope & Affected Files** and maps them to related Knowledge Items in `doc_config.json`.
- If `supersedes` is specified, automatically updates the older ADRs with a warning banner, marks them as `Superseded by ADR XXX`, and updates `doc_config.json`.
- Formats standard Markdown structure with date, context, decision, impact, and optional sections for rejected alternatives, invariants, and verification.
- Registers the ADR entry into `doc_config.json` with linked dependencies and updates `AGENTS.md`.

<!-- if-compact -->
// turbo
`ki_mutate(tool="create_adr", args={"title": "<Descriptive Title>", "topic_name": "<short_topic_slug>", "context": "<Context and Problem statement>", "decision": "<Specific architectural decision reached>", "consequences": "<Positive and negative trade-offs>", "supersedes": ["<optional_old_id_1>", "<optional_old_id_2>"], "rejected_alternatives": "<what failed and why>", "invariants": "- [MUST] <rule>\n- [MUST NOT] <antipattern>", "verification": "<pytest command or test>"})`
<!-- else-compact -->
// turbo
`create_adr(title="<Descriptive Title>", topic_name="<short_topic_slug>", context="<Context and Problem statement>", decision="<Specific architectural decision reached>", consequences="<Positive and negative trade-offs>", supersedes=["<optional_old_id_1>", "<optional_old_id_2>"], rejected_alternatives="<what failed and why>", invariants="- [MUST] <rule>\n- [MUST NOT] <antipattern>", verification="<pytest command or test>")`
<!-- /if-compact -->

## Step 2 — Verify and Synchronize
Verify that the ADR was created in `decisions/` and referenced in documentation:
<!-- if-compact -->
// turbo
`ki_mutate(tool="sync_agents_md")`
<!-- else-compact -->
// turbo
`sync_agents_md()`
<!-- /if-compact -->

Immediately after successful integration, suggest that the user run (or automatically launch) the `/sync-knowledge` workflow to keep `DIR_INDEX` up to date.
