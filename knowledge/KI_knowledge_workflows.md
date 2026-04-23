<!-- last_verified: 2026-04-21 -->
# KI: Knowledge Management Workflows

## Overview
Description of standard workflows for maintaining and expanding the Pocket Team knowledge base. These processes automate routine tasks and ensure documentation consistency.

## Key Components

| Workflow | File | Purpose |
|---|---|---|
| `/expand-knowledge` | `.know/workflows/expand-knowledge.md` | Iterative expansion of the knowledge base to cover "blind spots" and refine details. |
| `/sync-knowledge` | `.know/workflows/sync-knowledge.md` | Synchronization of indexes, update of dependencies, and actualization of agent instructions. |

## Operational Details
- **Hard Links Architecture**: Workflow templates are stored in `.know/workflows/`. During system initialization, the `init_ki_system.py` script creates hard links to these files in the `.agent/workflows/` directory. This allows them to be used as executable workflows while maintaining centralized management within the knowledge base.
- **Workflow Triggers**: 
    - Use `/expand-knowledge` when modules with low knowledge density (❄️ icon) or missing KIs (🔴 icon) are detected.
    - Use `/sync-knowledge` after any changes in project structure or when adding new tools.

## Common Pitfalls
- **Broken Links (Windows)**: When moving the project between drives, hard links may turn into regular copies or break. Solution: rerun `init_ki_system.py`.
- **Manual Edits**: Changes made directly in `.agent/workflows/` may be overwritten or fail to be included in the knowledge base. Always edit the source files in `.know/workflows/`.

## Related KIs
