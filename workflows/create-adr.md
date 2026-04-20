---
description: Document architectural decisions, logic transitions, or abandoned paths (ADR)
---

# /create-adr — Architectural Decision Records (ADR / Retrospective)

Triggered on user demand when it's necessary to document a significant architectural transition, fix a complex bug, or record an "erroneous path" that was abandoned. **ADRs (Architecture Decision Records) are strictly time-bound** — they reflect the trade-offs that were relevant at the moment the decision was made.

## General AI Instructions
- **Never modify old ADRs.** If a decision is revisited, create a new ADR with a reference to the old one.
- The internal structure of an ADR should be a chronological log (append-only).

## Step 0 — Discovery Phase
Before writing the document, the AI must analyze the context of recent changes to "infer" the problem independently:
1. **Git History**: Run `git log --since="3 days ago" -p` (or another reasonable period) to see code changes and commits.
2. **Analytics**: Match "fix" messages with logic changes. Look for patterns: reverted changes, data type shifts, addition of new protective mechanisms.
3. **Proposal**: Formulate a list of ADR candidates (e.g., "Abandoning FP16", "Switching to explicit Parquet schemas").
4. **Validation**: Present this list to the user. If the user approves, proceed to Step 1.

## Step 1 — Determining the Sequence Number (ID)
Analyze the file list in the `decisions/` directory using `list_dir` or `run_command` (e.g., `Get-ChildItem`).
- Find the maximum prefix `XXX_...`.
- The new ADR should have the prefix `XXX + 1` (e.g., if `001_...` exists, the new one will be `002_...`). If the directory does not exist yet, create it and start with `001_`.

## Step 2 — Writing the Document
Create a file in the `decisions/` folder named `<ID>_<short_topic_name>.md`.
The document **must** have the following structure:

```markdown
<!-- created: YYYY-MM-DD -->
# ADR <ID>: <Title>

## Context and Problem
Briefly describe what we encountered, why the old approach stopped working, and what the constraints were.

## Decisions Made and Lessons Learned
- **What was tried and didn't work:** (optional, if there was a negative experience)
- **Successful Solution (Best Practice):** The specific architectural decision or rule reached. Short and to the point.

## Impact
What will change in the project after this decision is adopted (positive and negative trade-offs).
```

## Step 3 — Registration in Configuration
Add the created file to the `knowledge_items` block of `doc_config.json` configuration with a brief summary.

## Step 4 — Knowledge Synchronization
Immediately after successful integration, suggest that the user run, or (if permitted) automatically launch the `/sync-knowledge` workflow to update `DIR_INDEX` and `AGENTS.md`.
