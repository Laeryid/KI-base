"""
ki_manager/server.py

MCP server entry point for ki-manager.
Implements MCP stdio protocol (JSON-RPC 2.0).

Usage:
    ki-manager
    ki-manager --workspace /path/to/project
    python -m ki_manager.server
"""

import sys
import json
import os
import subprocess
import importlib.metadata
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.platform == "win32":
    # Removed codecs.getwriter because it causes OSError [Errno 22] Invalid argument on flush() with Windows pipes.
    # Force UTF-8 for native stdin/stdout on Windows to avoid surrogateescape crashes on Cyrillic.
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

# â”€â”€â”€ Package paths â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_PACKAGE_DIR = Path(__file__).parent
_SCRIPTS_DIR = _PACKAGE_DIR / "scripts"
_WORKFLOWS_DIR = _PACKAGE_DIR / "workflows"

# Make scripts and tools importable for server.py itself
_TOOLS_DIR = _PACKAGE_DIR / "tools"
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_TOOLS_DIR))
import ki_utils
import facade
import ki_search

# â”€â”€â”€ Logging â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_LOG_DIR = Path.home() / ".ki_base" / "logs"


def safe_log(msg: str):
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = _LOG_DIR / f"mcp_{os.getpid()}.log"
        with open(log_file, "a", encoding="utf-8") as lf:
            lf.write(msg + "\n")
    except Exception:
        pass


# â”€â”€â”€ Context helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_jail_dir() -> str:
    return ki_utils.get_knowledge_root()


def get_project_root() -> str:
    return ki_utils.get_project_root()


def get_doc_config() -> dict:
    return ki_utils.get_doc_config()


CURRENT_TOOL_MODE: str = os.environ.get("KI_TOOL_MODE", "full").lower()


# ─── Global Virtual Content ─────────────────────────────────────────────────

GLOBAL_INSTRUCTIONS = """\
# Global AI Instructions for ki-manager

## 1. Project Navigation
- **`DIR_INDEX.md`** (`{{KI_DIR}}/DIR_INDEX.md`) — project directory tree.
- **`doc_config.json`** (`{{KI_DIR}}/doc_config.json`) — manifest of tracked artifacts.
- All Knowledge Items (KI) live in `{{KI_DIR}}/knowledge/`.
- Architecture Decision Records (ADR) live in `{{KI_DIR}}/decisions/` or `decisions/`.
- Start here: `{{KI_DIR}}/knowledge/_OVERVIEW.ki.md`

## 2. Forced Efficiency (Anti-Hallucinations)
1. **Mandatory Planning Template**:
   Before making code changes, your initial plan (Implementation Plan) **MUST** include:
   - **Affected layers**: [which subsystems are affected]
   - **Read KIs**: [LIST of files from `{{KI_DIR}}/knowledge/` which you read for this task]. *If the list is empty — read KIs before writing code!*
   - **KIs Constraints**: [which approaches are prohibited by current architecture]

2. **Strict Adherence**:
   - Always read relevant KIs before modifying a module.
<!-- if-compact -->
   - Use `ki_search(query="...")` and `ki_read(rel_path="...")` to discover and read documentation.
   - For read-only analysis tools (`audit_coverage`, `generate_dir_index`, `ki_scaffold_status`, `git_diff_secured`), call `ki_call(tool="...")`.
   - For state-modifying operations (`git_checkpoint`, `write_know_file`, `edit_know_file`, `ki_scaffold`, `create_adr`), call `ki_mutate(tool="...", args={...})`.
   - To inspect schemas of available tools, call `ki_tools(name="<tool_name>")`.
<!-- else-compact -->
   - Use `ki_search(query="...")` and `ki_read(rel_path="...")` or `read_know_file(rel_path="...")` to explore documentation.
   - After significant changes, run `audit_coverage` via MCP.
   - Use `git_checkpoint` to save knowledge snapshots.
<!-- /if-compact -->
   
## 3. Workflow-driven Execution
1. Check `ki://workflows/` resources or MCP Prompts if the user asks for a complex documentation task.
2. These workflows are your "operating system". You **MUST** follow their steps exactly as written.
"""

def get_adr_list(project_root: str, jail: str) -> str:
    """Dynamically scan for ADR files in decisions/ or .ki-base/decisions/."""
    return ki_utils.get_adr_table(project_root, jail)


# â”€â”€â”€ Security â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_FORBIDDEN_WRITE_EXT = {".py", ".pyc", ".bat", ".ps1", ".sh", ".exe", ".cmd", ".dll"}
_FORBIDDEN_WRITE_FILES = {"doc_config.json"}  # can only be modified via dedicated tools

NO_WORKSPACE_ERROR = {
    "isError": True,
    "content": [{
        "type": "text",
        "text": (
            "âťŚ No active workspace detected.\n\n"
            "To fix, call ki_status with explicit path:\n"
            "  ki_status({\"path\": \"/absolute/path/to/project\"})\n\n"
            "Or ensure the MCP client passes workspaceUri in _meta.io.modelcontextprotocol/clientInfo."
        )
    }]
}


def validate_path(rel_path: str, is_write: bool = False) -> str:
    jail = get_jail_dir()
    if not jail:
        raise PermissionError(
            "âťŚ No active workspace detected. "
            "Call ki_status({\"path\": \"/absolute/path/to/project\"}) to set it."
        )

    normalized = ki_utils.normalize_path(rel_path, make_absolute=False)
    if not os.path.isabs(normalized):
        if normalized.startswith(".."):
            raise PermissionError(f"Access Denied: path '{rel_path}' escapes sandbox.")
        target = os.path.abspath(os.path.join(jail, normalized))
    else:
        target = os.path.abspath(normalized)

    if not os.path.normcase(target).startswith(os.path.normcase(jail)):
        raise PermissionError("Access Denied: jail breach detected.")

    if is_write:
        ext = os.path.splitext(target)[1].lower()
        if ext in _FORBIDDEN_WRITE_EXT:
            raise PermissionError(f"Access Denied: modifying {ext} files is forbidden.")
        if os.path.basename(target).lower() in _FORBIDDEN_WRITE_FILES:
            raise PermissionError(f"Access Denied: use dedicated tools to modify this file.")

    return target


# â”€â”€â”€ Script runner â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def run_script(script_name: str, args: List[str] = None) -> dict:
    """Run a bundled analysis script in the context of the active project."""
    jail = get_jail_dir()
    if not jail:
        return NO_WORKSPACE_ERROR

    script_path = _SCRIPTS_DIR / script_name
    if not script_path.exists():
        return {"isError": True, "content": [{"type": "text",
            "text": f"Error: Script '{script_name}' not found in package."}]}

    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=get_project_root(),
        env=env,
    )
    output = result.stdout + (result.stderr if result.stderr else "")
    return {"content": [{"type": "text", "text": output}]}


# â”€â”€â”€ MCP Tool Definitions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

