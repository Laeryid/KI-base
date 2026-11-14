---
name: ki-manager-expand-knowledge
description: Iteratively add new KI files for undocumented or poorly documented modules
metadata:
  author: ki-manager
  version: "1.1"
<!-- if-compact -->
allowed-tools: ki_instructions ki_read ki_search ki_tools ki_call ki_mutate
<!-- else-compact -->
allowed-tools: read_know_file write_know_file edit_know_file ki_instructions ki_read audit_coverage add_ki_to_config analyze_dependencies save_state git_checkpoint find_unmapped_files ki_split_analyze ki_split edit_doc_config ki_lint ki_sync
<!-- /if-compact -->
---

# /expand-knowledge — Expanding the Knowledge Base

Triggered when there's a need to **add new knowledge**, detail existing knowledge, or split overloaded KIs.

---

## Step 1 — Run Coverage Audit

// turbo
<!-- if-compact -->
`ki_call(tool="audit_coverage")`
<!-- else-compact -->
`audit_coverage()`
<!-- /if-compact -->

The script will output a coverage matrix, a list of Blind Spots, and density metrics.

**Completion Condition**:
Iterations can be stopped if ALL of the following conditions are met:
1. All modules in the matrix have **GREEN (✅)** status.
2. The **⚠️ Untracked Areas** section is empty.
3. No **🔥 (Complexity)** tags — overloaded KIs (>10 files).
4. No **❄️ (Low Density)** tags — documentation too brief for the code volume.

> [!TIP]
> If the conditions above are met but you have code changes, use the `/sync-knowledge` workflow.

---

## Step 2 — Select Iteration Target

Select **one** target with the highest priority in the following order:

1. ⚠️ **Blind Spots / Untracked Areas** (folders exist, contain code, but missing from audit):
   - If folder should be tracked: add to `tracked_modules` or document files.
   - If folder should NOT be audited (e.g. static assets, tests, benchmarks): ignore via
     <!-- if-compact -->
     `ki_mutate(tool="edit_doc_config", args={"section": "ignore_dirs", "action": "append", "value": "<folder_name>"})`
     <!-- else-compact -->
     `edit_doc_config(section="ignore_dirs", action="append", value="<folder_name>")`
     <!-- /if-compact -->
2. 🔴 **Critical Priority / Partial Coverage** in the matrix (uncovered code files).
3. 🔥 **Complexity Warning** (one KI covers >10 files) — goal: split into two cohesive KIs via `ki_split`.
4. ❄️ **Low Density** (KI exists but is brief relative to code volume without reaching saturation) — goal: detailing.
5. 🌾 **Medium/Low Priority** — for planned improvement.

---

## Safety & Tooling Rules
> [!NOTE]
> - `{{KI_DIR}}` (knowledge_root) is the system container. All Knowledge Items (`*.ki.md`) live strictly in `{{KI_DIR}}/knowledge/`.
> - **NEVER** write `.ki.md` files directly into `{{KI_DIR}}/` root, and **NEVER** delete `{{KI_DIR}}/knowledge/`.
> - Native file tools (`read_file`, `edit_file`) **are allowed** for inspecting and editing `.md` files inside `{{KI_DIR}}/knowledge/`.
> - After editing KI files, run `ki_sync` (or `ki_lint`) to validate structure, metadata, and references.
> 
<!-- if-compact -->
> Available `ki-manager` MCP tools for knowledge operations:
> - `ki_read` — to read existing KIs.
> - `ki_mutate(tool="write_know_file", ...)` / `edit_know_file` — optional sandboxed alternatives to native file tools.
> - `ki_mutate(tool="make_know_dir", ...)` — to create directories inside the knowledge base.
> - `ki_call(tool="ki_split_analyze", ...)` — to analyze an overloaded KI for splitting.
> - `ki_mutate(tool="ki_split", ...)` — to atomically apply KI bisection.
> - `ki_mutate(tool="ki_sync")` / `ki_call(tool="ki_lint")` — to validate and synchronize state after edits.
<!-- else-compact -->
> Available `ki-manager` MCP tools for knowledge operations:
> - `read_know_file` / `ki_read` — to read existing KIs.
> - `write_know_file` / `edit_know_file` — optional sandboxed alternatives to native file tools.
> - `make_know_dir` — to create directories inside the knowledge base.
> - `ki_split_analyze` — to analyze an overloaded KI for splitting.
> - `ki_split` — to atomically apply KI bisection.
> - `ki_sync` / `ki_lint` — to validate and synchronize state after edits.
<!-- /if-compact -->

---

## Step 3 — Research and Execution (B-Tree Workflow)

### Case A: Documenting Unmapped Files (Merge or Create)
1. Inspect unmapped files of the target module (ordered by architectural weight from core hubs to utilities):
   <!-- if-compact -->
   // turbo
   `ki_call(tool="find_unmapped_files", args={"path": "<module_path>"})`
   <!-- else-compact -->
   // turbo
   `find_unmapped_files(path="<module_path>")`
   <!-- /if-compact -->
2. Check existing KIs in this module (listed in `find_unmapped_files` output).
3. **Semantic Match (Merge)**:
   - If the file naturally belongs to an existing KI, **merge it into that KI** regardless of its current size:
     - Update the KI with `edit_know_file` (add to `Key Components` and description).
     - Update `depends_on` in `doc_config.json` via `add_ki_to_config`.
   - If no existing KI is semantically suitable: create a new focused KI (go to Step 4).
