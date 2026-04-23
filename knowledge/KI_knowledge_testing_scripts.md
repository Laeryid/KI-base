<!-- last_verified: 2026-04-23 -->
# KI: Knowledge Testing - Scripts & Helpers

## Overview
Detailed description of tests for auxiliary initialization and synchronization scripts of the knowledge system. These tests verify environment setup, instruction file updates (`AGENTS.md`), and `.gitignore` configuration.

## Key Components
| Class / Function | File | Purpose |
|---|---|---|
| `test_init_ki_system.py` | `.know/tests/test_init_ki_system.py` | Verification of venv detection, `.gitignore` updates (idempotency), and addition of sections to `AGENTS.md`. |
| `test_sync_and_add_ki.py` | `.know/tests/test_sync_and_add_ki.py` | Testing of the KI table synchronization in `AGENTS.md` and registration of new KIs in `doc_config.json`. |
| `test_ki_utils.py` | `.know/tests/test_ki_utils.py` | Validation of knowledge root discovery logic and configuration loading from various sources. |

## Non-obvious Details
- **Hardlink Support**: Tests verify the creation of hard links for workflows, which requires the source and target to be on the same physical drive.
- **Idempotency**: All file update scripts (`.gitignore`, `AGENTS.md`) are designed such that repeated runs do not duplicate data.

## Common Pitfalls
- **Python Path**: Scripts in tests often add `../scripts` to `sys.path`. Changing the folder structure may cause tests to fail to find modules.
- **Venv Detection**: `detect_venv` searches for standard names (`.venv`, `venv`). If a non-standard name is used, tests may fail or use the system interpreter.

## Related KIs
