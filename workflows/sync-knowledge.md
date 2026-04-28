---
description: Synchronize the project knowledge system (KI, DIR_INDEX, artifacts)
---

# /sync-knowledge — Knowledge System Synchronization

Triggered manually after completing significant work (refactoring, new feature, architectural change).

## Safety & Tooling Rules (Mandatory)
> [!IMPORTANT]
> When working with this workflow, it is **STRICTLY PROHIBITED** to use general file editing tools (e.g., `filesystem.edit_file`) for files inside the <knowledge_root> directory.
> 
> You **MUST** use the following MCP tools from the `KnowledgeManager` server:
> - `write_know_file` — to create or fully overwrite a KI.
> - `edit_know_file` — for precise text replacement.
> - `make_know_dir` — to create directories inside the knowledge base.
> 
> This ensures that documentation changes remain isolated within the knowledge sandbox and do not accidentally affect the project's source code.

## Step 1 — Identify Changes

Run `KnowledgeEngine.check_for_changes()` to get a list of modified files:

// turbo
`KnowledgeManager.check_changes()`

Record the result. If there are no changes, terminate; everything is up to date.

## Step 2 — Update Affected Documentation Artifacts

1. **Smart Date Update**:
   Run the following tool to update `last_verified` tags ONLY in KIs affected by code changes:
   // turbo
   `KnowledgeManager.update_last_verified()`

2. **Manual Updates**:
   For each artifact in `AFFECTED ARTIFACTS` that requires content changes (not just date):
   - If it's `architecture.md` → read dependencies, update the section reflecting the changes.
   - If it's `KI_*.md` → update only the outdated parts, maintaining the `KI_template.md` structure.
   - If it's `SKILL.md` → update description according to the new code behavior.

## Step 3 — Update DIR_INDEX.md

// turbo
`KnowledgeManager.generate_dir_index()`

If the script hasn't been created yet, generate `DIR_INDEX.md` manually: project directories only (no files), with file counts for each.

## Step 4 — Update AGENTS.md

// turbo
`KnowledgeManager.sync_agents_md()`

## Step 5 — Save New State to doc_state.json

// turbo
`KnowledgeManager.save_state()`

## Step 6 — Incremental Dependency Update

Update inter-KI links ONLY for modified KIs to minimize Git noise.

// turbo
`KnowledgeManager.analyze_dependencies(only_changed=True)`

> [!NOTE]
> Use `KnowledgeManager.analyze_all_dependencies()` only if there were global structural changes in the project.

## Step 7 — Git Checkpoint

Finalize the synchronization by creating a git snapshot of the knowledge state.

// turbo
`KnowledgeManager.git_checkpoint(message="Sync knowledge system state")`
