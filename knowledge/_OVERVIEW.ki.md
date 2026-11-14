<!-- last_verified: 2026-11-14 -->
# KI: KI-base / ki-manager Project Overview

## Overview
`ki-manager` is a standalone JSON-RPC 2.0 MCP server and CLI toolkit written in Python for managing modular Knowledge Items (`*.ki.md`) and Architecture Decision Records (`decisions/*.md`). It provides Just-in-Time invariant retrieval (`ki_context_for`), lifecycle management, deterministic validation (`ki_lint`), single-call synchronization (`ki_sync`), and optional declarative hooks (`ki-manager install-hooks`, `ki-manager hook`).

## Entry Points & Public API
- `src/ki_manager/server.py` (`main`): MCP stdio loop + CLI subcommand pass-through.
- `src/ki_manager/cli.py` (`main`): CLI commands (`install-skills`, `install-hooks`, `hook`, `lint`).
- `src/ki_manager/scripts/ki_context.py` (`get_context_for`): Just-in-Time invariant extraction with deduplication cache.
- `src/ki_manager/scripts/ki_lint.py` (`lint_knowledge_base`): Structure, lifecycle status, and `depends_on` linter.
- `src/ki_manager/scripts/ki_hooks.py` (`install_harness_hooks`, `handle_pre_edit`, `handle_stop_lint`): Declarative JSON harness engine.

## Invariants
- [MUST] Keep `scripts/` business logic independent of the MCP stdio loop in `server.py`.
- [MUST] Keep workflow instructions in `src/ki_manager/workflows/` and `GLOBAL_INSTRUCTIONS` compatible with both `full` and `compact` tool modes (`<!-- if-compact -->` / `<!-- else-compact -->`).
- [MUST] Use `.venv\Scripts\python.exe` and `.venv\Scripts\pytest.exe` for running Python and tests in this workspace (tests isolate `Path.home()` via `tests/conftest.py`).

## Common Pitfalls
- **Windows `stdio` flushing**: Never wrap `sys.stdout` with `codecs.getwriter`; native Python stdout handles JSON-RPC flushes cleanly on Windows pipes.
- **`.lstrip("./")` on hidden folders**: Never use `.lstrip("./")` on `.ki-base/` or `.know/` paths because `lstrip` strips a character set, removing leading dots.

## Related KIs
- [KI_knowledge_system.md](KI_knowledge_system.md)
- [KI_knowledge_mcp.md](KI_knowledge_mcp.md)
