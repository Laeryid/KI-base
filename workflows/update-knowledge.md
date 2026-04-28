---
description: Unified workflow — expands knowledge base if gaps exist, increases KI's quality and then synchronizes the full knowledge system
---

# /update-knowledge — Knowledge Base Update & Sync

Unified workflow that combines **expansion** (new KI creation, splitting, detailing) with **synchronization** (state update, dependency linking, indexing).

Run this workflow after any significant code changes or on a scheduled basis.

---

## Safety & Tooling Rules (Mandatory)

> [!IMPORTANT]
> When working with this workflow, it is **STRICTLY PROHIBITED** to use general file editing tools (e.g., `filesystem.edit_file`) for files inside the `<knowledge_root>` directory.
>
> You **MUST** use the following MCP tools from the `KnowledgeManager` server:
> - `write_know_file` — to create or fully overwrite a KI.
> - `edit_know_file` — for precise text replacement.
> - `make_know_dir` — to create directories inside the knowledge base.
>
> This ensures that documentation changes remain isolated within the knowledge sandbox and do not accidentally affect the project's source code.

---

## Phase 1 — Detect Code Changes

// turbo
`KnowledgeManager.check_changes()`

Record the list of modified files. This list informs the Audit phase but does not prevent cleaning existing documentation gaps.

---

## Phase 2 — Coverage Audit

// turbo
```powershell
# Call via MCP: KnowledgeManager.audit_coverage()
```

Analyze the output. Proceed to **Phase 3 (Expand)** if **any** of the following conditions are true:

| Signal | Meaning |
|---|---|
| ⚠️ Untracked Areas (Blind Spots) | A directory has code but no KI |
| 🔴 Critical Priority | No KI + large file volume |
| 🔥 Complexity Warning | One KI covers > 10 files |
| ❄️ Low Density | KI exists but is too brief for the code volume |

> [!TIP]
> If the audit shows all ✅ GREEN and no signals above, skip Phase 3 and proceed directly to Phase 4 (Sync).

---

## Phase 3 — Expand & Refactor Knowledge Base (conditional)

> Run this phase if Phase 2 identified gaps or Complexity Warnings. Run steps 3.1–3.4 for **one target per run** (highest priority first). If there are multiple targets, warn user to run the workflow again.

**Any** of the following signals is the reason to fulfil the phase 3.
| Signal | Meaning |
|---|---|
| ⚠️ Untracked Areas (Blind Spots) | A directory has code but no KI |
| 🔴 Critical Priority | No KI + large file volume |
| 🔥 Complexity Warning | One KI covers > 10 files |
| ❄️ Low Density | KI exists but is too brief for the code volume |

### 3.1 — Select Target

Priority order:
1. ⚠️ **Blind Spots** — create a new KI.
2. 🔴 **Critical Priority** — no KI + large code volume.
3. 🔥 **Complexity** — split one overloaded KI into focused KIs.
4. ❄️ **Low Density** — detail an existing sparse KI.
5. 🟡 **Medium/Low Priority** — planned improvement.

### 3.2 — Research & Analysis

**Case A — New module or Blind Spot:**
1. Read all files in the target directory.
2. Define **Purpose** and **Key Components**.
3. Check dependencies (who imports / calls this module).

**Case B — Split (Complexity):**
1. Read the current overloaded KI.
2. Identify logical file groups (e.g., `core logic`, `models`, `utils`).
3. Prepare a structure for new, focused KIs.

**Case C — Detail (Low Density):**
1. Find non-obvious points: side-effects, init order, hidden configs.
2. Add "Non-obvious Details" and "Common Pitfalls" sections.

### 3.3 — Create or Update KI File

Use `KnowledgeManager.write_know_file` or `KnowledgeManager.edit_know_file`.

**Standard KI structure:**
```markdown
<!-- last_verified: YYYY-MM-DD -->
# KI: <Module Name>

## Overview
<Purpose in 1-2 sentences>

## Key Components
| Class / Function | File | Purpose |
|---|---|---|

## Non-obvious Details
- <A fact not visible from function signatures>

## Common Pitfalls
- **<Symptom>**: <Solution>
```

### 3.4 — Register in doc_config.json

Update `doc_config.json`: add the new KI to `knowledge_items`, set `depends_on` for related KIs.

### 3.5 — Link Dependencies for New KI

// turbo
```powershell
# Call via MCP: KnowledgeManager.analyze_dependencies(ki_name="KI_FILENAME.md", only_changed=false)
```

---

## Phase 4 — Synchronize Affected Artifacts

For each artifact listed in the `check_changes()` output:

- `architecture.md` → read dependencies, update the section reflecting the changes.
- `KI_*.md` → read the KI and update only the outdated parts (preserve structure). Set `<!-- last_verified: YYYY-MM-DD -->`.
- `SKILL.md` → update the description to match new code behavior.

---

## Phase 5 — Finalization (always runs)

### 5.1 — Rebuild Directory Index

// turbo
`KnowledgeManager.generate_dir_index()`

### 5.2 — Sync AGENTS.md

// turbo
`KnowledgeManager.sync_agents_md()`

### 5.3 — Save State

// turbo
`KnowledgeManager.save_state()`

### 5.4 — Global Dependency Update

Final pass to ensure all inter-KI links are consistent across the entire knowledge base.

// turbo
`KnowledgeManager.analyze_all_dependencies()`

### 5.5 — Git Checkpoint

// turbo
`KnowledgeManager.git_checkpoint(message="Update knowledge base: expand + sync")`

---

## Completion Criteria (Checklist)

- [ ] `check_changes()` output reviewed.
- [ ] `audit_coverage()` run; signals identified.
- [ ] If gaps found: new or updated `KI_*.md` created in `knowledge/`.
- [ ] New KI registered in `doc_config.json`.
- [ ] `last_verified` in every touched KI contains today's date.
- [ ] `DIR_INDEX.md` regenerated.
- [ ] `AGENTS.md` synchronized.
- [ ] `doc_state.json` saved.
- [ ] All inter-KI dependencies linked.
- [ ] Git checkpoint created.
