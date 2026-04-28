## Forced Efficiency (Anti-Hallucinations)

1. **Mandatory Planning Template**:
   Before making code changes, your initial plan (Implementation Plan) **MUST** include the following block:
   - **Affected layers**: [which subsystems are affected]
   - **Read KIs**: [LIST of files from `.know/knowledge/` which you read via `view_file` for this task]. *If the list is empty — read KIs before writing code!*
   - **KIs Constraints**: [which approaches are prohibited by current architecture]

2. **Mandatory validation (Linter)**:
   After every save or modification of a `.py` file, you **MUST** check it for syntax errors:
   ```powershell
   .venv/Scripts/python.exe -m py_compile <full_path_to_file.py>
   ```
   You are not allowed to proceed to the next steps until you fix the found `SyntaxError`.
   

## Project Navigation

- **`DIR_INDEX.md`** (`.know/DIR_INDEX.md`) — project directory tree.
- **`doc_config.json`** (`.know/doc_config.json`) — manifest of tracked artifacts and their dependencies on code.

## Knowledge Sandbox (Security)

1. **Mandatory Tooling**: For any changes inside the `.know` directory (including KIs, `doc_config.json`, and `DIR_INDEX.md`), you **MUST** use the `KnowledgeManager` MCP tools (`write_know_file`, `edit_know_file`, `make_know_dir`).
2. **Isolation**: Using general filesystem tools (`filesystem.edit_file`) for knowledge base files is **STRICTLY PROHIBITED**. This ensures the documentation process is isolated from the production code.
