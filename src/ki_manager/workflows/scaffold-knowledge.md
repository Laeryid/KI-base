---
name: ki-manager-scaffold-knowledge
description: Bootstrap the knowledge base — generate KI stubs for all uncovered modules, then enrich them with AI analysis in small batches
metadata:
  author: ki-manager
  version: "1.3"
<!-- if-compact -->
allowed-tools: ki_instructions ki_read ki_search ki_tools ki_call ki_mutate
<!-- else-compact -->
allowed-tools: audit_coverage ki_scaffold ki_scaffold_status ki_finalize_scaffolds analyze_all_dependencies generate_dir_index git_checkpoint read_know_file write_know_file ki_instructions ki_read
<!-- /if-compact -->
---

# /scaffold-knowledge — Bootstrap & Enrich the Knowledge Base

Three-phase workflow:
1. **Scaffold** — generate structural stubs for all uncovered modules (no AI, fast).
2. **Enrich** — fill each stub with AI-written analysis in small batches (context-aware, iterative).
3. **Finalize** — strip scaffold markers, update summaries, wire up dependencies.

> [!NOTE]
> If scaffolding is already done, skip to **Phase 2**. If all stubs are enriched, skip to **Phase 3**.

---

## Phase 1 — Generate Stubs

### Step 1.1 — Check Current Coverage

// turbo
<!-- if-compact -->
`ki_call(tool="audit_coverage")`
<!-- else-compact -->
`audit_coverage()`
<!-- /if-compact -->

If all modules are ✅ GREEN — skip Phase 1 entirely and go to Phase 2.

### Step 1.2 — Preview (optional)

// turbo
<!-- if-compact -->
`ki_mutate(tool="ki_scaffold", args={"dry_run": true})`
<!-- else-compact -->
`ki_scaffold(dry_run=true)`
<!-- /if-compact -->

### Step 1.3 — Generate Scaffold KIs

**All uncovered modules (recommended for new projects):**

// turbo
<!-- if-compact -->
`ki_mutate(tool="ki_scaffold")`
<!-- else-compact -->
`ki_scaffold()`
<!-- /if-compact -->

**Specific modules only:**

// turbo
<!-- if-compact -->
`ki_mutate(tool="ki_scaffold", args={"modules": "path/to/module1,path/to/module2"})`
<!-- else-compact -->
`ki_scaffold(modules="path/to/module1,path/to/module2")`
<!-- /if-compact -->

**Regenerate existing stubs:**

// turbo
<!-- if-compact -->
`ki_mutate(tool="ki_scaffold", args={"force": true})`
<!-- else-compact -->
`ki_scaffold(force=true)`
<!-- /if-compact -->

### Step 1.4 — Git Checkpoint

// turbo
<!-- if-compact -->
`ki_mutate(tool="git_checkpoint", args={"message": "Bootstrap knowledge base: scaffold KI stubs"})`
<!-- else-compact -->
`git_checkpoint(message="Bootstrap knowledge base: scaffold KI stubs")`
<!-- /if-compact -->

---

## Phase 2 — Enrich Stubs (AI Analysis)

> [!IMPORTANT]
> This phase is **context-sensitive**. Process KIs in small batches (3–5 per run). When context starts to fill up, save progress and recommend the user to continue in a new session.

### Step 2.1 — Get the List of Pending Stubs

// turbo
<!-- if-compact -->
`ki_call(tool="ki_scaffold_status")`
<!-- else-compact -->
`ki_scaffold_status()`
<!-- /if-compact -->

Identify all KIs with status `🚧 Pending`. These are the enrichment targets.

### Step 2.2 — Select a Batch

Take **3–5 pending KIs** (start from the most critical: 🔴 Critical or ⚠️ Blind Spots first).

For each KI in the batch, perform Steps 2.3–2.4 sequentially before moving to the next.

### Step 2.3 — Analyze the Source Module

For the current KI:

1. Read the KI stub with `ki_read` (or `read_know_file`) to get the list of files and extracted symbols:
<!-- if-compact -->
   `ki_read(rel_path="<filename>.ki.md")`
<!-- else-compact -->
   `read_know_file(rel_path="<filename>.ki.md")`
<!-- /if-compact -->
2. Read the actual source files referenced in the stub.
3. Identify:
   - **Purpose** — what problem does this module solve? (1–2 sentences)
   - **Key Components** — which classes/functions are the most important and what do they do?
   - **Non-obvious Details** — side-effects, initialization order, global state, hidden configs, important constraints.
   - **Common Pitfalls** — known failure modes, misuse patterns.

### Step 2.4 — Overwrite the KI with Enriched Content

