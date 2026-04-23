<!-- last_verified: 2026-04-22 -->
# KI: Knowledge Management Infrastructure (Core)

## Overview
The core of the Pocket Team knowledge management system. Provides technical initialization, hash calculation, coverage auditing, index generation, and MCP integration.

## Key Components
| Component | File | Purpose |
|---|---|---|
| **System Init** | `.know/scripts/init_ki_system.py` | Primary setup: workflow hard links, `.gitignore` updates, and MCP config generation. |
| **Knowledge Engine** | `.know/scripts/knowledge_engine.py` | Technical core: SHA-256 hash calculation, `mtime` filtering, and dependency mapping. |
| **KI Utils** | `.know/scripts/ki_utils.py` | Common utilities: project and knowledge base path resolution, configuration loading. |
| **Audit Provider** | `.know/scripts/audit_coverage.py` | Metric collection: Density and Complexity. |
| **Dependency Analyzer** | `.know/scripts/ki_dependency_analyzer.py` | Analysis of links between KIs based on imports in code. |
| **Module Analyzer** | `.know/scripts/analyze_module.py` | Deep coverage analysis of a specific directory or module. |
| **Unmapped Finder** | `.know/scripts/find_unmapped_files.py` | Search for project files not linked to a KI in `doc_config.json`. |
| **Index Generator** | `.know/scripts/generate_dir_index.py` | Automatic assembly of `DIR_INDEX.md` based on project structure. |
| **Agent Sync** | `.know/scripts/sync_agents_md.py` | Synchronization of rules and context in `AGENTS.md`. |
| **Knowledge MCP** | `.know/scripts/knowledge_mcp.py` | Interface for interaction via the MCP protocol with "sandbox" support. |

## Knowledge MCP Tools
The system provides the following tools via MCP (KnowledgeManager):
- **audit_coverage**: Runs a full audit.
- **sync_agents_md**: Updates instructions for agents.
- **generate_dir_index**: Rebuilds the file index.
- **check_changes**: Checks for changes in tracked files.
- **save_state**: Commits current hash states.
- **read_know_file / write_know_file**: Safe file operations within `.know`.
- **edit_know_file**: Atomic editing (text replacement) within `.know`.
- **analyze_dependencies**: Automated linking of KIs based on code.

## Technical Details
- **Path Resolution Logic**: The `ki_utils.py` utility searches for the knowledge base root (`knowledge_root`) in the following order:
    1. Command line argument `--config`.
    2. `knowledge_root` field in `ki_config.json`.
    3. Script's parent directory (standard for `.know/scripts/`).
    4. Search for the `.know` folder in current and parent directories.
- **Security Sandboxing**: The MCP server restricts access to the `.know` directory only. Attempts to go outside (`..` or absolute paths) are blocked in `validate_path`.
- **Execution Protection**: Modifying executable files (`.py`, `.exe`, `.bat`, `.sh`, etc.) via MCP write tools is prohibited.
- **Config Integrity**: Direct overwrite of `doc_config.json` via `write_know_file` is prohibited. Only partial editing (`edit_know_file`) is allowed to prevent loss of knowledge base structure.
- **mtime Optimization**: To speed up auditing, the system first checks the file modification time (`mtime`). SHA-256 hash is recalculated only if the file has physically changed on disk.
- **Forced Efficiency Injection**: The `init_ki_system.py` script automatically inserts critical rules into `AGENTS.md`: planning blocks (Affected layers), linting before saving, and prohibition of cascading asynchrony.

## Common Pitfalls
- **Stale State**: If `doc_state.json` is corrupted, false audit positives may occur. Solution: use `save_state` for forced hash synchronization.
- **Critical Config Loss**: Complete overwrite of `doc_config.json` by tools without structure validation logic (like `write_know_file`) is unacceptable. This will lead to the loss of all metadata and links. Use only `edit_know_file` or specialized scripts.
- **Python Path**: Initialization scripts attempt to automatically detect `.venv`. If multiple environments exist, ensure the correct `venv_python` is set in `ki_config.json`.
- **Encoding Issues**: On Windows, scripts use forced UTF-8 encoding in `sys.stdin/stdout`, but external calls (e.g., `find_unmapped_files`) may encounter system code page limitations when non-ASCII characters are present in filenames.

## Related KIs
