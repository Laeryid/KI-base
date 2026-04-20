---
description: Iteratively add new KI files for undocumented or poorly documented modules
---

# /expand-knowledge — Expanding the Knowledge Base

Triggered when there's a need to **add new knowledge**, detail existing knowledge, or split overloaded KIs.

---

## Step 1 — Run Coverage Audit

// turbo
```powershell
# Call via MCP: KnowledgeManager.audit_coverage()
```

The script will output a coverage matrix, a list of Blind Spots, and density metrics.

**Completion Condition**:
Iterations can be stopped if ALL of the following conditions are met:
1. All modules in the matrix have **GREEN (✅)** status.
2. The **⚠️ Untracked Areas** section is empty.
3. No **🔥 (Complexity)** tags — overloaded KIs.
4. No **❄️ (Low Density)** tags — documentation too brief for the code volume.

> [!TIP]
> If the conditions above are met but you have code changes, use the `/sync-knowledge` workflow.

---

## Step 2 — Select Iteration Target

Select **one** target with the highest priority in the following order:

1. ⚠️ **Blind Spots** (folders exist, lots of code, but missing from audit) — create a new KI.
2. 🔴 **Critical Priority** in the matrix (no KI + large size).
3. 🔥 **Complexity Warning** (one KI covers >10 files) — goal: split into multiple KIs.
4. ❄️ **Low Density** (KI exists but is "empty" relative to code) — goal: detailing.
5. 🟡 **Medium/Low Priority** — for planned improvement.

---

## Step 3 — Research and Analysis

### Case A: New Module or Blind Spot
1. Read the files in the directory.
2. Define the **Purpose** and **Key Components**.
3. Check dependencies (who calls this module).

### Case B: Splitting (Complexity)
1. Read the current KI.
2. Identify logical groups of files (e.g., `core logic`, `models`, `utils`).
3. Prepare the structure for new, more focused KIs.

### Case C: Detailing (Low Density)
1. Find non-obvious points in the code: side-effects, initialization order, hidden configs.
2. Add "Non-obvious Details" and "Common Pitfalls" sections.

---

## Step 4 — Create or Update a KI File

**KI Structure (Standard)**:
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

---

## Step 5 — Registration

1. **doc_config.json**: Register the new KI or update `depends_on` for existing ones.

---

## Step 6 — Committing the State

// turbo
```powershell
# Call via MCP: KnowledgeManager.save_state()
```

## Step 7 — Synchronizing AGENTS.md

// turbo
```powershell
# Call via MCP: KnowledgeManager.sync_agents_md()
```

---

## Readiness Criteria (Checklist)

- [ ] `KI_*.md` created or updated in the `knowledge/` directory.
- [ ] KI registered in `doc_config.json` under the `knowledge_items` section.
- [ ] `last_verified` in the KI contains the current date.
- [ ] Script `sync_agents_md.py` executed without errors.