MCP_TOOLS = [
    {
        "name": "ki_instructions",
        "description": (
            "Get workflow instructions and project rules for ki-manager. "
            "Available documents:\n"
            "- 'overview' \u2014 global AI rules and project navigation\n"
            "- 'knowledge-items' \u2014 table of registered KI files\n"
            "- 'create-adr' \u2014 workflow: document architectural decisions\n"
            "- 'expand-knowledge' \u2014 workflow: deep enrichment of KI files\n"
            "- 'scaffold-knowledge' \u2014 workflow: bulk scaffold of uncovered modules\n"
            "- 'sync-knowledge' \u2014 workflow: sync KI after code changes\n"
            "Call this before starting any documentation workflow task."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "document": {
                    "type": "string",
                    "description": "Document name from the list above (e.g. 'create-adr')"
                }
            },
            "required": ["document"]
        },
        "annotations": {
            "title": "Get KI Instructions",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        }
    },
    # â”€â”€ Initialization â”€â”€
    {
        "name": "ki_init_project",
        "description": (
            "Initialize knowledge structure in a project directory. "
            "Creates ki_config.json, doc_config.json, DIR_INDEX.md, "
            "and a starter _OVERVIEW.ki.md. Registers the project in the global registry."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Absolute path to the project root"},
                "project_name": {"type": "string", "description": "Human-readable project name (optional, defaults to folder name)"},
                "language": {"type": "string", "description": "Primary language: python, typescript, etc. (default: python)"},
                "venv_python": {"type": "string", "description": "Explicit path to venv python.exe (auto-detected if omitted)"},
                "knowledge_root": {"type": "string", "description": "Name of the knowledge directory (default: .ki-base)"},
                "config_location": {"type": "string", "description": "Where to put ki_config.json: 'root' or 'knowledge_dir' (default: knowledge_dir)"},
                "force": {"type": "boolean", "description": "Overwrite existing files (default: false)"},
            },
            "required": ["project_path"],
        },
        "annotations": {
            "title": "Initialize KI Project",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
        },
    },
    # â”€â”€ Registry â”€â”€
    {
        "name": "ki_migrate_project",
        "description": "Migrate a legacy .know/ project to the modern .ki-base/ architecture. Renames directories, updates config, and ensures _OVERVIEW.ki.md exists.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {
            "title": "Migrate Legacy Project",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
        },
    },
    {
        "name": "ki_register_project",
        "description": "Register an existing project in the global registry. Can point to ki_config.json or use inline_config (bypassing the file).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "config_path": {"type": "string", "description": "Path to ki_config.json (optional)"},
                "workspace": {"type": "string", "description": "Absolute path to the project root (optional if config_path is given)"},
                "inline_config": {"type": "object", "description": "JSON object with config settings (e.g. {'paths': {'knowledge_root': 'docs'}})"}
            },
        },
        "annotations": {
            "title": "Register Project",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "ki_list_projects",
        "description": "List all projects registered in the global KI registry.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {
            "title": "List Projects",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "ki_status",
        "description": "Check which project is active for the current workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path to check (defaults to workspace root)"}},
        },
        "annotations": {
            "title": "Project Status",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "ki_prune_registry",
        "description": "Remove projects from the registry whose directories no longer exist.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {
            "title": "Prune Registry",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
        },
    },
    # â”€â”€ Coverage & Audit â”€â”€
    {
        "name": "audit_coverage",
        "description": (
            "Run a knowledge base coverage audit. Compares tracked modules against "
            "registered KIs. Returns a coverage matrix with priority gaps. "
            "NOTE: every project folder, including utility/empty ones, must have a KI. "
            "CRITICAL AGENT RULE: After making significant architectural changes or creating "
            "new modules, you MUST run this tool to ensure documentation remains in sync."
        ),
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {
            "title": "Audit Coverage",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },

    {
        "name": "generate_dir_index",
        "description": "Generate or update .ki-base/DIR_INDEX.md with directory structure.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {
            "title": "Generate Dir Index",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "analyze_dependencies",
        "description": "Analyze Python/TS imports to update 'Related KIs' section in a KI file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ki_name": {"type": "string", "description": "KI filename to analyze"},
                "only_changed": {"type": "boolean", "description": "Only process KIs for changed files"},
            },
        },
        "annotations": {
            "title": "Analyze Dependencies",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "analyze_all_dependencies",
        "description": "Analyze all KI files and update their 'Related KIs' sections.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {
            "title": "Analyze All Dependencies",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "ki_graph_visualize",
        "description": (
            "Generate a Mermaid architecture diagram visualizing relationships between "
            "Knowledge Items (KIs) and files. "
            "Modes: 'semantic' (default, files grouped into KI subgraphs with dependency edges), "
            "'ki-only' (high-level map of KI nodes only), "
            "'coverage' (semantic map plus an 'Unmapped Files' cluster to highlight gaps)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["semantic", "ki-only", "coverage"],
                    "description": "Visualization mode (default: semantic)",
                },
                "ki_name": {
                    "type": "string",
                    "description": "Optional KI name to focus on (shows only this KI and its direct neighbors)",
                },
                "direction": {
                    "type": "string",
                    "enum": ["TD", "LR", "TB", "RL", "BT"],
                    "description": "Flowchart layout direction (default: TD)",
                },
            },
        },
        "annotations": {
            "title": "Visualize Knowledge Graph",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "find_unmapped_files",
        "description": "Find source files not covered by any KI.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Subdirectory to scan (optional)"}},
        },
        "annotations": {
            "title": "Find Unmapped Files",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "analyze_module",
        "description": "Analyze directory stats with knowledge context (file count, KI coverage, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "recursive": {"type": "boolean"},
            },
        },
        "annotations": {
            "title": "Analyze Module",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "ki_scaffold",
        "description": (
            "Generate scaffold KI files for all uncovered modules in one pass (no AI required). "
            "Extracts class/function names via regex for Python, TypeScript, JavaScript, Go; "
            "falls back to file listing for other languages. "
            "Marks generated KIs with <!-- scaffold: true --> for subsequent flash enrichment. "
            "Run this as Phase 2 of the /scaffold-knowledge workflow."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "modules": {
                    "type": "string",
                    "description": "Comma-separated module paths or labels to scaffold (default: all uncovered)",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, show what would be created without writing files (default: false)",
                },
                "force": {
                    "type": "boolean",
                    "description": "Overwrite existing KI files that have the scaffold marker (default: false)",
                },
            },
        },
        "annotations": {
            "title": "Scaffold KI Files",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
        },
    },
    {
        "name": "ki_scaffold_status",
        "description": "Print a concise status table of all scaffold KIs (pending vs enriched) by reading their headers.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {
            "title": "Scaffold Status",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "ki_finalize_scaffolds",
        "description": (
            "Finalize all enriched scaffold KI files in one pass. "
            "For each KI marked with <!-- scaffold: enriched -->: "
            "(1) removes the scaffold marker so the KI becomes a regular KI, "
            "(2) extracts the Overview text and updates the summary in doc_config.json. "
            "KIs still marked <!-- scaffold: true --> (pending) are left untouched. "
            "Run this as Phase 3 of the /scaffold-knowledge workflow, after all stubs are enriched."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, show what would change without writing files (default: false)",
                },
            },
        },
        "annotations": {
            "title": "Finalize Scaffold KIs",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "update_last_verified",
        "description": "Update the last_verified date in all KI files to today.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {
            "title": "Update Last Verified",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    # ─── Config & ADR Management ───
    {
        "name": "add_ki_to_config",
        "description": "Register a new or update an existing Knowledge Item (KI) in doc_config.json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ki_name": {
                    "type": "string",
                    "description": "Knowledge Item filename (e.g. 'KI_storage.md')"
                },
                "description": {
                    "type": "string",
                    "description": "Full description of the Knowledge Item"
                },
                "covers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of covered modules or functional areas"
                },
                "depends_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of source files/directories this KI depends on"
                },
                "summary": {
                    "type": "string",
                    "description": "Optional short summary for tables and overview"
                }
            },
            "required": ["ki_name", "description"]
        },
        "annotations": {
            "title": "Add KI To Config",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True
        }
    },
    {
        "name": "edit_doc_config",
        "description": (
            "Safely edit service sections of doc_config.json: "
            "'tracked_modules', 'artifacts', or 'coverage_settings'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": ["tracked_modules", "artifacts", "coverage_settings"],
                    "description": "Section in doc_config.json to modify"
                },
                "action": {
                    "type": "string",
                    "enum": ["set", "append", "delete"],
                    "description": "Action to perform: set, append, or delete"
                },
                "key": {
                    "type": "string",
                    "description": "Key name (for dicts) or identifier/index"
                },
                "value": {
                    "description": "Value to set or append (can be string, number, dict, or list)"
                }
            },
            "required": ["section", "action"]
        },
        "annotations": {
            "title": "Edit Doc Config",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False
        }
    },
    {
        "name": "sync_agents_md",
        "description": (
            "Synchronize Knowledge Items and ADR tables in AGENTS.md "
            "with doc_config.json and decisions/ directory. "
            "Can be disabled in ki_config.json ('sync_agents_md': false)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agents_path": {
                    "type": "string",
                    "description": "Optional explicit path to AGENTS.md"
                }
            }
        },
        "annotations": {
            "title": "Sync AGENTS.md",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True
        }
    },
    {
        "name": "create_adr",
        "description": (
            "Create a new Architecture Decision Record (ADR), automatically allocating "
            "the next sequential ID (XXX), saving the template file, registering it in "
            "doc_config.json, and updating AGENTS.md."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the architecture decision"
                },
                "status": {
                    "type": "string",
                    "default": "Accepted",
                    "description": "Status of the decision (e.g. 'Accepted', 'Proposed', 'Superseded')"
                },
                "context": {
                    "type": "string",
                    "description": "Context and problem statement"
                },
                "decision": {
                    "type": "string",
                    "description": "The decision that was made and rules adopted"
                },
                "consequences": {
                    "type": "string",
                    "description": "Consequences, trade-offs, and impact"
                },
                "topic_name": {
                    "type": "string",
                    "description": "Short slug for the filename (e.g. 'sqlite_storage')"
                }
            },
            "required": ["title", "context", "decision", "consequences", "topic_name"]
        },
        "annotations": {
            "title": "Create ADR",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False
        }
    },
    # â”€â”€ File Operations â”€â”€
    {
        "name": "read_know_file",
        "description": (
            "Read a Knowledge Item (KI) file inside the knowledge root directory. "
            "CRITICAL AGENT RULE: In this project, code is documented using ki-manager. "
            "Before planning implementation or modifying any code, you MUST use this tool "
            "to read .ki-base/knowledge/_OVERVIEW.ki.md and any other relevant KIs to "
            "understand the architecture, rules, and constraints."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"rel_path": {"type": "string", "description": "Path relative to knowledge root/"}},
            "required": ["rel_path"],
        },
        "annotations": {
            "title": "Read Knowledge Item",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "write_know_file",
        "description": "Create or overwrite a file inside knowledge root (scripts and executables are protected).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rel_path": {"type": "string", "description": "Path relative to knowledge root/"},
                "content": {"type": "string"},
            },
            "required": ["rel_path", "content"],
        },
        "annotations": {
            "title": "Write Knowledge Item",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
        },
    },
    {
        "name": "edit_know_file",
        "description": "Edit a file inside knowledge root by replacing a specific text fragment.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rel_path": {"type": "string", "description": "Path relative to knowledge root/"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["rel_path", "old_text", "new_text"],
        },
        "annotations": {
            "title": "Edit Knowledge Item",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
        },
    },
    {
        "name": "make_know_dir",
        "description": "Create a new subdirectory inside knowledge root.",
        "inputSchema": {
            "type": "object",
            "properties": {"rel_path": {"type": "string", "description": "Path relative to knowledge root/"}},
            "required": ["rel_path"],
        },
        "annotations": {
            "title": "Create Knowledge Dir",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    # â”€â”€ Git Operations â”€â”€
    {
        "name": "git_checkpoint",
        "description": "Stage and commit all knowledge root changes to git.",
        "inputSchema": {
            "type": "object",
            "properties": {"message": {"type": "string", "description": "Commit message suffix"}},
        },
        "annotations": {
            "title": "Git Checkpoint",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
        },
    },
    {
        "name": "git_restore",
        "description": "Restore a file inside .ki-base/ from a git revision.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "File path relative to knowledge root/"},
                "revision": {"type": "string", "description": "Git revision (default: HEAD)"},
            },
        },
        "annotations": {
            "title": "Git Restore",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
        },
    },
    {
        "name": "git_diff_secured",
        "description": "Get git diff for project files (sandboxed).",
        "inputSchema": {
            "type": "object",
            "properties": {"paths": {"type": "string", "description": "Comma-separated paths"}},
        },
        "annotations": {
            "title": "Git Diff",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    # â”€â”€ State â”€â”€
    {
        "name": "save_state",
        "description": "Capture and save file hash state to doc_state.json.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {
            "title": "Save State",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "restore_mapping",
        "description": "Restore doc_config.json from existing KI files.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {
            "title": "Restore Mapping",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    # ─── Search & Read ───
    facade.KI_SEARCH_TOOL,
    facade.KI_READ_TOOL,
]

_INSTRUCTIONS_TOOL = next(t for t in MCP_TOOLS if t["name"] == "ki_instructions")
COMPACT_TOOLS = [
    _INSTRUCTIONS_TOOL,
    facade.KI_SEARCH_TOOL,
    facade.KI_READ_TOOL,
    facade.KI_TOOLS_TOOL,
    facade.KI_CALL_TOOL,
    facade.KI_MUTATE_TOOL,
]

def get_mcp_prompts() -> list:
    prompts = [
        {
            "name": "knowledge-instructions",
            "description": "Agent instructions from .ki-base/AGENTS.md for the active project.",
        },
        {
            "name": "knowledge-items",
            "description": "Dynamic table of all registered Knowledge Items.",
        },
    ]
    if _WORKFLOWS_DIR.exists():
        for f in _WORKFLOWS_DIR.glob("*.md"):
            prompts.append({
                "name": f.stem,
                "description": f"KI workflow: {f.stem.replace('-', ' ').title()}",
            })
    return prompts


# â”€â”€â”€ Tool Implementations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def tool_git_checkpoint(args: dict) -> dict:
    jail = get_jail_dir()
    if not jail:
        return {"isError": True, "content": [{"type": "text", "text": "Error: No active project."}]}
    project_root = get_project_root()
    ki_base_rel = os.path.relpath(jail, project_root)
    targets = [
        os.path.join(ki_base_rel, "doc_config.json"),
        os.path.join(ki_base_rel, "ki_config.json"),
        os.path.join(ki_base_rel, "AGENTS.md"),
        os.path.join(ki_base_rel, "DIR_INDEX.md"),
        os.path.join(ki_base_rel, "knowledge"),
        os.path.join(ki_base_rel, "decisions") if os.path.exists(os.path.join(jail, "decisions")) else None,
    ]
    try:
        for t in targets:
            if t and os.path.exists(os.path.join(project_root, t)):
                subprocess.run(["git", "add", t], cwd=project_root, check=False, capture_output=True)
        status = subprocess.run(["git", "diff", "--quiet", "--cached"], cwd=project_root)
        if status.returncode == 0:
            return {"content": [{"type": "text", "text": "No changes to checkpoint."}]}
        user_msg = args.get("message", "Knowledge checkpoint")
        message = f"[AI] {user_msg}"
        result = subprocess.run(
            ["git", "commit", "-m", message, "--author=ki-manager <ki-manager@bot>"],
            cwd=project_root,
            capture_output=True, text=True, encoding="utf-8", check=True,
        )
        return {"content": [{"type": "text", "text": f"Checkpoint created: {message}\n{result.stdout}"}]}
    except subprocess.CalledProcessError as e:
        return {"isError": True, "content": [{"type": "text", "text": f"Git Error: {e.stderr or str(e)}"}]}


def tool_git_restore(args: dict) -> dict:
    target_rel = args.get("target", "doc_config.json")
    revision = args.get("revision", "HEAD")
    if revision.startswith("-") or ";" in revision or "|" in revision:
        return {"isError": True, "content": [{"type": "text", "text": "Error: suspicious revision string."}]}
    try:
        target_abs = validate_path(target_rel)
    except PermissionError as e:
        return {"isError": True, "content": [{"type": "text", "text": str(e)}]}
    try:
        result = subprocess.run(
            ["git", "checkout", revision, "--", target_abs],
            cwd=get_project_root(),
            capture_output=True, text=True, encoding="utf-8", check=True,
        )
        return {"content": [{"type": "text", "text": f"Restored '{target_rel}' from {revision}.\n{result.stdout}"}]}
    except subprocess.CalledProcessError as e:
        return {"isError": True, "content": [{"type": "text", "text": f"Git Error: {e.stderr or str(e)}"}]}


def tool_add_ki_to_config(args: dict) -> dict:
    jail = get_jail_dir()
    if not jail:
        return NO_WORKSPACE_ERROR

    ki_name = args.get("ki_name")
    description = args.get("description")
    covers = args.get("covers", [])
    depends_on = args.get("depends_on", [])
    summary = args.get("summary")

    if not ki_name or not description:
        return {"isError": True, "content": [{"type": "text", "text": "Error: 'ki_name' and 'description' are required."}]}

    if not isinstance(covers, list) or not isinstance(depends_on, list):
        return {"isError": True, "content": [{"type": "text", "text": "Error: 'covers' and 'depends_on' must be arrays."}]}

    sys.path.insert(0, str(_SCRIPTS_DIR))
    import add_ki_to_config
    try:
        msg = add_ki_to_config.add_ki(ki_name, description, covers, depends_on, summary)
        return {"content": [{"type": "text", "text": msg}]}
    except Exception as e:
        return {"isError": True, "content": [{"type": "text", "text": f"Error registering KI: {e}"}]}


def tool_edit_doc_config(args: dict) -> dict:
    jail = get_jail_dir()
    if not jail:
        return NO_WORKSPACE_ERROR

    section = args.get("section")
    action = args.get("action")
    key = args.get("key")
    value = args.get("value")

    allowed_sections = {"tracked_modules", "artifacts", "coverage_settings"}
    if section not in allowed_sections:
        return {"isError": True, "content": [{"type": "text", "text": f"Error: section '{section}' is not allowed. Allowed: {sorted(allowed_sections)}"}]}

    if action not in ("set", "append", "delete"):
        return {"isError": True, "content": [{"type": "text", "text": f"Error: action '{action}' is not supported. Use set, append, or delete."}]}

    config = ki_utils.get_doc_config()
    if not config:
        config = {}

    if section == "tracked_modules":
        # May be stored in coverage_settings.tracked_modules or root tracked_modules
        target_container = config.setdefault("coverage_settings", {})
        if "tracked_modules" not in target_container and "tracked_modules" in config:
            modules_list = config["tracked_modules"]
        else:
            modules_list = target_container.setdefault("tracked_modules", [])

        if not isinstance(modules_list, list):
            modules_list = []
            target_container["tracked_modules"] = modules_list

        if action == "append":
            if value is None:
                return {"isError": True, "content": [{"type": "text", "text": "Error: 'value' is required for append action."}]}
            modules_list.append(value)
            msg = f"Appended module to tracked_modules: {value}"
        elif action == "set":
            if key is not None:
                idx = -1
                if isinstance(key, int) or (isinstance(key, str) and key.isdigit()):
                    idx = int(key)
                else:
                    for i, item in enumerate(modules_list):
                        mod_name = item[0] if isinstance(item, list) and item else (item if isinstance(item, str) else "")
                        if mod_name == key:
                            idx = i
                            break
                if 0 <= idx < len(modules_list):
                    modules_list[idx] = value
                    msg = f"Updated tracked_modules at index {idx}: {value}"
                else:
                    modules_list.append(value)
                    msg = f"Key '{key}' not found in tracked_modules; appended {value}"
            else:
                if isinstance(value, list):
                    if "tracked_modules" in config and target_container is not config:
                        config["tracked_modules"] = value
                    else:
                        target_container["tracked_modules"] = value
                    msg = f"Set tracked_modules list to {len(value)} items"
                else:
                    return {"isError": True, "content": [{"type": "text", "text": "Error: 'value' must be a list when setting tracked_modules without key."}]}
        elif action == "delete":
            deleted = False
            if key is not None:
                if isinstance(key, int) or (isinstance(key, str) and key.isdigit()):
                    idx = int(key)
                    if 0 <= idx < len(modules_list):
                        removed = modules_list.pop(idx)
                        deleted = True
                        msg = f"Deleted tracked_module at index {idx}: {removed}"
                else:
                    for i, item in enumerate(list(modules_list)):
                        mod_name = item[0] if isinstance(item, list) and item else (item if isinstance(item, str) else "")
                        if mod_name == key:
                            modules_list.remove(item)
                            deleted = True
                            msg = f"Deleted tracked_module '{key}': {item}"
                            break
            elif value is not None:
                if value in modules_list:
                    modules_list.remove(value)
                    deleted = True
                    msg = f"Deleted tracked_module: {value}"
            if not deleted:
                return {"isError": True, "content": [{"type": "text", "text": f"Error: module key/value '{key or value}' not found in tracked_modules."}]}

    elif section == "artifacts":
        artifacts = config.setdefault("artifacts", {})
        if not isinstance(artifacts, dict):
            artifacts = {}
            config["artifacts"] = artifacts

        if action == "set":
            if not key:
                return {"isError": True, "content": [{"type": "text", "text": "Error: 'key' (artifact name) is required for set action on artifacts."}]}
            artifacts[key] = value
            msg = f"Set artifact '{key}' in doc_config.json"
        elif action == "append":
            if not key:
                return {"isError": True, "content": [{"type": "text", "text": "Error: 'key' (artifact name) is required for append action on artifacts."}]}
            art = artifacts.setdefault(key, {"description": "", "depends_on": []})
            deps = art.setdefault("depends_on", [])
            if isinstance(value, list):
                for v in value:
                    if v not in deps:
                        deps.append(v)
            elif value is not None:
                if value not in deps:
                    deps.append(value)
            msg = f"Appended dependencies to artifact '{key}'"
        elif action == "delete":
            if not key:
                return {"isError": True, "content": [{"type": "text", "text": "Error: 'key' is required for delete action on artifacts."}]}
            if key in artifacts:
                del artifacts[key]
                msg = f"Deleted artifact '{key}' from doc_config.json"
            else:
                return {"isError": True, "content": [{"type": "text", "text": f"Error: artifact '{key}' not found in doc_config.json."}]}

    elif section == "coverage_settings":
        settings = config.setdefault("coverage_settings", {})
        if not isinstance(settings, dict):
            settings = {}
            config["coverage_settings"] = settings

        if action == "set":
            if key:
                settings[key] = value
                msg = f"Set coverage_settings['{key}'] = {value}"
            elif isinstance(value, dict):
                settings.update(value)
                msg = f"Updated coverage_settings with {list(value.keys())}"
            else:
                return {"isError": True, "content": [{"type": "text", "text": "Error: 'key' or dict 'value' is required for set action on coverage_settings."}]}
        elif action == "append":
            if not key:
                return {"isError": True, "content": [{"type": "text", "text": "Error: 'key' is required for append action on coverage_settings."}]}
            target_list = settings.setdefault(key, [])
            if isinstance(target_list, list):
                if isinstance(value, list):
                    target_list.extend(value)
                elif value is not None:
                    target_list.append(value)
                msg = f"Appended to coverage_settings['{key}']"
            else:
                return {"isError": True, "content": [{"type": "text", "text": f"Error: coverage_settings['{key}'] is not a list."}]}
        elif action == "delete":
            if not key:
                return {"isError": True, "content": [{"type": "text", "text": "Error: 'key' is required for delete action on coverage_settings."}]}
            if key in settings:
                del settings[key]
                msg = f"Deleted coverage_settings['{key}']"
            else:
                return {"isError": True, "content": [{"type": "text", "text": f"Error: key '{key}' not found in coverage_settings."}]}

    ki_utils.save_doc_config(config)
    return {"content": [{"type": "text", "text": msg}]}


def tool_sync_agents_md(args: dict) -> dict:
    jail = get_jail_dir()
    if not jail:
        return NO_WORKSPACE_ERROR

    sys.path.insert(0, str(_SCRIPTS_DIR))
    import sync_agents_md
    msg = sync_agents_md.sync_agents_md(args.get("agents_path"))
    return {"content": [{"type": "text", "text": msg}]}


def tool_create_adr(args: dict) -> dict:
    jail = get_jail_dir()
    project_root = get_project_root()
    if not jail or not project_root:
        return NO_WORKSPACE_ERROR

    title = args.get("title", "").strip()
    status = args.get("status", "Accepted").strip()
    context = args.get("context", "").strip()
    decision = args.get("decision", "").strip()
    consequences = args.get("consequences", "").strip()
    topic_name = args.get("topic_name", "").strip()

    if not title or not topic_name:
        return {"isError": True, "content": [{"type": "text", "text": "Error: 'title' and 'topic_name' are required."}]}

    import re
    topic_slug = re.sub(r"[^\w\-]+", "_", topic_name).strip("_").lower()

    decisions_candidates = ki_utils.get_decisions_dirs(project_root, jail)
    target_dir = None
    for d in decisions_candidates:
        if os.path.exists(d):
            target_dir = d
            break
    if not target_dir:
        target_dir = os.path.join(project_root, "decisions")
        os.makedirs(target_dir, exist_ok=True)

    max_num = 0
    if os.path.exists(target_dir):
        for f in os.listdir(target_dir):
            m = re.match(r"^(\d+)", f)
            if m:
                num = int(m.group(1))
                if num > max_num:
                    max_num = num

    next_id = f"{max_num + 1:03d}"
    adr_filename = f"{next_id}_{topic_slug}.md"
    adr_abs_path = os.path.join(target_dir, adr_filename)

    import datetime
    today = datetime.date.today().isoformat()

    adr_content = f"""<!-- created: {today} -->
<!-- status: {status} -->
# ADR {next_id}: {title}

**Status**: {status}  
**Date**: {today}  

## Context and Problem
{context}

## Decisions Made
{decision}

## Consequences
{consequences}
"""
    with open(adr_abs_path, "w", encoding="utf-8") as f:
        f.write(adr_content)

    rel_doc_path = os.path.relpath(adr_abs_path, jail).replace("\\", "/")
    if rel_doc_path.startswith(".."):
        rel_doc_path = os.path.relpath(adr_abs_path, project_root).replace("\\", "/")

    sys.path.insert(0, str(_SCRIPTS_DIR))
    import add_ki_to_config
    reg_msg = add_ki_to_config.add_ki(
        ki_name=rel_doc_path,
        description=f"ADR {next_id}: {title} ({status})",
        covers=["Architecture Decisions"],
        depends_on=[],
        summary=f"ADR {next_id}: {title}"
    )

    import sync_agents_md
    sync_res = sync_agents_md.sync_agents_md()

    return {
        "content": [{
            "type": "text",
            "text": f"Created ADR {adr_filename} at {adr_abs_path}\n{reg_msg}\n{sync_res}"
        }]
    }


def tool_read_file(args: dict) -> Any:
    """Read a Knowledge Item or ADR file with optional section filtering and character limit."""
    rel_path = args.get("rel_path", "").strip()
    if not rel_path:
        return "Error: 'rel_path' is required."

    project_root = get_project_root()
    jail = get_jail_dir()

    target = None
    norm = ki_utils.normalize_path(rel_path, make_absolute=False)
    base_name = os.path.basename(norm)

    # 1. Try resolving within jail (knowledge root from config, default .ki-base)
    if jail:
        # 1a. Direct path inside jail
        try:
            cand = validate_path(norm)
            if os.path.exists(cand) and os.path.isfile(cand):
                target = cand
        except Exception:
            target = None

        # 1b. Try inside jail/knowledge/ (standard structure: <jail>/knowledge/<file>)
        if not target:
            try:
                cand = validate_path(os.path.join("knowledge", norm))
                if os.path.exists(cand) and os.path.isfile(cand):
                    target = cand
            except Exception:
                target = None

        # 1c. If rel_path starts with the knowledge_root folder name itself (e.g. '.ki-base/...' or 'knowledge/...'),
        # strip the prefix and resolve inside jail
        if not target and project_root:
            rel_to_proj = os.path.relpath(jail, project_root).replace("\\", "/")
            if norm.startswith(rel_to_proj + "/"):
                sub_path = norm[len(rel_to_proj) + 1:]
                try:
                    cand = validate_path(sub_path)
                    if os.path.exists(cand) and os.path.isfile(cand):
                        target = cand
                except Exception:
                    pass
                if not target:
                    try:
                        cand = validate_path(os.path.join("knowledge", sub_path))
                        if os.path.exists(cand) and os.path.isfile(cand):
                            target = cand
                    except Exception:
                        pass

    # 2. Try resolving ADR or path relative to project_root
    if not target and project_root:
        candidates = ki_utils.get_decisions_dirs(project_root, jail)
        # Check by basename in decisions dirs
        for d in candidates:
            cand_p = os.path.abspath(os.path.join(d, base_name))
            if os.path.exists(cand_p) and cand_p.endswith(".md") and os.path.isfile(cand_p):
                target = cand_p
                break
        if not target:
            # Check relative to project root, ensuring it is within decisions or jail
            cand_p = os.path.abspath(os.path.join(project_root, norm))
            if os.path.exists(cand_p) and cand_p.endswith(".md") and os.path.isfile(cand_p):
                valid_prefixes = candidates + ([jail] if jail else [])
                for vp in valid_prefixes:
                    if os.path.normcase(cand_p).startswith(os.path.normcase(vp)):
                        target = cand_p
                        break

    # 3. Fallback: Search by basename in jail (knowledge root) and its subfolders
    if not target and jail and os.path.exists(jail):
        for root, _, files in os.walk(jail):
            if base_name in files:
                cand_p = os.path.abspath(os.path.join(root, base_name))
                if cand_p.endswith(".md") and os.path.isfile(cand_p):
                    target = cand_p
                    break

    if not target or not os.path.exists(target):
        return f"File not found: '{rel_path}'."

    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return f"Error reading file '{rel_path}': {e}"

    section = args.get("section")
    if section:
        sec_content = facade.extract_markdown_section(content, section)
        if sec_content is None:
            return f"Section '{section}' not found in '{rel_path}'."
        content = sec_content

    max_chars = args.get("max_chars")
    if max_chars is not None:
        try:
            mc = int(max_chars)
            if mc > 0 and len(content) > mc:
                content = content[:mc] + f"\n\n... [truncated to {mc} characters]"
        except (ValueError, TypeError):
            pass

    return content


# ─── Tool Dispatcher ─────────────────────────────────────────────────────────

def handle_tool_call(name: str, args: dict) -> Any:
    try:
        if name == "ki_instructions":
            doc = args.get("document", "")
            know_name = os.path.basename(ki_utils.get_knowledge_root()) or ".ki-base"
            if doc == "overview":
                return facade.render_instruction(GLOBAL_INSTRUCTIONS, CURRENT_TOOL_MODE, know_name)
            elif doc == "knowledge-items":
                return f"Knowledge Items for this project:\n\n{ki_utils.get_ki_list_table()}"
            else:
                wf_path = _WORKFLOWS_DIR / f"{doc}.md"
                if wf_path.exists():
                    with open(wf_path, "r", encoding="utf-8") as f:
                        raw = f.read()
                        return facade.render_instruction(raw, CURRENT_TOOL_MODE, know_name)
                else:
                    available = [p.stem for p in _WORKFLOWS_DIR.glob("*.md")] if _WORKFLOWS_DIR.exists() else []
                    return (
                        f"Unknown document: '{doc}'.\n"
                        f"Available: overview, knowledge-items, {', '.join(available)}"
                    )

        # â”€â”€ Init â”€â”€
        if name == "ki_init_project":
            sys.path.insert(0, str(_PACKAGE_DIR / "tools"))
            from scaffold import init_project
            return init_project(args)

        # â”€â”€ Registry â”€â”€
        if name == "ki_migrate_project":
            return scaffold.migrate_project(str(get_project_root()))
        if name == "ki_register_project":
            config_path = args.get("config_path", "")
            # Accept directory too
            if config_path and os.path.isdir(ki_utils.normalize_path(config_path)):
                config_path = os.path.join(ki_utils.normalize_path(config_path), "ki_config.json")
            ok, msg = ki_utils.register_project(config_path)
            return msg
        if name == "ki_list_projects":
            reg = ki_utils.load_registry()
            if not reg["projects"]:
                return "No projects registered."
            return "\n".join(f"- {v['name']}: {k}" for k, v in reg["projects"].items())
        if name == "ki_status":
            match = ki_utils.find_project_by_cwd(args.get("path"))
            if match:
                loc = get_jail_dir() or match.get("workspace", "")
                return f"Active: {match['name']} at {loc}"
            return "No project active for current workspace."
        if name == "ki_prune_registry":
            reg = ki_utils.load_registry()
            before = len(reg["projects"])
            reg["projects"] = {k: v for k, v in reg["projects"].items()
                               if os.path.exists(v["config_path"])}
            ki_utils.save_registry(reg)
            return f"Pruned {before - len(reg['projects'])} stale project(s)."

        # â”€â”€ Coverage / Analysis â”€â”€
        if name == "audit_coverage":
            return run_script("audit_coverage.py")

        if name == "generate_dir_index":
            return run_script("generate_dir_index.py")
        if name == "update_last_verified":
            import datetime, glob, re as re_mod
            jail = get_jail_dir()
            if not jail: return "Error: No project."
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            count = 0
            for filepath in glob.glob(os.path.join(jail, "knowledge", "*.md")):
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                new_content = re_mod.sub(r'^(last_verified:\s*)"?\d{4}-\d{2}-\d{2}"?', rf'\g<1>"{today}"', content, flags=re_mod.MULTILINE)
                if new_content != content:
                    import tempfile
                    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(filepath), text=True)
                    try:
                        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                            f.write(new_content)
                        os.replace(tmp_path, filepath)
                        count += 1
                    except Exception:
                        if os.path.exists(tmp_path): os.remove(tmp_path)
            return f"Updated last_verified in {count} files."
        if name == "analyze_all_dependencies":
            return run_script("ki_dependency_analyzer.py", ["--all"])
        if name == "analyze_dependencies":
            ki_name = args.get("ki_name")
            only_changed = args.get("only_changed", False)
            cmd_args = []
            if ki_name:
                cmd_args += ["--ki", ki_name]
            if only_changed:
                cmd_args.append("--changed")
            if not cmd_args:
                return {"isError": True, "content": [{"type": "text",
                    "text": "Error: provide ki_name or only_changed=true"}]}
            return run_script("ki_dependency_analyzer.py", cmd_args)
        if name == "ki_graph_visualize":
            cmd_args = []
            if args.get("mode"):
                cmd_args += ["--mode", args["mode"]]
            if args.get("ki_name"):
                cmd_args += ["--ki", args["ki_name"]]
            elif args.get("ki"):
                cmd_args += ["--ki", args["ki"]]
            if args.get("direction"):
                cmd_args += ["--direction", args["direction"]]
            return run_script("ki_graph_visualize.py", cmd_args)
        if name == "find_unmapped_files":
            return run_script("find_unmapped_files.py", [args.get("path", ".")])
        if name == "analyze_module":
            cmd_args = [args.get("path", ".")]
            if args.get("recursive"):
                cmd_args.append("--recursive")
            return run_script("analyze_module.py", cmd_args)
        if name == "ki_scaffold":
            cmd_args = []
            if args.get("dry_run"):
                cmd_args.append("--dry-run")
            if args.get("modules"):
                cmd_args += ["--modules", args["modules"]]
            if args.get("force"):
                cmd_args.append("--force")
            return run_script("generate_ki_scaffolds.py", cmd_args)
        if name == "ki_scaffold_status":
            return run_script("generate_ki_scaffolds.py", ["--status"])
        if name == "ki_finalize_scaffolds":
            cmd_args = []
            if args.get("dry_run"):
                cmd_args.append("--dry-run")
            return run_script("finalize_ki_scaffolds.py", cmd_args)

        # ─── Config & ADR Management ───
        if name == "add_ki_to_config":
            return tool_add_ki_to_config(args)
        if name == "edit_doc_config":
            return tool_edit_doc_config(args)
        if name == "sync_agents_md":
            return tool_sync_agents_md(args)
        if name == "create_adr":
            return tool_create_adr(args)

        # ─── File Ops ───
        if name == "read_know_file":
            with open(validate_path(args["rel_path"]), "r", encoding="utf-8") as f:
                return f.read()
        if name == "write_know_file":
            p = validate_path(args["rel_path"], is_write=True)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            import tempfile
            fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(p), text=True)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                    f.write(args["content"])
                os.replace(tmp_path, p)
            except Exception as e:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise e
            return "File written."
        if name == "edit_know_file":
            p = validate_path(args["rel_path"], is_write=True)
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            old_text = args["old_text"].replace("\r\n", "\n")
            new_text = args["new_text"].replace("\r\n", "\n")
            if old_text not in content:
                return "Error: old_text not found in file."
            with open(p, "w", encoding="utf-8") as f:
                f.write(content.replace(old_text, new_text, 1))
            return "File edited."
        if name == "make_know_dir":
            os.makedirs(validate_path(args["rel_path"]), exist_ok=True)
            return "Directory created."

        # â”€â”€ Git â”€â”€
        if name == "git_checkpoint":
            return tool_git_checkpoint(args)
        if name == "git_restore":
            return tool_git_restore(args)
        if name == "git_diff_secured":
            paths = args.get("paths", "").split(",") if args.get("paths") else []
            return run_script("git_diff_secured.py", paths)

        # â”€â”€ State â”€â”€
        if name in ("save_state", "restore_mapping"):
            jail = get_jail_dir()
            sys.path.insert(0, str(_SCRIPTS_DIR))
            from knowledge_engine import KnowledgeEngine
            ke = KnowledgeEngine(get_project_root(), os.path.basename(jail))
            if name == "restore_mapping":
                return ke.restore_mapping()
            return str(ke.save_state(ke.capture_full_state()))

        # ─── Search & Read ───
        if name == "ki_search":
            query = args.get("query", "").strip()
            scope = args.get("scope", "all")
            limit = int(args.get("limit", 10))
            res = ki_search.search_knowledge(query, project_root=get_project_root(), scope=scope, limit=limit)
            return json.dumps(res, ensure_ascii=False, indent=2)

        if name == "ki_read":
            return tool_read_file(args)

        # ─── Facade Dispatchers & Catalog ───
        if name == "ki_tools":
            tool_name = args.get("name")
            group_name = args.get("group")
            if tool_name:
                tools_map = {t["name"]: t for t in MCP_TOOLS}
                for ct in COMPACT_TOOLS:
                    tools_map[ct["name"]] = ct
                if tool_name in tools_map:
                    return json.dumps(tools_map[tool_name], ensure_ascii=False, indent=2)
                return f"Tool '{tool_name}' not found."
            return facade.format_tools_catalog(MCP_TOOLS, group_filter=group_name)

        if name in ("ki_call", "ki_mutate"):
            target_tool = args.get("tool", "").strip()
            target_args = args.get("args")
            if target_args is None:
                target_args = {}
            if not isinstance(target_args, dict):
                return "Error: 'args' parameter must be an object/dict."
            if not target_tool:
                return "Error: 'tool' parameter is required."
            if target_tool in ("ki_call", "ki_mutate"):
                return "Cannot nest dispatcher calls."

            tools_map = {t["name"]: t for t in MCP_TOOLS}
            for ct in COMPACT_TOOLS:
                tools_map[ct["name"]] = ct

            if target_tool not in tools_map:
                return f"Unknown tool: '{target_tool}'. Use ki_tools() to view available tools."

            tool_def = tools_map[target_tool]
            is_ro = tool_def.get("annotations", {}).get("readOnlyHint", False)

            if name == "ki_call" and not is_ro:
                return (
                    f"Tool '{target_tool}' is state-modifying and cannot be called via ki_call. "
                    f"Use ki_mutate(tool='{target_tool}', args=...) instead."
                )
            if name == "ki_mutate" and is_ro:
                return (
                    f"Tool '{target_tool}' is read-only. "
                    f"Use ki_call(tool='{target_tool}', args=...) instead."
                )

            valid, err_msg = facade.validate_args_against_schema(tool_def.get("inputSchema", {}), target_args)
            if not valid:
                schema_json = json.dumps(tool_def.get("inputSchema", {}), ensure_ascii=False, indent=2)
                return f"Invalid arguments for '{target_tool}': {err_msg}\nRequired Schema:\n{schema_json}"

            return handle_tool_call(target_tool, target_args)

        return f"Unknown tool: {name}"

    except Exception as e:
        return f"Error in {name}: {str(e)}"


