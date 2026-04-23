<!-- last_verified: 2026-04-20 -->
# KI: Architectural Decisions (ADR)

## Overview
The process of documenting significant architectural changes, technology choices, and logical transitions within the project.

## Key Components

| Component | File | Purpose |
|---|---|---|
| `/create-adr` | `.know/workflows/create-adr.md` | Workflow for creating new decision records. |
| **ADR Repository** | `.know/decisions/` | Storage for all accepted decisions in chronological order. |
| **ADR Template** | `.know/decisions/000_adr_template.md` | Standard template for documenting context, choices, and consequences. |

## Decision Process
- **Chronology**: Each decision receives an incremental ID (`001`, `002`...).
- **Immutable State**: Old ADRs are never edited. If a decision is revisited, a new ADR is created with a reference to the previous one.
- **Append-Only Log**: The internal structure of an ADR implies a sequential accumulation of context and lessons learned.

## ADR Structure
1. **Context and Problem**: Why did the old approach stop working?
2. **Decisions & Lessons**: What was tried and what was the final outcome.
3. **Impact**: How this will change project work and what are the trade-offs.

## Common Pitfalls
- **Skipping Registration**: Creating an ADR without adding it to `doc_config.json` will result in other agents not seeing this decision in their context.
- **Vague Impact**: Describing the impact without specific trade-offs makes the ADR useless for future analysis.

## Related KIs
