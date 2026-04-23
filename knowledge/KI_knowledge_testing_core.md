<!-- last_verified: 2026-04-21 -->
# KI: Knowledge System Core Testing

## Overview
Testing of low-level knowledge system mechanisms: the Engine, MCP proxy security, and base utilities.

## Key Components
| File | Purpose |
|---|---|
| `.know/tests/conftest.py` | Test infrastructure: `tmp_project` fixture for creating an isolated `.know` environment. |
| `.know/tests/test_knowledge_engine.py` | Validation of the base cycle: scanning -> hash calculation -> change detection. |
| `.know/tests/test_knowledge_engine_extra.py` | Extended engine tests: handling of hidden files, permissions, and large data volumes. |
| `.know/tests/test_mcp_security.py` | Testing protection against exiting the `.know` boundary (Path Traversal) and write permissions. |
| `.know/tests/test_mcp_arguments.py` | Validation of MCP tool arguments and handling of incorrect data types. |
| `.know/tests/test_edge_cases.py` | Stability testing in the absence of `doc_config.json`, empty directories, and corrupted indexes. |
| `.know/tests/test_ki_utils.py` | Tests for auxiliary functions related to markdown parsing and path operations. |

## Non-obvious Details
- **Path Isolation**: Tests explicitly override the `.know` path to avoid affecting the real project knowledge base.
- **Fixture Lifecycle**: The `tmp_project` fixture is automatically cleaned up after each test, preventing the accumulation of "dirty" state.

## Related KIs
