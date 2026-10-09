---
name: ki-manager-sync-knowledge
description: Synchronize the project knowledge system (KI, DIR_INDEX, artifacts)
metadata:
  author: ki-manager
  version: "1.1"
<!-- if-compact -->
allowed-tools: ki_instructions ki_read ki_search ki_tools ki_call ki_mutate
<!-- else-compact -->
allowed-tools: read_know_file write_know_file edit_know_file audit_coverage check_ki_drift generate_dir_index ki_instructions ki_read git_diff_secured update_last_verified save_state analyze_dependencies git_checkpoint
<!-- /if-compact -->
---

# /sync-knowledge — Knowledge System Synchronization

Triggered manually after completing significant work (refactoring, new feature, architectural change).

## Safety & Tooling Rules (Mandatory)
> [!IMPORTANT]
> When working with this workflow, it is **STRICTLY PROHIBITED** to use general file editing tools (e.g., `filesystem.edit_file`) for files inside the <knowledge_root> directory.
> 
<!-- if-compact -->
> You **MUST** use the following MCP tools from the `ki-manager` server:
> - `ki_read` — to read existing KIs.
> - `ki_mutate(tool="write_know_file", ...)` — to create or fully overwrite a KI.
> - `ki_mutate(tool="edit_know_file", ...)` — for precise text replacement.
> - `ki_mutate(tool="make_know_dir", ...)` — to create directories inside the knowledge base.
<!-- else-compact -->
> You **MUST** use the following MCP tools from the `ki-manager` server:
> - `read_know_file` / `ki_read` — to read existing KIs.
> - `write_know_file` — to create or fully overwrite a KI.
> - `edit_know_file` — for precise text replacement.
> - `make_know_dir` — to create directories inside the knowledge base.
<!-- /if-compact -->
> 
> This ensures that documentation changes remain isolated within the knowledge sandbox and do not accidentally affect the project's source code.

## Step 1 — Identify Changes & Drift

1. **Check Drift and Discrepancies**:
   Run `check_ki_drift` to detect dead symbols, unmapped new symbols, missing files, or broken links:
   // turbo
<!-- if-compact -->
   `ki_call(tool="check_ki_drift")`
<!-- else-compact -->
   `check_ki_drift()`
<!-- /if-compact -->

2. **Git Modified Files**:
   Run `git_diff_secured` to get a list of modified files:
   // turbo
<!-- if-compact -->
   `ki_call(tool="git_diff_secured")`
<!-- else-compact -->
   `git_diff_secured`
<!-- /if-compact -->

Record the results. If there are neither changes nor drift issues, terminate; everything is up to date.

## Step 2 — Update Affected Documentation Artifacts

1. **Smart Date Update**:
   Run the following tool to update `last_verified` tags ONLY in KIs affected by code changes:
   // turbo
<!-- if-compact -->
   `ki_mutate(tool="update_last_verified")`
<!-- else-compact -->
   `update_last_verified`
<!-- /if-compact -->

2. **Manual Updates**:
   For each artifact in `AFFECTED ARTIFACTS` or flagged in the drift report that requires content changes:
   - If it's `architecture.md` → read dependencies, update the section reflecting the changes.
   - If it's `KI_*.md` → update only the outdated parts, maintaining the canonical KI structure.
   - If it's `SKILL.md` → update description according to the new code behavior.

## Step 3 — Update DIR_INDEX.md

// turbo
<!-- if-compact -->
`ki_call(tool="generate_dir_index")`
<!-- else-compact -->
`generate_dir_index`
<!-- /if-compact -->

## Step 4 — Save New State to doc_state.json

// turbo
<!-- if-compact -->
`ki_mutate(tool="save_state")`
<!-- else-compact -->
`save_state`
<!-- /if-compact -->

## Step 5 — Incremental Dependency Update

Update inter-KI links ONLY for modified KIs to minimize Git noise.

// turbo
<!-- if-compact -->
`ki_call(tool="analyze_dependencies", args={"only_changed": true})`
<!-- else-compact -->
`analyze_dependencies(args={"only_changed": true})`
<!-- /if-compact -->

> [!NOTE]
> Use `analyze_all_dependencies` only if there were global structural changes in the project.

## Step 6 — Git Checkpoint

Finalize the synchronization by creating a git snapshot of the knowledge state.

// turbo
<!-- if-compact -->
`ki_mutate(tool="git_checkpoint", args={"message": "Sync knowledge system state"})`
<!-- else-compact -->
`git_checkpoint(args={"message": "Sync knowledge system state"})`
<!-- /if-compact -->