# â”€â”€â”€ MCP Main Loop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _write_ide_instructions() -> None:
    """Write instructions.md to known IDE MCP config directories on startup.

    Supported IDEs / AI tools:
      - Antigravity (Google): ~/.gemini/antigravity-cli/mcp/ki-manager/
      - Cursor:               ~/.cursor/mcp/ki-manager/
      - Windsurf:             ~/.windsurf/mcp/ki-manager/
      - Claude Desktop:       ~/Library/Application Support/Claude/mcp/ki-manager/  (macOS)
    """
    home = Path.home()
    candidates = [
        home / ".gemini" / "antigravity-cli" / "mcp" / "ki-manager",
        home / ".cursor" / "mcp" / "ki-manager",
        home / ".windsurf" / "mcp" / "ki-manager",
        home / "Library" / "Application Support" / "Claude" / "mcp" / "ki-manager",
    ]
    content = facade.render_instruction(GLOBAL_INSTRUCTIONS, CURRENT_TOOL_MODE)
    tools_to_write = COMPACT_TOOLS if CURRENT_TOOL_MODE == "compact" else MCP_TOOLS
    for target_dir in candidates:
        # Only write if the parent MCP folder already exists (IDE is installed)
        if target_dir.parent.parent.exists():
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                instructions_path = target_dir / "instructions.md"
                instructions_path.write_text(content, encoding="utf-8")
                safe_log(f"Wrote instructions.md → {instructions_path}")

                # Sync tool schema JSON files if target is an IDE mcp tool directory
                for tool in tools_to_write:
                    try:
                        tool_file = target_dir / f"{tool['name']}.json"
                        schema_data = {
                            "name": tool["name"],
                            "description": tool["description"],
                            "parameters": tool.get("inputSchema", {})
                        }
                        tool_file.write_text(json.dumps(schema_data, indent=2, ensure_ascii=False), encoding="utf-8")
                    except Exception as te:
                        safe_log(f"Could not write tool schema {tool['name']}.json: {te}")
            except Exception as e:
                safe_log(f"Could not write instructions.md to {target_dir}: {e}")


