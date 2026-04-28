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

## Workflow-driven Execution

1. **Strict Adherence**: When a user mentions a command (e.g., `/sync`, `/expand`) or asks for a complex documentation task, check `ki://workflows/` resources first. 
2. **Step-by-Step**: These workflows are your "operating system". You **MUST** follow their steps exactly as written.
3. **Execution Mode**: If you identify that a task matches a known workflow, inform the user: *"Task identified as [Workflow Name]. Starting execution according to the protocol."*
