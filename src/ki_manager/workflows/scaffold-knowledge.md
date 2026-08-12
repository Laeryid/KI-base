---
name: ki-manager-scaffold-knowledge
description: Bootstrap the knowledge base — generate KI stubs for all uncovered modules, then enrich them with AI analysis in small batches
metadata:
  author: ki-manager
  version: "1.2"
allowed-tools: audit_coverage ki_scaffold ki_scaffold_status ki_finalize_scaffolds analyze_all_dependencies generate_dir_index git_checkpoint read_know_file write_know_file ki_instructions
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
`audit_coverage()`

If all modules are ✅ GREEN — skip Phase 1 entirely and go to Phase 2.

### Step 1.2 — Preview (optional)

// turbo
`ki_scaffold(dry_run=true)`

### Step 1.3 — Generate Scaffold KIs

**All uncovered modules (recommended for new projects):**

// turbo
`ki_scaffold()`

**Specific modules only:**

// turbo
`ki_scaffold(modules="path/to/module1,path/to/module2")`

**Regenerate existing stubs:**

// turbo
`ki_scaffold(force=true)`

### Step 1.4 — Git Checkpoint

// turbo
`git_checkpoint(message="Bootstrap knowledge base: scaffold KI stubs")`

---

## Phase 2 — Enrich Stubs (AI Analysis)

> [!IMPORTANT]
> This phase is **context-sensitive**. Process KIs in small batches (3–5 per run). When context starts to fill up, save progress and recommend the user to continue in a new session.

### Step 2.1 — Get the List of Pending Stubs

// turbo
`ki_scaffold_status()`

Identify all KIs with status `🚧 Pending`. These are the enrichment targets.

### Step 2.2 — Select a Batch

Take **3–5 pending KIs** (start from the most critical: 🔴 Critical or ⚠️ Blind Spots first).

For each KI in the batch, perform Steps 2.3–2.4 sequentially before moving to the next.

### Step 2.3 — Analyze the Source Module

For the current KI:

1. Read the KI stub with `read_know_file` to get the list of files and extracted symbols.
2. Read the actual source files referenced in the stub.
3. Identify:
   - **Purpose** — what problem does this module solve? (1–2 sentences)
   - **Key Components** — which classes/functions are the most important and what do they do?
   - **Non-obvious Details** — side-effects, initialization order, global state, hidden configs, important constraints.
   - **Common Pitfalls** — known failure modes, misuse patterns.

### Step 2.4 — Overwrite the KI with Enriched Content

Use `write_know_file` to replace the stub with the enriched version.

> [!IMPORTANT]
> The **first line must be `<!-- scaffold: enriched -->`**. This marker tells `ki_finalize_scaffolds` to process the file in Phase 3 (clean markers, update doc_config summary). The `Related KIs` section is left empty — it will be populated automatically in Phase 3.

**Required KI structure:**

```markdown
<!-- scaffold: enriched -->
<!-- last_verified: YYYY-MM-DD -->
# KI: <Module Name>

**Module:** `path/to/module`

## Overview
<Purpose in 1–2 sentences. What problem does this module solve?>

## Key Components
| Class / Function | File | Purpose |
|---|---|---|
| `ClassName` | `file.py` | <What it does> |

## Non-obvious Details
- <A fact not visible from function signatures>

## Common Pitfalls
- **<Symptom>**: <Solution>

## Related KIs
<!-- filled automatically by ki_finalize_scaffolds + analyze_all_dependencies -->
```

### Step 2.5 — Context Check (after each KI)

After writing each enriched KI, evaluate remaining context capacity:

- **Context < 50% used** → continue with the next KI in the batch.
- **Context 50–70% used** → finish the current batch, then do Step 2.6.
- **Context > 70% used** → stop immediately, do Step 2.6.

### Step 2.6 — Save Progress & Report

// turbo
`ki_scaffold_status()`

Report to the user:
- How many KIs were enriched in this run.
- How many `pending` stubs remain.
- If context is filling up: *"N stubs remain. Please run `/scaffold-knowledge` again in a new session to continue enrichment (Phase 2)."*

// turbo
`git_checkpoint(message="Enrich KI stubs: batch")`

---

## Phase 3 — Finalize (when `ki_scaffold_status` shows 0 pending)

> [!IMPORTANT]
> Run this phase **only once**, after all stubs are enriched (`ki_scaffold_status()` shows no 🚧 Pending entries).

### Step 3.1 — Finalize Scaffold KIs

Removes `<!-- scaffold: enriched -->` markers from all enriched KIs and updates their summaries in `doc_config.json` from the Overview text.

// turbo
`ki_finalize_scaffolds()`

Preview without changes:
`ki_finalize_scaffolds(dry_run=true)`

### Step 3.2 — Wire Up Dependencies

Populates the `Related KIs` section in every KI by analyzing code imports.

// turbo
`analyze_all_dependencies()`

### Step 3.3 — Rebuild Directory Index

// turbo
`generate_dir_index()`

### Step 3.4 — Final Git Checkpoint

// turbo
`git_checkpoint(message="Knowledge base bootstrapped and finalized")`

---

## What's Next?

| Next Step | When |
|-----------|------|
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
