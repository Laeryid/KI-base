<!-- last_verified: 2026-04-23 -->
# KI: Knowledge MCP Server

## Overview
A Model Context Protocol (MCP) adapter providing an interface between AI agents and the project's knowledge management system via the JSON-RPC (stdio) standard.

## Key Components

| Class / Function | File | Purpose |
|---|---|---|
| `validate_path` | `knowledge_mcp.py` | Ensures security (sandboxing) by checking file paths and extensions. |
| `run_script` | `knowledge_mcp.py` | Unified execution of auxiliary Python scripts from `.know/scripts/`. |
| `METHODS` | `knowledge_mcp.py` | Registry mapping MCP tool names to internal implementation functions. |
| `main` | `knowledge_mcp.py` | Main loop for processing JSON-RPC messages from stdin/stdout. |

## Security & Sandboxing
- **Path Validation**: Any file access via MCP passes through `validate_path`. Absolute paths and parent directory transitions (`..`) are prohibited.
- **Jail Directory**: All file operations are restricted to the `.know/` root directory. Attempts to exit (Path Traversal) via `..` or absolute paths are blocked.
- **Executable Protection**: Tools like `write_know_file` and `edit_know_file` prohibit modifying files with extensions like `.py`, `.bat`, `.ps1`, `.exe`, `.sh`, etc. This prevents self-modification of server code or script injection.
- **Config Protection**: The `doc_config.json` file is protected from complete overwrite via `write_know_file`. Only partial editing via `edit_know_file` is allowed.
- **Windows UTF-8 Fix**: Forced `utf-8` encoding for stdin/stdout/stderr to ensure correct handling of non-ASCII characters in Windows.

## Available Tools
The server provides tools for:
1. **Audit**: `audit_coverage`, `find_unmapped_files`, `analyze_module`.
2. **State Management**: `save_state`, `restore_mapping`, `check_changes`.
3. **Editing**: `read_know_file`, `write_know_file`, `edit_know_file`, `make_know_dir`.
4. **Synchronization**: `sync_agents_md`, `generate_dir_index`, `analyze_dependencies`.

## Related KIs

## Non-obvious Details
- **Shadowing Python Path**: The script adds its own directory to `sys.path[0]` to import `ki_utils` and `knowledge_engine` regardless of the working environment.
- **Tool Schema Generation**: The input data schema (`inputSchema`) for tools is dynamically generated based on `DEFAULT_TOOLS` during a `tools/list` call.

## Common Pitfalls
- **Path Traversal Error**: If an agent passes a path starting with `/` or containing `..`, the server will return a `PermissionError`. Paths must be relative (e.g., `knowledge/KI_name.md`).
- **Config Overwrite**: Complete overwrite of `doc_config.json` via `write_know_file` is blocked. This is a critical configuration file; its loss would break links in the knowledge base. Use `edit_know_file` for targeted edits.
- **Binary Files**: The server is designed to work with text-based Markdown files. Attempting to read/write binary data may result in encoding errors.
