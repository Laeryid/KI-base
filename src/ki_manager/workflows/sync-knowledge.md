---
name: ki-manager-sync-knowledge
description: Synchronize the project knowledge system (KI, DIR_INDEX, artifacts)
metadata:
  author: ki-manager
  version: "2.0"
<!-- if-compact -->
allowed-tools: ki_instructions ki_read ki_search ki_tools ki_call ki_mutate
<!-- else-compact -->
allowed-tools: ki_lint ki_sync read_know_file write_know_file edit_know_file audit_coverage check_ki_drift generate_dir_index ki_instructions ki_read git_diff_secured update_last_verified save_state analyze_dependencies git_checkpoint
<!-- /if-compact -->
---

# /sync-knowledge — Knowledge System Synchronization

Triggered manually after completing significant work (refactoring, new feature, architectural change) or after editing KI/ADR files.

## Safety & Tooling Rules
> [!NOTE]
> - Native file tools (`read_file`, `edit_file`) **are allowed** for inspecting and editing `.md` files inside `{{KI_DIR}}/knowledge/` and `{{KI_DIR}}/decisions/`.
> - Keep all `*.ki.md` files strictly inside `{{KI_DIR}}/knowledge/` (never in `{{KI_DIR}}/` root), and never delete `{{KI_DIR}}/knowledge/`.
<!-- if-compact -->
> - After editing any KI or ADR file, run `ki_mutate(tool="ki_sync")` (or `ki_call(tool="ki_lint")`) to validate structure, metadata, and references.
<!-- else-compact -->
> - After editing any KI or ADR file, run `ki_sync()` (or `ki_lint()`) to validate structure, metadata, and references.
<!-- /if-compact -->

## Fast Path — Composite Sync (`ki_sync`)

Run `ki_sync` to execute the full pipeline in a single call (`ki_lint` -> `git diff` -> `check_ki_drift` on affected KIs -> targeted `update_last_verified` -> `generate_dir_index` -> `save_state` -> `sync_agents_md`):

// turbo
<!-- if-compact -->
`ki_mutate(tool="ki_sync")`
<!-- else-compact -->
`ki_sync()`
<!-- /if-compact -->

If `ki_sync` aborts on `ki_lint` errors, fix the reported structural/metadata/reference issues (or pass `fix_lint=true` to auto-register unmapped KIs) and re-run `ki_sync`.

## Manual Enrichment (When Drift Is Reported)

If the `check_ki_drift` summary inside `ki_sync` reports dead symbols, unmapped symbols, or stale documentation:
1. Edit the affected KI(s) (using native `edit_file` or MCP `edit_know_file` / `write_know_file`).
2. Optionally run incremental dependency linking:
<!-- if-compact -->
   `ki_call(tool="analyze_dependencies", args={"only_changed": true})`
<!-- else-compact -->
   `analyze_dependencies(only_changed=true)`
<!-- /if-compact -->
3. Re-run `ki_sync` to refresh `last_verified`, `DIR_INDEX.md`, `doc_state.json`, and `AGENTS.md`:
<!-- if-compact -->
   `ki_mutate(tool="ki_sync")`
<!-- else-compact -->
   `ki_sync()`
<!-- /if-compact -->

## Optional — Git Checkpoint

Only create a dedicated git snapshot when explicitly requested or when `auto_git_checkpoint` is enabled in config:
<!-- if-compact -->
`ki_mutate(tool="git_checkpoint", args={"message": "Sync knowledge system state", "commit": true})`
<!-- else-compact -->
`git_checkpoint(message="Sync knowledge system state", commit=true)`
<!-- /if-compact -->
