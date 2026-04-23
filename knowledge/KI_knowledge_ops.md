<!-- last_verified: 2026-04-22 -->
# KI: Knowledge Operations

## Overview
This KI describes the internal tools and automations used to keep the project's knowledge base up to date. All scripts are located in the `.know/scripts/` directory.

## Core Tools

| Script | Description |
|---|---|
| `audit_coverage.py` | Generates a documentation coverage matrix. Checks file links with KIs. |
| `sync_agents_md.py` | Updates `AGENTS.md` based on current KIs and their descriptions. |
| `generate_dir_index.py` | Builds the directory index `DIR_INDEX.md`. |
| `ki_dependency_analyzer.py` | Analyzes imports in code and updates links between KIs. |
| `knowledge_mcp.py` | MCP server providing knowledge management tools for AI. |
| `find_unmapped_files.py` | Finds files not covered by documentation. |
| `init_ki_system.py` | Initializes knowledge infrastructure in a new project (venv, gitignore, AGENTS.md, hardlinks). |

## Implementation Details

### Knowledge MCP (knowledge_mcp.py)
Serves as a bridge between external tools (e.g., IDE or AI agents) and internal scripts. It provides a standardized set of tools, allowing agents to safely modify documentation within the `.know` sandbox.

### Coverage Control (find_unmapped_files.py)
Helps maintain 100% code coverage. The script scans the filesystem and checks the presence of each file in the `depends_on` sections of `knowledge_items` in `doc_config.json`.
- **Ignored paths**: `.git`, `__pycache__`, `node_modules`, `.venv`, `logs`, `tmp`.

### System Initialization (init_ki_system.py)
Automates the deployment of the knowledge system when cloning a repository to a new location or creating a new project from a template.
- **Venv Detection**: Automatically finds the Python interpreter path in `.venv`, `venv`, or `env`.
- **Git Isolation**: Adds rules to `.gitignore` that ignore system files in `.know` (e.g., `ki_config.json`) but keep the knowledge base itself (Markdown files) under version control.
- **Instruction Injection**: Checks `AGENTS.md` and adds missing sections: `Forced Efficiency`, `Project Navigation`, and the `Knowledge Items` header.
- **Hard Links for Workflows**: Creates hard links from `.know/workflows/` to `.agent/workflows/` (or another IDE directory). This allows the IDE to "see" workflows while keeping their management centralized in `.know`.
- **MCP Config**: Generates a JSON config for connecting `KnowledgeManager` to the IDE as an MCP server.

## Nuances and Limitations
- **Encoding**: On Windows, it is recommended to use UTF-8 encoding to avoid `UnicodeEncodeError`.
- **Dependencies**: The scripts require a configured `.venv` environment with dependencies installed from the project root.

## Useful Tips
- **Workflow**: When adding new functionality, use the `/expand-knowledge` workflow, which automatically calls these tools.
- **Audit**: If the audit shows red zones, use `find_unmapped_files.py` to find specific missing files.

## Related KIs
- [Knowledge Management Infrastructure (Core)](KI_knowledge_system.md)
- [Knowledge Dependency Analysis](KI_knowledge_dependency_analysis.md)