def _extract_workspace_from_meta(params: dict) -> Optional[str]:
    """ĐĐ·Đ˛Đ»ĐµĐşĐ°ĐµŃ‚ workspace URI Đ¸Đ· _meta Đ˝ĐľĐ˛ĐľĐłĐľ ĐżŃ€ĐľŃ‚ĐľĐşĐľĐ»Đ° (2026-07-28)."""
    meta = params.get("_meta", {})
    client_info = meta.get("io.modelcontextprotocol/clientInfo", {})
    return client_info.get("workspaceUri") or client_info.get("rootUri")


def main():
    # Apply --workspace early so registry lookup works
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--workspace", type=str)
    parser.add_argument("--tool-mode", type=str, choices=["full", "compact"], default=None)
    known, _ = parser.parse_known_args()
    if known.workspace:
        ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(known.workspace)
        
    global CURRENT_TOOL_MODE
    tool_mode = (known.tool_mode or os.environ.get("KI_TOOL_MODE", "full")).lower()
    if tool_mode not in ("full", "compact"):
        tool_mode = "full"
    CURRENT_TOOL_MODE = tool_mode

    safe_log(f"ki-manager MCP server started (PID: {os.getpid()}, tool-mode: {tool_mode})")
    _write_ide_instructions()

    while True:
        line = sys.stdin.readline()
        if not line:
            break

        safe_log(f"REQ: {line.strip()}")
        rid = None

        try:
            req = json.loads(line)

            # Intercept our own roots/list response
            if req.get("id") == "get_roots":
                roots = req.get("result", {}).get("roots", [])
                if roots:
                    root_uri = roots[0].get("uri")
                    if root_uri:
                        ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(root_uri)
                        safe_log(f"SET workspace via roots/list: {ki_utils.ACTIVE_WORKSPACE_PATH}")
                continue

            rid = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            # ĐťĐľĐ˛Ń‹Đą ĐżŃ€ĐľŃ‚ĐľĐşĐľĐ»: Đ¸Đ·Đ˛Đ»ĐµĐşĐ°ĐµĐĽ workspace Đ¸Đ· _meta ĐżŃ€Đ¸ ĐşĐ°Đ¶Đ´ĐľĐĽ Đ·Đ°ĐżŃ€ĐľŃĐµ
            if not ki_utils.ACTIVE_WORKSPACE_PATH:
                _ws = _extract_workspace_from_meta(params)
                if _ws:
                    ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(_ws)
                    safe_log(f"SET workspace via _meta: {ki_utils.ACTIVE_WORKSPACE_PATH}")

            def send(result_data):
                resp = json.dumps({"jsonrpc": "2.0", "id": rid, "result": result_data})
                safe_log(f"DEBUG: Before write RESP")
                safe_log(f"RESP: {resp}")
                sys.stdout.write(resp + "\n")
                safe_log(f"DEBUG: Before flush RESP")
                sys.stdout.flush()
                safe_log(f"DEBUG: After flush RESP")

            if method in ("initialize", "server/discover"):
                safe_log(f"DEBUG: Inside method {method}")
                # Extract workspace URI from any location in params
                root_uri = params.get("rootUri")
                if not root_uri:
                    folders = params.get("workspaceFolders") or []
                    if folders:
                        root_uri = folders[0].get("uri")
                if not root_uri:
                    def _find_uri(d):
                        if isinstance(d, dict):
                            for v in d.values():
                                r = _find_uri(v)
                                if r:
                                    return r
                        elif isinstance(d, list):
                            for v in d:
                                r = _find_uri(v)
                                if r:
                                    return r
                        elif isinstance(d, str) and (d.startswith("file://") or
                                (len(d) > 2 and d[1] == ":" and "\\" in d)):
                            return d
                    root_uri = _find_uri(params)

                safe_log(f"DEBUG: After _find_uri. root_uri={root_uri}")
                if root_uri:
                    ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(root_uri)
                    safe_log(f"SET workspace via initialize: {ki_utils.ACTIVE_WORKSPACE_PATH}")

                safe_log(f"DEBUG: Before importlib")
                try:
                    server_version = importlib.metadata.version("ki-manager")
                except importlib.metadata.PackageNotFoundError:
                    server_version = "2.0.11"
                except Exception as ex:
                    safe_log(f"DEBUG: importlib EXCEPTION: {ex}")
                    server_version = "2.0.11"
                safe_log(f"DEBUG: After importlib. version={server_version}")

                know_name = os.path.basename(ki_utils.get_knowledge_root()) or ".ki-base"
                resp = {
                    "protocolVersion": "2026-07-28" if method == "server/discover" else "2024-11-05",
                    "capabilities": {"tools": {}, "prompts": {}, "resources": {}},
                    "serverInfo": {"name": "ki-manager", "version": server_version},
                    "instructions": facade.render_instruction(GLOBAL_INSTRUCTIONS, CURRENT_TOOL_MODE, know_name),
                }
                if method == "server/discover":
                    resp["versions"] = ["2026-07-28", "2025-11-25", "2024-11-05"]
                send(resp)
                safe_log(f"DEBUG: After send() for {method}")

            elif method == "notifications/initialized":
                # Request roots from client for workspace detection
                req_roots = json.dumps({"jsonrpc": "2.0", "id": "get_roots", "method": "roots/list", "params": {}})
                safe_log(f"SEND_REQ: {req_roots}")
                sys.stdout.write(req_roots + "\n")
                sys.stdout.flush()

            elif method == "tools/list":
                tools_list = COMPACT_TOOLS if tool_mode == "compact" else MCP_TOOLS
                send({"tools": tools_list, "ttlMs": 300000, "cacheScope": "global"})

            elif method == "tools/call":
                tool_name = params["name"]
                tool_args = params.get("arguments", {})
                # Fallback: ĐżŃ€ĐľĐ±ŃĐµĐĽ Đ˛Đ·ŃŹŃ‚ŃŚ workspace Đ¸Đ· Đ°Ń€ĐłŃĐĽĐµĐ˝Ń‚ĐľĐ˛ Đ¸Đ˝ŃŃ‚Ń€ŃĐĽĐµĐ˝Ń‚Đ°
                if not ki_utils.ACTIVE_WORKSPACE_PATH:
                    _ws_arg = tool_args.get("path") or tool_args.get("project_path")
                    if _ws_arg:
                        ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(_ws_arg)
                        safe_log(f"SET workspace via tool args: {ki_utils.ACTIVE_WORKSPACE_PATH}")
                result = handle_tool_call(tool_name, tool_args)
                if isinstance(result, dict) and "content" in result:
                    send(result)
                else:
                    send({"content": [{"type": "text", "text": str(result)}]})

            elif method == "prompts/list":
                send({"prompts": get_mcp_prompts()})

            elif method == "prompts/get":
                prompt_name = params.get("name")
                know_name = os.path.basename(ki_utils.get_knowledge_root()) or ".ki-base"
                content = None
                if prompt_name == "knowledge-instructions":
                    content = facade.render_instruction(GLOBAL_INSTRUCTIONS, CURRENT_TOOL_MODE, know_name)
                elif prompt_name == "knowledge-items":
                    match = ki_utils.find_project_by_cwd() or ki_utils.ACTIVE_WORKSPACE_PATH
                    if not match:
                        content = "No registered project. Run ki_init_project first."
                    else:
                        content = f"Knowledge Items for this project:\n\n{ki_utils.get_ki_list_table()}"
                else:
                    wf_path = _WORKFLOWS_DIR / f"{prompt_name}.md"
                    if wf_path.exists():
                        with open(wf_path, "r", encoding="utf-8") as f:
                            raw = f.read()
                            know_name = os.path.basename(ki_utils.get_knowledge_root()) or ".ki-base"
                            content = facade.render_instruction(raw, CURRENT_TOOL_MODE, know_name)
                    else:
                        content = f"Unknown prompt: {prompt_name}"
                send({"messages": [{"role": "user", "content": {"type": "text", "text": content}}]})

            elif method == "resources/list":
                jail = get_jail_dir()
                resources = [
                    {"uri": "ki://instructions.md", "name": "instructions.md (Global AI Rules)", "mimeType": "text/markdown"},
                    {"uri": "ki://knowledge-items.md", "name": "knowledge-items.md (Dynamic KI List)", "mimeType": "text/markdown"},
                    {"uri": "ki://adr-list.md", "name": "adr-list.md (Dynamic ADR List)", "mimeType": "text/markdown"},
                ]
                if jail:
                    for fname in ("doc_config.json", "DIR_INDEX.md"):
                        fpath = os.path.join(jail, fname)
                        if os.path.exists(fpath):
                            resources.append({"uri": f"ki://{fname}", "name": fname, "mimeType": "text/plain"})
                if _WORKFLOWS_DIR.exists():
                    for f in sorted(_WORKFLOWS_DIR.glob("*.md")):
                        wf_name = f.stem
                        resources.append({
                            "uri": f"ki://workflows/{wf_name}",
                            "name": f"Workflow: {wf_name}",
                            "mimeType": "text/markdown"
                        })
                resource_templates = [
                    {
                        "uriTemplate": "ki://workflows/{name}",
                        "name": "KI Workflow Instruction",
                        "mimeType": "text/markdown",
                        "description": "Access bundled workflow instructions by name"
                    }
                ]
                send({"resources": resources, "resourceTemplates": resource_templates})

            elif method == "resources/templates/list":
                resource_templates = [
                    {
                        "uriTemplate": "ki://workflows/{name}",
                        "name": "KI Workflow Instruction",
                        "mimeType": "text/markdown",
                        "description": "Access bundled workflow instructions by name"
                    }
                ]
                send({"resourceTemplates": resource_templates})

            elif method == "resources/read":
                uri = params.get("uri", "")
                jail = get_jail_dir()
                content = None
                
                # Virtual resources
                if uri == "ki://instructions.md":
                    know_name = os.path.basename(ki_utils.get_knowledge_root()) or ".ki-base"
                    content = facade.render_instruction(GLOBAL_INSTRUCTIONS, CURRENT_TOOL_MODE, know_name)
                elif uri == "ki://knowledge-items.md":
                    content = f"Knowledge Items for this project:\n\n{ki_utils.get_ki_list_table()}"
                elif uri == "ki://adr-list.md":
                    content = get_adr_list(get_project_root(), jail) if jail else "No active project."
                elif uri in ("ki://workflows/", "ki://workflows"):
                    if _WORKFLOWS_DIR.exists():
                        lines = ["# Available Workflows\n"]
                        for f in sorted(_WORKFLOWS_DIR.glob("*.md")):
                            lines.append(f"- `ki://workflows/{f.stem}` ({f.name})")
                        content = "\n".join(lines)
                    else:
                        content = "No workflows directory found."
                elif uri.startswith("ki://workflows/"):
                    wf_name = uri.replace("ki://workflows/", "")
                    if not wf_name.endswith(".md"):
                        wf_name += ".md"
                    wf_path = _WORKFLOWS_DIR / wf_name
                    if wf_path.exists():
                        with open(wf_path, "r", encoding="utf-8") as f:
                            raw = f.read()
                            know_name = os.path.basename(ki_utils.get_knowledge_root()) or ".ki-base"
                            content = facade.render_instruction(raw, CURRENT_TOOL_MODE, know_name)
                
                # Physical resources in jail
                elif jail and uri.startswith("ki://"):
                    fname = uri.replace("ki://", "")
                    fpath = os.path.join(jail, fname)
                    if os.path.exists(fpath):
                        with open(fpath, "r", encoding="utf-8") as f:
                            content = f.read()
                
                if content is not None:
                    send({"contents": [{"uri": uri, "mimeType": "text/plain", "text": content}]})
                else:
                    send({"isError": True, "error": {"code": -32602, "message": f"Resource not found: {uri}"}})

            else:
                # Fallback for unknown methods to prevent hangs
                if rid is not None:
                    send({"isError": True, "error": {"code": -32601, "message": f"Method not found: {method}"}})

        except Exception as e:
            safe_log(f"ERROR: {e}")
            try:
                err_resp = json.dumps({
                    "jsonrpc": "2.0",
                    "id": rid,
                    "error": {"code": -32603, "message": str(e)},
                })
                sys.stdout.write(err_resp + "\n")
                sys.stdout.flush()
            except Exception as inner:
                safe_log(f"CRITICAL: {inner}")


if __name__ == "__main__":
    main()