4. **Overflow Check**:
   - If after merging the KI has more than 10 files in `depends_on`, **proceed immediately to Case B (Split)**.

### Case B: Splitting Overloaded KIs (B-Tree Split on Overflow)
When a KI covers $> 10$ files (or triggers 🔥 `COMPLEXITY WARNING`):
1. Run static import bisection analysis:
   <!-- if-compact -->
   // turbo
   `ki_call(tool="ki_split_analyze", args={"ki_name": "<filename>.ki.md"})`
   <!-- else-compact -->
   // turbo
   `ki_split_analyze(ki_name="<filename>.ki.md")`
   <!-- /if-compact -->
2. The tool computes a balanced bisection (Group A vs Group B) based on internal imports and abstraction layers.
3. Prepare content for both parts, ensuring all files from the original KI are covered.
4. Apply the split atomically:
   <!-- if-compact -->
   // turbo
   `ki_mutate(tool="ki_split", args={"ki_name": "<filename>.ki.md", "target_a": {"ki_name": "...", "summary": "...", "depends_on": [...], "content": "..."}, "target_b": {"ki_name": "...", "summary": "...", "depends_on": [...], "content": "..."}})`
   <!-- else-compact -->
   // turbo
   `ki_split(ki_name="<filename>.ki.md", target_a={"ki_name": "...", "summary": "...", "depends_on": [...], "content": "..."}, target_b={"ki_name": "...", "summary": "...", "depends_on": [...], "content": "..."})`
   <!-- /if-compact -->

### Case C: Detailing (Low Density)
1. Find non-obvious points in the code: side-effects, initialization order, hidden configs.
2. Add "Non-obvious Details" and "Common Pitfalls" sections using `edit_know_file`.

---

## Step 4 — Create or Update a KI File

Write the file using `write_know_file` or `edit_know_file` (passing `rel_path="<filename>.ki.md"` automatically writes inside `{{KI_DIR}}/knowledge/`):
<!-- if-compact -->
// turbo
`ki_mutate(tool="write_know_file", args={"rel_path": "<filename>.ki.md", "content": "..."})`
<!-- else-compact -->
// turbo
`write_know_file(rel_path="<filename>.ki.md", content="...")`
<!-- /if-compact -->

**KI Structure (Standard)**:
```markdown
<!-- last_verified: YYYY-MM-DD -->
# KI: <Module Name>

## Overview
<Purpose in 1-2 sentences>

## Entry Points & Public API
- `SymbolName`: <Primary interface, factory, or entry function for external consumers>

## Key Components
| Class / Function | File | Purpose |
|---|---|---|

## Testing & Verification
- Test commands: `pytest tests/test_<module>.py`
- Test files: `tests/test_<module>.py`

## Invariants
- [MUST] <Hard constraint or architectural rule>
- [MUST NOT] <Forbidden pattern>

## Non-obvious Details
- <A fact not visible from function signatures>

## Common Pitfalls
- **<Symptom>**: <Solution>

## Related KIs
<!-- Populated by analyze_dependencies -->
```

---

## Step 5 — Registration

Register the new KI in `doc_config.json`:
<!-- if-compact -->
// turbo
`ki_mutate(tool="add_ki_to_config", args={"ki_name": "<filename>.ki.md", "description": "<Full description>", "depends_on": ["path/to/tracked/file.py"], "summary": "<Concise summary>"})`
<!-- else-compact -->
// turbo
`add_ki_to_config(ki_name="<filename>.ki.md", description="<Full description>", depends_on=["path/to/tracked/file.py"], summary="<Concise summary>")`
<!-- /if-compact -->

---

## Step 5.1 — Analyze Dependencies

Automatically identify and link related KIs based on code imports:

// turbo
<!-- if-compact -->
`ki_call(tool="analyze_dependencies", args={"ki_name": "<filename>.ki.md", "only_changed": false})`
<!-- else-compact -->
`analyze_dependencies(ki_name="<filename>.ki.md", only_changed=false)`
<!-- /if-compact -->

---

## Step 6 — Committing the State

// turbo
<!-- if-compact -->
`ki_mutate(tool="save_state")`
<!-- else-compact -->
`save_state()`
<!-- /if-compact -->

## Step 7 — Final Run Coverage Audit

// turbo
<!-- if-compact -->
`ki_call(tool="audit_coverage")`
<!-- else-compact -->
`audit_coverage()`
<!-- /if-compact -->

Updates coverage metrics and verifies that the blind spot is resolved.

## Step 8 — Synchronize & Validate (`ki_sync`)

Finalize the expansion by validating structure/metadata/references and updating `DIR_INDEX.md`, `doc_state.json`, and `AGENTS.md`:

// turbo
<!-- if-compact -->
`ki_mutate(tool="ki_sync")`
<!-- else-compact -->
`ki_sync()`
<!-- /if-compact -->

---

## Readiness Criteria (Checklist)

- [ ] `KI_*.md` created or updated in the `knowledge/` directory.
- [ ] KI registered in `doc_config.json` under the `knowledge_items` section.
- [ ] `last_verified` in the KI contains the current date.
