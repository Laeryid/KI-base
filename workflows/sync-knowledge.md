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

For each artifact in `AFFECTED ARTIFACTS`:

- If it's `architecture.md` → read dependencies, update the section reflecting the changes.
- If it's `KI_*.md` → read the KI file and update only the outdated parts (preserve structure).
- If it's `SKILL.md` → update the description according to the new code behavior.

After updating an artifact, add the following line to the file header:
```
<!-- last_verified: YYYY-MM-DD -->
```

## Step 2.1 — Analyze Dependencies

Automatically identify and update inter-KI links for changed files.

// turbo
```powershell
# Call via MCP: KnowledgeManager.analyze_dependencies(ki_name="all", only_changed=true)
```

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
