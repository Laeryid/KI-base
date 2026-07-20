---
description: Bootstrap a knowledge base from scratch — scaffold all modules automatically, then enrich with AI in a single flash pass
---

# /scaffold-knowledge — Knowledge Base Bootstrap

Use this workflow when starting a knowledge base for a **new project** with zero or minimal KI coverage. It replaces running `/expand-knowledge` dozens of times.

> [!TIP]
> After `/scaffold-knowledge` completes, run `/expand-knowledge` only for the highest-priority `❄️ Low Density` modules. The bulk of coverage is already established.

---

## Safety & Tooling Rules (Mandatory)

> [!IMPORTANT]
> When working with this workflow, it is **STRICTLY PROHIBITED** to use general file editing tools (e.g., `filesystem.edit_file`) for files inside the `<knowledge_root>` directory.
>
> You **MUST** use the following MCP tools from the `KnowledgeManager` server:
> - `write_know_file` — to create or fully overwrite a KI.
> - `edit_know_file` — for precise text replacement.
>
> This ensures that documentation changes remain isolated within the knowledge sandbox.

---

## ⚡ Resuming an Interrupted Run

> [!NOTE]
> This workflow is designed to survive interruptions at any point (context window exhaustion, model crash, timeout).

Before running Phases 1–2, check the current state:

1. **Read `doc_config.json`** → check `knowledge_items` section.
2. **Scan `.ki-base/knowledge/`** for files containing `<!-- scaffold: true -->`.

| What you find | What to do |
|---|---|
| No KI files at all | Start from **Phase 1** |
| Some KI files, some modules still uncovered | Re-run **Phase 2** (idempotent — skips already-created KIs) |
| All KIs exist, some still have `<!-- scaffold: true -->` | Skip to **Phase 3** directly |
| All KIs have `<!-- scaffold: enriched -->` | Skip to **Phase 4** (finalization only) |

Check scaffold status to see how many pending modules remain:
```
KnowledgeManager.ki_scaffold_status()
```

---

## Phase 1 — Coverage Snapshot

// turbo
```
KnowledgeManager.audit_coverage()
```

Record the number of uncovered modules. If **all modules are already covered (✅)**, stop — use `/expand-knowledge` or `/update-knowledge` instead.

---

## Phase 2 — Auto-Scaffold (no AI, instant, idempotent)

// turbo
```
KnowledgeManager.ki_scaffold()
```

This tool:
- Scans every **uncovered** module from `doc_config.json → coverage_settings.tracked_modules`
- Extracts symbol names via regex (classes, functions, exports) — supports Python, TS, JS, Go, with a file-list fallback for other languages
- Creates a `KI_*.md` file for each module with structure:
  - `<!-- scaffold: true -->` marker (signals incomplete KI)
  - Filled `## Key Components` table (file names + symbol names)
  - Empty `## Overview`, `## Non-obvious Details`, `## Common Pitfalls` (marked `<!-- TODO -->`)
- Registers each KI in `doc_config.json` **immediately after writing** (crash-safe: partial runs are always consistent)
- **Skips already-existing KIs** — safe to re-run after interruption

> [!NOTE]
> Scaffold KIs are **not yet useful** for AI orientation (Overview is empty). Phase 3 fixes this.

**Verify** with a second audit that the matrix is now populated:

// turbo
```
KnowledgeManager.audit_coverage()
```

All modules should now show `✅` in the KI column (but `❄️ Low Density` flags are expected — that's normal).

---

## Phase 3 — Flash Enrichment (AI, resumable)

This is the key phase. The agent reads all scaffold KIs **in one context** and fills their `Overview` sections.

### 3.0 — Determine remaining work

Before starting, collect the list of KIs marked `🚧 Pending (True)`:

// turbo
```
KnowledgeManager.ki_scaffold_status()
```

Report: **"N scaffold KIs remaining: [list of names]"**

> [!TIP]
> If resuming after interruption: KIs with `<!-- scaffold: enriched -->` are already done — skip them.
> Only `<!-- scaffold: true -->` KIs need work. The marker is the checkpoint.

### 3.1 — Batch enrichment loop

For each remaining scaffold KI, in priority order:

1. **Read the KI file** to get the list of files from the `## Key Components` table.
2. **Read the first 60 lines** of each source file listed (skip files > 50 KB — just use filename).
3. **Write a concise Overview** (2–4 sentences):
   - What this module does (purpose)
   - What it is used for (consumer perspective)
   - Key entry points if obvious
4. **Fill `Purpose` column** in the Key Components table — one short phrase per symbol.
5. **Immediately replace `<!-- scaffold: true -->`** with `<!-- scaffold: enriched -->` using `edit_know_file`.

> [!IMPORTANT]
> Step 5 (marker replacement) MUST happen **before moving to the next KI**.
> This is the checkpoint: if the agent crashes after step 5, the next run will correctly skip this KI.
>
> Use flash-quality descriptions — brevity is the goal. `Non-obvious Details` and `Common Pitfalls` can stay as `<!-- TODO -->`.

### 3.2 — Confirm completion

After the loop, verify no `<!-- scaffold: true -->` remain.

Report: **"All N scaffold KIs enriched"** or **"M KIs still pending — re-run workflow to continue"**.

If KIs are still pending (context limit hit), run this workflow again. Phase 3.0 will find the remainder automatically.

---

## Phase 4 — Finalization

// turbo
```
KnowledgeManager.generate_dir_index()
```

// turbo
```
KnowledgeManager.save_state()
```

// turbo
```
KnowledgeManager.analyze_all_dependencies()
```

// turbo
```
KnowledgeManager.git_checkpoint(message="Bootstrap knowledge base: scaffold + enrich")
```

---

## Completion Criteria

- [ ] `audit_coverage()` shows ✅ KI for every tracked module.
- [ ] All scaffold KIs have `<!-- scaffold: enriched -->` (no remaining `<!-- scaffold: true -->`).
- [ ] Every KI has a non-empty `## Overview` section.
- [ ] `DIR_INDEX.md` regenerated.
- [ ] `doc_state.json` saved.
- [ ] Git checkpoint created.

---

## What comes next

After bootstrap, run `/expand-knowledge` for:
1. `❄️ Low Density` modules with high importance — add `Non-obvious Details` and `Common Pitfalls`
2. `🔥 Complexity` KIs — split overloaded KIs into focused sub-KIs
3. Any module where you made significant code changes

The scaffold phase covers **breadth**. `/expand-knowledge` covers **depth**.