Replace the stub with the enriched version:
<!-- if-compact -->
// turbo
`ki_mutate(tool="write_know_file", args={"rel_path": "<filename>.ki.md", "content": "..."})`
<!-- else-compact -->
// turbo
`write_know_file(rel_path="<filename>.ki.md", content="...")`
<!-- /if-compact -->

> [!IMPORTANT]
> The **first line must be `<!-- scaffold: enriched -->`**. This marker tells `ki_finalize_scaffolds` to process the file in Phase 3 (clean markers, update doc_config summary). The `Related KIs` section is left empty — it will be populated automatically in Phase 3.

**Required KI structure:**

```markdown
<!-- scaffold: enriched -->
<!-- last_verified: YYYY-MM-DD -->
# KI: <Module Name>

## Overview
<Concise description in 1-2 sentences: what this module does and why it exists.
This text will automatically become the summary in doc_config.json on finalization.>

## Entry Points & Public API
- `SymbolName`: <Primary interface, factory, or entry function for external consumers>

## Key Components
| Class / Function | File | Purpose |
|---|---|---|
| `ClassName` | `path/to/file.py` | What it does |
| `function_name` | `path/to/file.py` | What it does |

## Testing & Verification
- Test commands: `pytest tests/test_<module>.py`
- Test files: `tests/test_<module>.py`

## Non-obvious Details
- <Specific architectural rule, side-effect, initialization constraint, or env var>
- <Only facts not obvious from function signatures alone>

## Common Pitfalls
- **<Symptom or misuse scenario>**: <Root cause and how to avoid it>

## Related KIs
<!-- populated by analyze_all_dependencies -->
```

### Step 2.5 — Check Progress

// turbo
<!-- if-compact -->
`ki_call(tool="ki_scaffold_status")`
<!-- else-compact -->
`ki_scaffold_status()`
<!-- /if-compact -->

Check enriched count:
- If all stubs show `✅ Enriched` (0 pending) → proceed to **Phase 3**.
- If context window is getting full (>50% used) → run git checkpoint, report progress, and recommend continuing in a new session:
<!-- if-compact -->
  `ki_mutate(tool="git_checkpoint", args={"message": "Enrich KI stubs: batch"})`
<!-- else-compact -->
  `git_checkpoint(message="Enrich KI stubs: batch")`
<!-- /if-compact -->

---

## Phase 3 — Finalize (when `ki_scaffold_status` shows 0 pending)

> [!IMPORTANT]
> Run this phase **only once**, after all stubs are enriched (`ki_scaffold_status()` shows no 🚧 Pending entries).

### Step 3.1 — Finalize Scaffold KIs
Removes `<!-- scaffold: enriched -->` markers from all enriched KIs and updates their summaries in `doc_config.json` from the Overview text.

// turbo
<!-- if-compact -->
`ki_mutate(tool="ki_finalize_scaffolds")`
<!-- else-compact -->
`ki_finalize_scaffolds()`
<!-- /if-compact -->

Preview without changes:
<!-- if-compact -->
`ki_mutate(tool="ki_finalize_scaffolds", args={"dry_run": true})`
<!-- else-compact -->
`ki_finalize_scaffolds(dry_run=true)`
<!-- /if-compact -->

### Step 3.2 — Wire Up Dependencies
Populates the `Related KIs` section in every KI by analyzing code imports.

// turbo
<!-- if-compact -->
`ki_call(tool="analyze_all_dependencies")`
<!-- else-compact -->
`analyze_all_dependencies()`
<!-- /if-compact -->

### Step 3.3 — Rebuild Directory Index

// turbo
<!-- if-compact -->
`ki_call(tool="generate_dir_index")`
<!-- else-compact -->
`generate_dir_index()`
<!-- /if-compact -->

### Step 3.4 — Final Git Checkpoint

// turbo
<!-- if-compact -->
`ki_mutate(tool="git_checkpoint", args={"message": "Knowledge base bootstrapped and finalized"})`
<!-- else-compact -->
`git_checkpoint(message="Knowledge base bootstrapped and finalized")`
<!-- /if-compact -->

---

## What's Next?

| Next Step | When |
|---|---|
| `/expand-knowledge` | To deepen individual KIs (split overloaded ones, add pitfalls) |
| `/sync-knowledge` | After code changes to keep the knowledge base up to date |

---

## Readiness Criteria (Checklist)

- [ ] Phase 1: `ki_scaffold()` executed; stubs created for all uncovered modules.
- [ ] Phase 2: `ki_scaffold_status()` shows 0 `pending` stubs; all are `enriched`.
- [ ] Phase 3: `ki_finalize_scaffolds()` run; no scaffold markers remain.
- [ ] Phase 3: `analyze_all_dependencies()` run; `Related KIs` populated.
- [ ] Phase 3: `DIR_INDEX.md` regenerated.
- [ ] Phase 3: Final git checkpoint created.
