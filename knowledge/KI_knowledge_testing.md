<!-- last_verified: 2026-04-23 -->
# KI: Knowledge Testing - Core & Infrastructure

## Overview
The testing infrastructure for the Pocket Team knowledge management system. Ensures validation of the Engine, auditing, and MCP integration under isolated conditions.

## Key Components
| Class / Function | File | Purpose |
|---|---|---|
| `tmp_project` fixture | `.know/tests/conftest.py` | Creates a temporary project structure with `.know`, `doc_config.json`, and dummy source code. |
| `KnowledgeEngine` tests | `.know/tests/test_knowledge_engine.py`, `test_knowledge_engine_extra.py` | Validates state capture, hash calculation, change detection, and artifact linking. |
| `Audit` tests | `.know/tests/test_audit_coverage.py`, `test_analyze_module.py` | Verifies correctness of Density calculation and identification of Blind Spots. |
| `Security` tests | `.know/tests/test_mcp_security.py` | Validates protection against Path Traversal and access restriction to the `.know` folder only. |
| `Edge Cases` | `.know/tests/test_edge_cases.py` | Tests behavior with empty files, corrupted JSON, and missing configuration. |

## Testing Strategy
- **File System Isolation**: All tests use the `tmp_path` fixture from pytest. The knowledge engine is initialized inside this temporary folder.
- **Mocking Scripts**: Tests in `scripts/` often import functionality directly by manipulating `sys.path` in `conftest.py`.
- **Validation Markers**: `@pytest.mark.positive` and `@pytest.mark.negative` markers are used to separate success scenarios from error handling.

## How to Run
To run the knowledge system tests, use the following command:
```powershell
.venv\Scripts\python.exe -m pytest .know/tests/
```

## Related KIs
