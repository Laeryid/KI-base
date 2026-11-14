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
import re
import io
import contextlib
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
if "ki_manager.scripts.ki_utils" in sys.modules:
    ki_utils = sys.modules["ki_manager.scripts.ki_utils"]
    sys.modules["ki_utils"] = ki_utils
elif "ki_utils" in sys.modules:
    ki_utils = sys.modules["ki_utils"]
    sys.modules["ki_manager.scripts.ki_utils"] = ki_utils
else:
    try:
        from ki_manager.scripts import ki_utils
        sys.modules["ki_utils"] = ki_utils
    except ImportError:
        import ki_utils
import facade
import ki_search
import ki_context

# â”€â”€â”€ Logging â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_LOG_DIR = Path.home() / ".ki_base" / "logs"


def safe_log(msg: str):
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        import datetime
        today_str = datetime.date.today().isoformat()
        log_file = _LOG_DIR / f"mcp_{today_str}.log"
        if len(msg) > 2000:
            msg = msg[:1997] + "..."
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

## 1. Project Navigation & Architecture
`{{KI_DIR}}` (knowledge_root) is the **system container** for the entire knowledge infrastructure (analogous to `.git/` in Git).

```
<project_root>/
├── {{KI_DIR}}/                 ← SYSTEM CONTAINER (do not pollute with .ki.md)
│   ├── config.json             ← Machine-specific environment config (venv path, etc.)
│   ├── ki_config.json          ← Project knowledge configuration
│   ├── doc_config.json         ← Manifest of tracked modules and Knowledge Items
│   ├── DIR_INDEX.md            ← Auto-generated project directory tree
│   ├── coverage_matrix.md      ← Audit report (from audit_coverage)
│   ├── knowledge/              ← STRICTLY ALL Knowledge Items (*.ki.md) live HERE!
│   │   ├── _OVERVIEW.ki.md     ← Project overview stub (MUST NOT be deleted)
│   │   └── <module>.ki.md      ← Module Knowledge Items
│   └── decisions/              ← Architectural Decision Records (*.md ADRs)
├── AGENTS.md                   ← Project instructions for AI agents in harness
└── CLAUDE.md                   ← Instructions for Claude Code / Anthropic
```

- **`DIR_INDEX.md`** (`{{KI_DIR}}/DIR_INDEX.md`) — project directory tree.
- **`doc_config.json`** (`{{KI_DIR}}/doc_config.json`) — manifest of tracked artifacts.
- **`_OVERVIEW.ki.md`** (`{{KI_DIR}}/knowledge/_OVERVIEW.ki.md`) — start here for high-level architecture.
- **Harness & Agent Instructions Guide**: see `ki://agent-rules.md` or `ki_instructions(document="agent-rules")` for recommended snippets for `AGENTS.md` and `CLAUDE.md`.

> [!CAUTION]
> 1. NEVER place `*.ki.md` files directly in the root of `{{KI_DIR}}/`. All Knowledge Items must reside in `{{KI_DIR}}/knowledge/`.
> 2. NEVER delete `{{KI_DIR}}/knowledge/`. The initial `_OVERVIEW.ki.md` (~640 bytes) is a bootstrap stub, not a duplicate. Deleting `knowledge/` breaks audit, scaffolding, and dependency analysis.

## 2. Forced Efficiency (Anti-Hallucinations)
1. **Mandatory Planning Template**:
   Before making code changes, your initial plan (Implementation Plan) **MUST** include:
   - **Affected layers**: [which subsystems are affected]
   - **Read KIs**: [LIST of files from `{{KI_DIR}}/knowledge/` which you read for this task]. *If the list is empty — read KIs before writing code!*
   - **KIs Constraints**: [which approaches are prohibited by current architecture]

2. **Strict Adherence**:
   - Before editing existing code, call `ki_context_for(files=[...])` to retrieve active invariants, pitfalls, and ADR rules.
   - Always read relevant KIs before modifying a module.
   - Native file tools (`read_file`, `edit_file`) may be used to inspect or edit `.md` files inside `{{KI_DIR}}/knowledge/` or `{{KI_DIR}}/decisions/` as long as all `*.ki.md` remain in `{{KI_DIR}}/knowledge/`.
<!-- if-compact -->
   - Use `ki_list()` to view all documented items, `ki_search(query="...")` to find topics, and `ki_read(rel_path="...")` to read documentation.
   - For read-only analysis tools (`ki_lint`, `audit_coverage`, `generate_dir_index`, `ki_scaffold_status`, `git_diff_secured`), call `ki_call(tool="...")`.
   - For state-modifying operations (`ki_sync`, `git_checkpoint`, `write_know_file`, `edit_know_file`, `ki_scaffold`, `create_adr`), call `ki_mutate(tool="...", args={...})`.
   - After editing KI or ADR files, run `ki_mutate(tool="ki_sync")` (or `ki_call(tool="ki_lint")`) to validate and synchronize state.
   - To inspect schemas of available tools, call `ki_tools(name="<tool_name>")`.
<!-- else-compact -->
   - Use `ki_list()` to view all documented items, `ki_search(query="...")` to find topics, and `ki_read(rel_path="...")` or `read_know_file(rel_path="...")` to explore documentation.
   - After editing KI or ADR files, run `ki_sync()` (or `ki_lint()`) to validate metadata/references and synchronize `DIR_INDEX.md`, `doc_state.json`, and `AGENTS.md`.
   - After significant code changes, run `audit_coverage` via MCP.
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

_FORBIDDEN_WRITE_EXT = {
    ".py", ".pyc", ".bat", ".ps1", ".sh", ".exe", ".cmd", ".dll",
    ".js", ".mjs", ".cjs", ".ts", ".vbs", ".wsf", ".bash", ".zsh"
}
_FORBIDDEN_WRITE_FILES = {
    "doc_config.json", "ki_config.json", "config.json", "doc_state.json"
}  # can only be modified via dedicated tools

NO_WORKSPACE_ERROR = {
    "isError": True,
    "content": [{
        "type": "text",
        "text": (
            "✖ No active workspace detected.\n\n"
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
            "✖ No active workspace detected. "
            "Call ki_status({\"path\": \"/absolute/path/to/project\"}) to set it."
        )

    normalized = ki_utils.normalize_path(rel_path, make_absolute=False)
    if not os.path.isabs(normalized):
        if normalized.startswith(".."):
            raise PermissionError(f"Access Denied: path '{rel_path}' escapes sandbox.")
        target = os.path.abspath(os.path.join(jail, normalized))
    else:
        target = os.path.abspath(normalized)

    if not ki_utils.is_subpath(target, jail):
        raise PermissionError("Access Denied: jail breach detected.")

    if is_write:
        ext = os.path.splitext(target)[1].lower()
        if ext in _FORBIDDEN_WRITE_EXT:
            raise PermissionError(f"Access Denied: modifying {ext} files is forbidden.")
        if os.path.basename(target).lower() in _FORBIDDEN_WRITE_FILES:
            raise PermissionError("Access Denied: use dedicated tools to modify this file.")

    return target


def resolve_know_path(rel_path: str, is_write: bool = False, must_exist: bool = False) -> str:
    """
    Resolves a relative knowledge/ADR path using smart cascading, security validation,
    and tolerance for prefixes like 'ADR_'.

    If must_exist is True: raises FileNotFoundError if not found.
    If must_exist is False and file doesn't exist: returns the target creation path
    (defaulting flat KI files to <jail>/knowledge/<norm>).
    """
    jail = get_jail_dir()
    if not jail:
        raise PermissionError(
            "✖ No active workspace detected. "
            "Call ki_status({\"path\": \"/absolute/path/to/project\"}) to set it."
        )

    norm = ki_utils.normalize_path(rel_path, make_absolute=False)
    if not norm:
        raise ValueError("rel_path cannot be empty.")

    if not os.path.isabs(norm) and norm.startswith(".."):
        raise PermissionError(f"Access Denied: path '{rel_path}' escapes sandbox.")

    project_root = get_project_root()
    base_name = os.path.basename(norm)
    dir_name = os.path.dirname(norm)

    # Name variants (tolerance for ADR_ / adr_ prefixes)
    name_variants = [base_name]
    m_adr = re.match(r"^(?:ADR|adr)[_\-](.*)", base_name)
    if m_adr:
        name_variants.append(m_adr.group(1))
    elif re.match(r"^\d+", base_name):
        name_variants.append(f"ADR_{base_name}")
        name_variants.append(f"adr_{base_name}")

    target = None

    # 1. Direct path inside jail
    try:
        cand = validate_path(norm)
        if os.path.exists(cand) and os.path.isfile(cand):
            target = cand
    except Exception:
        target = None

    # 1b. If base_name had ADR_ prefix, try direct path with stripped name in same directory inside jail
    if not target and m_adr and dir_name:
        try:
            cand = validate_path(os.path.join(dir_name, m_adr.group(1)))
            if os.path.exists(cand) and os.path.isfile(cand):
                target = cand
        except Exception:
            target = None

    # 2. Inside jail/knowledge/ (standard structure: <jail>/knowledge/<file>)
    if not target and jail:
        for nv in name_variants:
            sub = os.path.join(dir_name, nv) if dir_name else nv
            try:
                cand = validate_path(os.path.join("knowledge", sub))
                if os.path.exists(cand) and os.path.isfile(cand):
                    target = cand
                    break
            except Exception:
                pass

    # 3. If rel_path starts with the knowledge_root folder name itself (e.g. '.ki-base/...' or 'knowledge/...'),
    # strip prefix and resolve inside jail
    if not target and jail and project_root:
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

    # 4. Decisions directories (ADR resolution)
    if not target and project_root:
        candidates = ki_utils.get_decisions_dirs(project_root, jail)
        for d in candidates:
            if not os.path.exists(d):
                continue
            # Try by name variants
            for nv in name_variants:
                cand_p = os.path.abspath(os.path.join(d, nv))
                if os.path.exists(cand_p) and cand_p.endswith(".md") and os.path.isfile(cand_p):
                    target = cand_p
                    break
            if target:
                break

            # If still not found, match by ADR ID prefix (e.g. '002' or '2')
            m_id = re.match(r"^(?:ADR[_\-]?)?(\d+)", base_name, re.IGNORECASE)
            if m_id:
                target_id = m_id.group(1)
                for f in os.listdir(d):
                    if f.endswith(".md"):
                        m_f = re.match(r"^(?:ADR[_\-]?)?(\d+)", f, re.IGNORECASE)
                        if m_f and (m_f.group(1) == target_id or m_f.group(1).lstrip("0") == target_id.lstrip("0")):
                            target = os.path.abspath(os.path.join(d, f))
                            break
            if target:
                break

        # Also check relative to project root directly if within decisions or jail
        if not target:
            cand_p = os.path.abspath(os.path.join(project_root, norm))
            if os.path.exists(cand_p) and cand_p.endswith(".md") and os.path.isfile(cand_p):
                valid_prefixes = candidates + ([jail] if jail else [])
                for vp in valid_prefixes:
                    if os.path.normcase(cand_p).startswith(os.path.normcase(vp)):
                        target = cand_p
                        break

    # 5. Fallback: Search by basename variants in jail and its subfolders
    if not target and jail and os.path.exists(jail):
        for root, _, files in os.walk(jail):
            for nv in name_variants:
                if nv in files:
                    cand_p = os.path.abspath(os.path.join(root, nv))
                    if cand_p.endswith(".md") and os.path.isfile(cand_p):
                        target = cand_p
                        break
            if target:
                break

    # Security check on resolved existing target
    if target:
        valid_roots = [jail]
        if project_root:
            valid_roots.extend(ki_utils.get_decisions_dirs(project_root, jail))
        is_safe = any(ki_utils.is_subpath(target, vr) for vr in valid_roots if vr)
        if not is_safe:
            raise PermissionError("Access Denied: jail breach detected.")

        if is_write:
            ext = os.path.splitext(target)[1].lower()
            if ext in _FORBIDDEN_WRITE_EXT:
                raise PermissionError(f"Access Denied: modifying {ext} files is forbidden.")
            if os.path.basename(target).lower() in _FORBIDDEN_WRITE_FILES:
                raise PermissionError("Access Denied: use dedicated tools to modify this file.")

        return target

    # Target not found
    if must_exist:
        raise FileNotFoundError(f"Knowledge file '{rel_path}' not found.")

    # Target does not exist, but we are resolving path for creation (e.g. write_know_file)
    # If path is flat (no dir specified) and jail has knowledge folder, default to knowledge/
    if not dir_name:
        know_dir = os.path.join(jail, "knowledge")
        if os.path.exists(know_dir) or base_name.startswith("KI_") or base_name.endswith(".ki.md"):
            return validate_path(os.path.join("knowledge", base_name), is_write=is_write)

    return validate_path(norm, is_write=is_write)


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
            "readOnlyHint": True,
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
            "readOnlyHint": True,
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
            "readOnlyHint": True,
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
        "name": "check_ki_drift",
        "description": (
            "Detect discrepancies and drift between Knowledge Items (KI) and code: "
            "dead symbols, unmapped public functions/classes, missing files, broken wiki-links, "
            "and git date modifications."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ki_name": {
                    "type": "string",
                    "description": "Optional specific KI filename (e.g. 'KI_server.md'). Omit to check all KIs.",
                },
            },
        },
        "annotations": {
            "title": "Check Knowledge Drift",
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
        "description": (
            "Update the last_verified date to today in affected KI files "
            "(by git diff / doc_config mapping, explicit ki_files, or all_files=true)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ki_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of KI filenames or relative paths to update.",
                },
                "all_files": {
                    "type": "boolean",
                    "description": "Set true to update all KI files regardless of code changes.",
                },
            },
        },
        "annotations": {
            "title": "Update Last Verified",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "ki_split_analyze",
        "description": (
            "Analyze an overloaded Knowledge Item (>10 files) and calculate an optimal bisection "
            "into Group A and Group B by static import graph."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ki_name": {
                    "type": "string",
                    "description": "Filename of the overloaded KI to analyze (e.g. 'KI_rich.md')"
                }
            },
            "required": ["ki_name"]
        },
        "annotations": {
            "title": "Analyze KI Split",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True
        }
    },
    {
        "name": "ki_split",
        "description": (
            "Atomically split an overloaded Knowledge Item into two balanced Knowledge Items "
            "(target_a and target_b), update doc_config.json, and remove original if renamed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ki_name": {
                    "type": "string",
                    "description": "Original KI filename being split (e.g. 'KI_rich.md')"
                },
                "target_a": {
                    "type": "object",
                    "description": "Payload for part A: {ki_name, summary, depends_on, content}",
                    "properties": {
                        "ki_name": {"type": "string"},
                        "summary": {"type": "string"},
                        "depends_on": {"type": "array", "items": {"type": "string"}},
                        "content": {"type": "string"}
                    },
                    "required": ["ki_name", "depends_on"]
                },
                "target_b": {
                    "type": "object",
                    "description": "Payload for part B: {ki_name, summary, depends_on, content}",
                    "properties": {
                        "ki_name": {"type": "string"},
                        "summary": {"type": "string"},
                        "depends_on": {"type": "array", "items": {"type": "string"}},
                        "content": {"type": "string"}
                    },
                    "required": ["ki_name", "depends_on"]
                }
            },
            "required": ["ki_name", "target_a", "target_b"]
        },
        "annotations": {
            "title": "Apply KI Split",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False
        }
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
                },
                "status": {
                    "type": "string",
                    "description": "Optional lifecycle status (KI: stub, draft, poc, active, stale, archived; ADR: draft, poc, accepted, superseded, deprecated, archived)"
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
            "'tracked_modules', 'artifacts', 'coverage_settings', or 'ignore_dirs'. "
            "For 'tracked_modules', items are [module_path, label, importance (1-10)] triples "
            "(e.g. ['src/api', 'API Subsystem', 8]) or simple string module paths (normalized automatically)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": ["tracked_modules", "artifacts", "coverage_settings", "ignore_dirs"],
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
                    "description": "Value to set or append. For 'tracked_modules': a [path, label, importance] array (e.g. ['src', 'Source', 8]) or string path (e.g. 'src'). For artifacts: dict or dependency string."
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
                    "default": "accepted",
                    "description": "Status of the decision: 'draft' (or 'proposed'), 'poc', 'accepted' (default), 'superseded', 'deprecated', 'archived'"
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
                },
                "supersedes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of previous ADR IDs superseded by this record (e.g. ['001', '002'])"
                },
                "rejected_alternatives": {
                    "type": "string",
                    "description": "Alternatives and failed attempts considered and rejected"
                },
                "invariants": {
                    "type": "string",
                    "description": "Hard architectural invariants and rules for future AI agents (e.g. MUST / MUST NOT)"
                },
                "verification": {
                    "type": "string",
                    "description": "Verification steps, test command, or validation procedure"
                },
                "affected_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of source files or modules affected by this decision (auto-detected if omitted)"
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
            "properties": {
                "rel_path": {"type": "string", "description": "Path relative to knowledge root/"},
                "max_chars": {"type": "integer", "description": "Optional maximum number of characters to return"},
                "offset": {"type": "integer", "default": 0, "description": "Optional character offset to start reading from"},
            },
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
        "description": (
            "Check or commit knowledge root changes to git. "
            "Requires auto_git_checkpoint=true in ki_config.json or commit=true to create a commit."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Commit message suffix"},
                "commit": {
                    "type": "boolean",
                    "description": "Explicitly create a git commit even when auto_git_checkpoint is disabled.",
                },
            },
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
    {
        "name": "ki_lint",
        "description": (
            "Lint the knowledge base for structural, metadata (status, superseded_by cycles, last_verified, "
            "empty sections), and referential integrity (doc_config.json registration, depends_on paths)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "staged": {
                    "type": "boolean",
                    "description": "Only check Git-staged knowledge files (default: false).",
                    "default": False,
                },
                "fix": {
                    "type": "boolean",
                    "description": "Auto-fix safe issues such as registering unmapped KIs in doc_config.json (default: false).",
                    "default": False,
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "json"],
                    "description": "Output format (default: markdown).",
                    "default": "markdown",
                },
            },
        },
        "annotations": {
            "title": "Lint Knowledge Base",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    {
        "name": "ki_sync",
        "description": (
            "Composite synchronization tool: runs ki_lint -> git diff -> check_ki_drift (on affected KIs) -> "
            "targeted update_last_verified -> generate_dir_index -> save_state -> sync_agents_md. "
            "Aborts before mutating doc_state.json or AGENTS.md if ki_lint reports errors."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "fix_lint": {
                    "type": "boolean",
                    "description": "Auto-fix safe lint issues before syncing (default: false).",
                    "default": False,
                },
                "skip_drift": {
                    "type": "boolean",
                    "description": "Skip check_ki_drift analysis on affected KIs (default: false).",
                    "default": False,
                },
                "agents_path": {
                    "type": "string",
                    "description": "Optional explicit path to AGENTS.md.",
                },
            },
        },
        "annotations": {
            "title": "Synchronize Knowledge System",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    },
    # ─── Navigation, Search & Read ───
    facade.KI_LIST_TOOL,
    facade.KI_SEARCH_TOOL,
    facade.KI_READ_TOOL,
    facade.KI_CONTEXT_FOR_TOOL,
]

# Dynamically bind ki_call and ki_mutate schemas to readOnlyHint annotations
facade.sync_dispatch_schemas(MCP_TOOLS)

_INSTRUCTIONS_TOOL = next(t for t in MCP_TOOLS if t["name"] == "ki_instructions")
COMPACT_TOOLS = [
    _INSTRUCTIONS_TOOL,
    facade.KI_LIST_TOOL,
    facade.KI_SEARCH_TOOL,
    facade.KI_READ_TOOL,
    facade.KI_CONTEXT_FOR_TOOL,
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
        os.path.join(ki_base_rel, "doc_state.json"),
        os.path.join(ki_base_rel, "ki_config.json"),
        os.path.join(ki_base_rel, "AGENTS.md"),
        os.path.join(ki_base_rel, "DIR_INDEX.md"),
        os.path.join(ki_base_rel, "knowledge"),
        os.path.join(ki_base_rel, "decisions") if os.path.exists(os.path.join(jail, "decisions")) else None,
    ]
    existing_targets = [t for t in targets if t and os.path.exists(os.path.join(project_root, t))]
    should_commit = bool(args.get("commit", False)) or ki_utils.is_auto_git_checkpoint_enabled()

    if not should_commit:
        try:
            pending = []
            if existing_targets:
                stat_res = subprocess.run(
                    ["git", "status", "--porcelain", "--", *existing_targets],
                    cwd=project_root, capture_output=True, text=True, encoding="utf-8", check=False,
                )
                if stat_res.returncode == 0 and stat_res.stdout.strip():
                    pending = [line.rstrip() for line in stat_res.stdout.splitlines() if line.strip()]
            note = (
                "Git auto-commit is disabled (auto_git_checkpoint=false). "
                "Knowledge changes remain in the working tree for atomic commit with your code "
                "(pass commit=true or set auto_git_checkpoint=true in ki_config.json to commit)."
            )
            if pending:
                return {"content": [{"type": "text", "text": f"{note}\nPending knowledge changes:\n" + "\n".join(pending)}]}
            return {"content": [{"type": "text", "text": f"{note}\nNo pending knowledge changes."}]}
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": f"Git Error: {str(e)}"}]}

    try:
        for t in existing_targets:
            subprocess.run(["git", "add", t], cwd=project_root, check=False, capture_output=True)
        status = subprocess.run(["git", "diff", "--quiet", "--cached"], cwd=project_root, capture_output=True)
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


def _collect_git_changed_files(project_root: str) -> list:
    """Returns project-relative forward-slash paths of uncommitted git changes."""
    if not project_root or not os.path.exists(os.path.join(project_root, ".git")):
        return []
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=2,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return []
        changed = []
        for line in res.stdout.splitlines():
            if len(line) < 4:
                continue
            raw_path = line[3:].strip()
            if " -> " in raw_path:
                raw_path = raw_path.split(" -> ", 1)[1].strip()
            raw_path = raw_path.strip('"').replace("\\", "/")
            if raw_path:
                changed.append(raw_path)
        return changed
    except Exception:
        return []


def _resolve_target_ki_files(project_root: str, jail: str, know_dir: str, args: dict) -> list:
    """Resolves which KI files should have last_verified updated."""
    all_ki_map = {}
    for root, dirs, files in os.walk(know_dir):
        dirs[:] = sorted(d for d in dirs if d != "decisions" and not d.startswith("."))
        for fname in sorted(files):
            if not ki_utils.is_ki_filename(fname, include_overview=True):
                continue
            fpath = os.path.join(root, fname)
            if os.path.isfile(fpath):
                rel_posix = os.path.relpath(fpath, know_dir).replace("\\", "/")
                all_ki_map[rel_posix] = fpath

    if not all_ki_map:
        return []

    if args.get("all_files"):
        return [all_ki_map[k] for k in sorted(all_ki_map)]

    basename_lookup = {}
    for rel_k, fpath in all_ki_map.items():
        basename_lookup.setdefault(os.path.basename(rel_k), []).append(rel_k)

    ki_files_arg = args.get("ki_files")
    if isinstance(ki_files_arg, str):
        ki_files_arg = [x.strip() for x in ki_files_arg.split(",") if x.strip()]
    if isinstance(ki_files_arg, list) and ki_files_arg:
        selected = []
        seen = set()
        for item in ki_files_arg:
            item_norm = str(item).strip().replace("\\", "/")
            while item_norm.startswith("./"):
                item_norm = item_norm[2:]
            item_norm = item_norm.lstrip("/")
            matched_keys = []
            if item_norm in all_ki_map:
                matched_keys = [item_norm]
            else:
                base = os.path.basename(item_norm)
                matched_keys = basename_lookup.get(base, [])
            for mk in matched_keys:
                if mk not in seen:
                    seen.add(mk)
                    selected.append(all_ki_map[mk])
        return selected

    changed_files = set(_collect_git_changed_files(project_root))

    sys.path.insert(0, str(_SCRIPTS_DIR))
    from knowledge_engine import KnowledgeEngine
    rel_jail = os.path.relpath(jail, project_root) if project_root else os.path.basename(jail)
    ke = KnowledgeEngine(project_root, rel_jail)
    if os.path.exists(ke.state_file):
        modified, new_files, _ = ke.check_for_changes()
        changed_files.update(p.replace("\\", "/") for p in (modified + new_files))

    affected_keys = set()
    if changed_files:
        affected_map = ke.get_affected_ki_map(list(changed_files))
        for ki_key in affected_map:
            key_norm = ki_key.replace("\\", "/")
            while key_norm.startswith("./"):
                key_norm = key_norm[2:]
            key_norm = key_norm.lstrip("/")
            if key_norm.startswith("knowledge/"):
                key_norm = key_norm[len("knowledge/"):]
            if key_norm in all_ki_map:
                affected_keys.add(key_norm)
            else:
                for mk in basename_lookup.get(os.path.basename(key_norm), []):
                    affected_keys.add(mk)

        know_rel = os.path.relpath(know_dir, project_root).replace("\\", "/").strip("/")
        for cf in changed_files:
            cf_norm = cf.replace("\\", "/")
            while cf_norm.startswith("./"):
                cf_norm = cf_norm[2:]
            cf_norm = cf_norm.lstrip("/")
            rel_candidate = ""
            if cf_norm.startswith(know_rel + "/"):
                rel_candidate = cf_norm[len(know_rel) + 1:]
            elif cf_norm.startswith("knowledge/"):
                rel_candidate = cf_norm[len("knowledge/"):]
            if rel_candidate:
                if rel_candidate in all_ki_map:
                    affected_keys.add(rel_candidate)
                else:
                    for mk in basename_lookup.get(os.path.basename(rel_candidate), []):
                        affected_keys.add(mk)

    return [all_ki_map[k] for k in sorted(affected_keys) if k in all_ki_map]


def _update_last_verified_in_file(filepath: str, today: str) -> bool:
    """Updates or inserts last_verified tag in a single KI file. Returns True if modified."""
    import tempfile

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    has_tag = bool(
        re.search(r'<!--\s*last_verified:\s*"?\d{4}-\d{2}-\d{2}"?\s*-->', content, re.IGNORECASE)
        or re.search(r'^last_verified:\s*"?\d{4}-\d{2}-\d{2}"?', content, re.MULTILINE)
        or re.search(r'\*\*Last verified\*\*:\s*"?\d{4}-\d{2}-\d{2}"?', content, re.IGNORECASE)
    )

    new_content = content
    if has_tag:
        new_content = re.sub(
            r'<!--\s*last_verified:\s*"?\d{4}-\d{2}-\d{2}"?\s*-->',
            f'<!-- last_verified: {today} -->',
            new_content,
            flags=re.IGNORECASE,
        )
        new_content = re.sub(
            r'^(last_verified:\s*)"?\d{4}-\d{2}-\d{2}"?',
            rf'\g<1>"{today}"',
            new_content,
            flags=re.MULTILINE,
        )
        new_content = re.sub(
            r'(\*\*Last verified\*\*:\s*)"?\d{4}-\d{2}-\d{2}"?',
            rf'\g<1>{today}',
            new_content,
            flags=re.IGNORECASE,
        )
    else:
        lines = content.splitlines(keepends=True)
        res_lines = []
        inserted = False
        for line in lines:
            res_lines.append(line)
            if not inserted and line.startswith("# "):
                res_lines.append(f"\n<!-- last_verified: {today} -->\n")
                inserted = True
        if not inserted:
            res_lines.insert(0, f"<!-- last_verified: {today} -->\n\n")
        new_content = "".join(res_lines)

    if new_content == content:
        return False

    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(filepath), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(new_content)
        os.replace(tmp_path, filepath)
        return True
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False


def tool_update_last_verified(args: dict) -> str:
    """Updates last_verified only in affected KI files (or explicit/all_files)."""
    import datetime

    jail = get_jail_dir()
    if not jail:
        return "Error: No project."
    know_dir = os.path.join(jail, "knowledge")
    if not os.path.exists(know_dir):
        return "Updated last_verified in 0 files."

    project_root = get_project_root()
    target_files = _resolve_target_ki_files(project_root, jail, know_dir, args or {})
    if not target_files:
        return "Updated last_verified in 0 files (no affected KIs)."

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    updated_names = []
    for filepath in target_files:
        if _update_last_verified_in_file(filepath, today):
            updated_names.append(os.path.basename(filepath))

    if not updated_names:
        return "Updated last_verified in 0 files (already up to date)."
    return f"Updated last_verified in {len(updated_names)} files: {', '.join(updated_names)}."


def tool_add_ki_to_config(args: dict) -> dict:
    jail = get_jail_dir()
    if not jail:
        return NO_WORKSPACE_ERROR

    ki_name = args.get("ki_name")
    description = args.get("description")
    covers = args.get("covers", [])
    depends_on = args.get("depends_on", [])
    summary = args.get("summary")
    status = args.get("status")

    if not ki_name or not description:
        return {"isError": True, "content": [{"type": "text", "text": "Error: 'ki_name' and 'description' are required."}]}

    if not isinstance(covers, list) or not isinstance(depends_on, list):
        return {"isError": True, "content": [{"type": "text", "text": "Error: 'covers' and 'depends_on' must be arrays."}]}

    sys.path.insert(0, str(_SCRIPTS_DIR))
    import add_ki_to_config
    try:
        msg = add_ki_to_config.add_ki(ki_name, description, covers, depends_on, summary, status=status)
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

    allowed_sections = {"tracked_modules", "artifacts", "coverage_settings", "ignore_dirs"}
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
            norm_val = list(ki_utils.normalize_tracked_module(value))
            if not norm_val[0]:
                return {"isError": True, "content": [{"type": "text", "text": "Error: module path cannot be empty."}]}
            existing_idx = -1
            for i, item in enumerate(modules_list):
                if ki_utils.normalize_tracked_module(item)[0] == norm_val[0]:
                    existing_idx = i
                    break
            if existing_idx >= 0:
                modules_list[existing_idx] = norm_val
                msg = f"Updated existing tracked_module '{norm_val[0]}': {norm_val}"
            else:
                modules_list.append(norm_val)
                msg = f"Appended module to tracked_modules: {norm_val}"
        elif action == "set":
            if key is not None:
                norm_val = list(ki_utils.normalize_tracked_module(value)) if value is not None else value
                idx = -1
                if isinstance(key, int) or (isinstance(key, str) and key.isdigit()):
                    idx = int(key)
                else:
                    for i, item in enumerate(modules_list):
                        mod_name = ki_utils.normalize_tracked_module(item)[0]
                        if mod_name == key:
                            idx = i
                            break
                if 0 <= idx < len(modules_list):
                    modules_list[idx] = norm_val
                    msg = f"Updated tracked_modules at index {idx}: {norm_val}"
                else:
                    modules_list.append(norm_val)
                    msg = f"Key '{key}' not found in tracked_modules; appended {norm_val}"
            else:
                if isinstance(value, list):
                    norm_list = [list(ki_utils.normalize_tracked_module(v)) for v in value if ki_utils.normalize_tracked_module(v)[0]]
                    if "tracked_modules" in config and target_container is not config:
                        config["tracked_modules"] = norm_list
                    else:
                        target_container["tracked_modules"] = norm_list
                    msg = f"Set tracked_modules list to {len(norm_list)} items"
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
                        mod_name = ki_utils.normalize_tracked_module(item)[0]
                        if mod_name == key:
                            modules_list.remove(item)
                            deleted = True
                            msg = f"Deleted tracked_module '{key}': {item}"
                            break
            elif value is not None:
                norm_target = ki_utils.normalize_tracked_module(value)[0]
                for item in list(modules_list):
                    if ki_utils.normalize_tracked_module(item)[0] == norm_target:
                        modules_list.remove(item)
                        deleted = True
                        msg = f"Deleted tracked_module: {item}"
                        break
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

    elif section == "ignore_dirs":
        settings = config.setdefault("coverage_settings", {})
        if not isinstance(settings, dict):
            settings = {}
            config["coverage_settings"] = settings
        target_list = settings.setdefault("ignore_dirs", [])
        if not isinstance(target_list, list):
            target_list = []
            settings["ignore_dirs"] = target_list

        if action == "append":
            items_to_add = value if isinstance(value, list) else ([value] if value is not None else [])
            added = []
            for item in items_to_add:
                s_item = str(item).strip()
                if s_item and s_item not in target_list:
                    target_list.append(s_item)
                    added.append(s_item)
            msg = f"Appended to ignore_dirs: {added}"
        elif action == "set":
            if isinstance(value, list):
                settings["ignore_dirs"] = [str(x).strip() for x in value if str(x).strip()]
                msg = f"Set ignore_dirs to {settings['ignore_dirs']}"
            elif value is not None:
                settings["ignore_dirs"] = [str(value).strip()]
                msg = f"Set ignore_dirs to {settings['ignore_dirs']}"
            else:
                return {"isError": True, "content": [{"type": "text", "text": "Error: 'value' is required for set action on ignore_dirs."}]}
        elif action == "delete":
            target = key or value
            if not target:
                return {"isError": True, "content": [{"type": "text", "text": "Error: 'key' or 'value' is required for delete action on ignore_dirs."}]}
            s_target = str(target).strip()
            if s_target in target_list:
                target_list.remove(s_target)
                msg = f"Deleted '{s_target}' from ignore_dirs"
            else:
                return {"isError": True, "content": [{"type": "text", "text": f"Error: '{s_target}' not found in ignore_dirs."}]}

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


def tool_ki_lint(args: dict) -> dict:
    jail = get_jail_dir()
    project_root = get_project_root()
    if not jail or not project_root:
        return NO_WORKSPACE_ERROR

    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    import ki_lint

    staged = bool((args or {}).get("staged", False))
    fix = bool((args or {}).get("fix", False))
    fmt = str((args or {}).get("format", "markdown")).lower()

    res = ki_lint.lint_knowledge_base(
        project_root=project_root,
        knowledge_root=jail,
        staged=staged,
        fix=fix,
    )
    text = json.dumps(res, indent=2, ensure_ascii=False) if fmt == "json" else ki_lint.format_lint_report(res)
    return {"isError": not res.get("ok", True), "content": [{"type": "text", "text": text}]}


def tool_ki_sync(args: dict) -> dict:
    """Composite synchronization: ki_lint -> git diff -> check_ki_drift -> update_last_verified -> generate_dir_index -> save_state -> sync_agents_md."""
    import datetime

    jail = get_jail_dir()
    project_root = get_project_root()
    if not jail or not project_root:
        return NO_WORKSPACE_ERROR

    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    import ki_lint
    import check_ki_drift
    import generate_dir_index
    import sync_agents_md
    from knowledge_engine import KnowledgeEngine

    opts = args or {}
    fix_lint = bool(opts.get("fix_lint", False))
    skip_drift = bool(opts.get("skip_drift", False))
    agents_path = opts.get("agents_path")

    # Ensure ki_utils resolves the same project root even in monkeypatched tests
    prev_ws = ki_utils.ACTIVE_WORKSPACE_PATH
    if not prev_ws or os.path.abspath(prev_ws) != os.path.abspath(project_root):
        ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(project_root)

    try:
        # 1. ki_lint gate (before any state/AGENTS mutation)
        lint_res = ki_lint.lint_knowledge_base(
            project_root=project_root,
            knowledge_root=jail,
            staged=False,
            fix=fix_lint,
        )
        if not lint_res.get("ok", False):
            report = ki_lint.format_lint_report(lint_res)
            return {
                "isError": True,
                "content": [{
                    "type": "text",
                    "text": (
                        "❌ ki_sync aborted before updating doc_state.json or AGENTS.md: "
                        "ki_lint found errors that must be fixed first.\n\n" + report
                    ),
                }],
            }

        know_dir = ki_lint._resolve_know_dir(project_root, jail)

        # 2. Git diff & affected KIs
        git_changed = _collect_git_changed_files(project_root)
        target_kis = _resolve_target_ki_files(project_root, jail, know_dir, {}) if os.path.exists(know_dir) else []

        # 3. check_ki_drift on affected KIs
        drift_summary = "Skipped (no affected KIs in diff)."
        if skip_drift:
            drift_summary = "Skipped (skip_drift=true)."
        elif target_kis:
            drift_results = []
            for ki_path in target_kis:
                ki_name = os.path.basename(ki_path)
                drift_results.extend(
                    check_ki_drift.run_drift_check(
                        ki_filter=ki_name,
                        project_root=project_root,
                        knowledge_root=jail,
                    )
                )
            with_drift = [r for r in drift_results if r.get("drift_count", 0) > 0]
            drift_summary = (
                f"Checked {len(drift_results)} affected KI(s): {len(with_drift)} with drift."
                if drift_results
                else "No matching KIs checked."
            )
            if with_drift:
                drift_summary += "\n" + check_ki_drift.format_drift_markdown(with_drift)

        # 4. Targeted update_last_verified
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        updated_verified = []
        for ki_path in target_kis:
            if _update_last_verified_in_file(ki_path, today):
                updated_verified.append(os.path.basename(ki_path))

        # 5. generate_dir_index
        dir_index_path = os.path.join(jail, "DIR_INDEX.md")
        generate_dir_index.generate_dir_index(dir_index_path)

        # 6. save_state
        ke = KnowledgeEngine(project_root, os.path.basename(jail))
        ke.save_state(ke.capture_full_state())
        state_name = os.path.basename(getattr(ke, "state_file", None) or "doc_state.json")

        # 7. sync_agents_md
        agents_msg = sync_agents_md.sync_agents_md(agents_path)

        lines = [
            "✅ **ki_sync completed.**",
            f"- **1. ki_lint**: {lint_res['checked_kis']} KI(s), {lint_res['checked_adrs']} ADR(s) — 0 errors, {len(lint_res.get('warnings', []))} warning(s).",
            f"- **2. Git diff**: {len(git_changed)} changed file(s); {len(target_kis)} affected KI(s).",
            f"- **3. check_ki_drift**: {drift_summary}",
            f"- **4. update_last_verified**: updated {len(updated_verified)} file(s)"
            + (f" ({', '.join(updated_verified)})" if updated_verified else "") + ".",
            f"- **5. generate_dir_index**: updated `{os.path.basename(jail)}/DIR_INDEX.md`.",
            f"- **6. save_state**: saved `{state_name}`.",
            f"- **7. sync_agents_md**: {agents_msg}",
        ]
        if lint_res.get("fixed"):
            lines.append("- **Auto-fixed**: " + "; ".join(lint_res["fixed"]))
        if lint_res.get("warnings"):
            lines.append("\n**Lint Warnings:**")
            for w in lint_res["warnings"]:
                lines.append(f"- [{w['code']}] `{w['file']}`: {w['message']}")

        return {"content": [{"type": "text", "text": "\n".join(lines)}]}
    finally:
        ki_utils.ACTIVE_WORKSPACE_PATH = prev_ws


def tool_create_adr(args: dict) -> dict:
    jail = get_jail_dir()
    project_root = get_project_root()
    if not jail or not project_root:
        return NO_WORKSPACE_ERROR

    title = args.get("title", "").strip()
    status = ki_utils.normalize_status(args.get("status", "accepted"), doc_type="adr")
    context = args.get("context", "").strip()
    decision = args.get("decision", "").strip()
    consequences = args.get("consequences", "").strip()
    topic_name = args.get("topic_name", "").strip()
    supersedes_input = args.get("supersedes")
    rejected_alternatives = args.get("rejected_alternatives", "").strip()
    invariants = args.get("invariants", "").strip()
    verification = args.get("verification", "").strip()
    affected_files_input = args.get("affected_files")

    if not title or not topic_name:
        return {"isError": True, "content": [{"type": "text", "text": "Error: 'title' and 'topic_name' are required."}]}

    import re
    topic_slug = re.sub(r"[^\w\-]+", "_", topic_name).strip("_").lower()

    # Parse supersedes IDs
    supersedes_list = []
    if isinstance(supersedes_input, list):
        for item in supersedes_input:
            s_str = str(item).strip()
            if s_str:
                supersedes_list.append(s_str.zfill(3) if s_str.isdigit() else s_str)
    elif isinstance(supersedes_input, str) and supersedes_input.strip():
        for s in re.findall(r"\b\d+\b|\w+", supersedes_input):
            s_str = s.strip()
            if s_str:
                supersedes_list.append(s_str.zfill(3) if s_str.isdigit() else s_str)

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

    # Process superseded ADRs
    superseded_links = []
    updated_old_adrs = []
    doc_cfg = ki_utils.get_doc_config() or {}
    ki_entries = doc_cfg.get("knowledge_items", {})
    doc_cfg_modified = False

    for s_id in supersedes_list:
        matched_old_path = None
        matched_filename = None
        for d in decisions_candidates:
            if not os.path.exists(d):
                continue
            for f in os.listdir(d):
                if f.endswith(".md"):
                    m = re.match(r"^(\d+)", f)
                    if m and (m.group(1) == s_id or m.group(1) == s_id.lstrip("0") or f.startswith(s_id)):
                        matched_old_path = os.path.join(d, f)
                        matched_filename = f
                        break
            if matched_old_path:
                break

        if matched_old_path and os.path.exists(matched_old_path):
            try:
                with open(matched_old_path, "r", encoding="utf-8") as f_old:
                    old_content = f_old.read()

                new_status_str = f"Superseded by ADR {next_id}"
                if re.search(r"<!--\s*status:\s*([^\n\r>]+?)\s*-->", old_content, re.IGNORECASE):
                    old_content = re.sub(
                        r"<!--\s*status:\s*([^\n\r>]+?)\s*-->",
                        "<!-- status: superseded -->",
                        old_content,
                        count=1,
                        flags=re.IGNORECASE
                    )
                else:
                    old_content = "<!-- status: superseded -->\n" + old_content

                if re.search(r"<!--\s*superseded_by:\s*([^\n\r>]+?)\s*-->", old_content, re.IGNORECASE):
                    old_content = re.sub(
                        r"<!--\s*superseded_by:\s*([^\n\r>]+?)\s*-->",
                        f"<!-- superseded_by: {next_id} -->",
                        old_content,
                        count=1,
                        flags=re.IGNORECASE
                    )
                else:
                    old_content = re.sub(
                        r"(<!--\s*status:\s*superseded\s*-->\s*\n?)",
                        rf"\1<!-- superseded_by: {next_id} -->\n",
                        old_content,
                        count=1,
                        flags=re.IGNORECASE
                    )

                if re.search(r"\*\*Status\*\*:\s*([^\n\r]+)", old_content, re.IGNORECASE):
                    old_content = re.sub(
                        r"\*\*Status\*\*:\s*([^\n\r]+)",
                        f"**Status**: Superseded by [ADR {next_id}](./{adr_filename})",
                        old_content,
                        count=1,
                        flags=re.IGNORECASE
                    )

                warning_banner = (
                    f"> [!WARNING]\n"
                    f"> **This ADR is superseded by [ADR {next_id}: {title}](./{adr_filename}).**\n"
                )
                if re.search(r"> \[!WARNING\]\s*\n>\s*\*\*This ADR is superseded[^\n\r]*\*\*", old_content):
                    old_content = re.sub(
                        r"> \[!WARNING\]\s*\n>\s*\*\*This ADR is superseded[^\n\r]*\*\*\n?",
                        warning_banner,
                        old_content
                    )
                else:
                    title_match = re.search(r"(^#\s+[^\n\r]+\n+)", old_content, re.MULTILINE)
                    if title_match:
                        pos = title_match.end()
                        old_content = old_content[:pos] + warning_banner + "\n" + old_content[pos:]
                    else:
                        old_content = warning_banner + "\n" + old_content

                with open(matched_old_path, "w", encoding="utf-8") as f_old:
                    f_old.write(old_content)
                updated_old_adrs.append(matched_filename)

                for k_path, k_data in ki_entries.items():
                    if matched_filename in k_path:
                        k_data["status"] = "superseded"
                        k_data["superseded_by"] = next_id
                        desc = k_data.get("description", "")
                        if "(" in desc and ")" in desc:
                            k_data["description"] = re.sub(r"\([^\)]+\)$", f"({new_status_str})", desc)
                        else:
                            k_data["description"] = f"{desc} ({new_status_str})"
                        doc_cfg_modified = True

                superseded_links.append(f"[ADR {s_id}](./{matched_filename})")
            except Exception:
                superseded_links.append(f"ADR {s_id}")
        else:
            superseded_links.append(f"ADR {s_id}")

    if doc_cfg_modified:
        ki_utils.save_doc_config(doc_cfg)

    # 1. Automated Git Provenance
    git_info = []
    try:
        c_res = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=project_root, capture_output=True, text=True, timeout=2)
        if c_res.returncode == 0 and c_res.stdout.strip():
            b_res = subprocess.run(["git", "branch", "--show-current"], cwd=project_root, capture_output=True, text=True, timeout=2)
            branch_str = f" (branch: `{b_res.stdout.strip()}`)" if b_res.returncode == 0 and b_res.stdout.strip() else ""
            git_info.append(f"**Git Commit**: `{c_res.stdout.strip()}`{branch_str}")
        u_res = subprocess.run(["git", "config", "user.name"], cwd=project_root, capture_output=True, text=True, timeout=2)
        if u_res.returncode == 0 and u_res.stdout.strip():
            git_info.append(f"**Author**: {u_res.stdout.strip()}")
    except Exception:
        pass

    # 2. Automated Environment Snapshot
    import platform
    pkg_ver = ""
    try:
        import ki_manager
        pkg_ver = f" (ki-manager v{ki_manager.__version__})"
    except Exception:
        pass
    env_str = f"Python {platform.python_version()}, {platform.system()} {platform.release()}{pkg_ver}"

    # 3. Automated Scope & Affected Files + Related KIs
    affected_files = []
    if isinstance(affected_files_input, list):
        affected_files = [str(x).strip().replace("\\", "/") for x in affected_files_input if str(x).strip()]
    elif isinstance(affected_files_input, str) and affected_files_input.strip():
        affected_files = [f.strip().replace("\\", "/") for f in affected_files_input.splitlines() if f.strip()]

    if not affected_files:
        try:
            stat_res = subprocess.run(["git", "status", "--porcelain"], cwd=project_root, capture_output=True, text=True, timeout=2)
            if stat_res.returncode == 0 and stat_res.stdout.strip():
                for line in stat_res.stdout.splitlines():
                    parts = line.strip().split(maxsplit=1)
                    if len(parts) == 2:
                        p = parts[1].replace("\\", "/").strip('"')
                        if not p.endswith(".md"):
                            affected_files.append(p)
            if not affected_files:
                diff_res = subprocess.run(["git", "diff", "--name-only", "HEAD~1"], cwd=project_root, capture_output=True, text=True, timeout=2)
                if diff_res.returncode == 0 and diff_res.stdout.strip():
                    for line in diff_res.stdout.splitlines():
                        p = line.strip().replace("\\", "/").strip('"')
                        if p and not p.endswith(".md"):
                            affected_files.append(p)
        except Exception:
            pass

    affected_files = affected_files[:15]

    related_kis = set()
    scope_details = []
    for f in affected_files:
        matched_ki_for_file = []
        norm_f = f.lstrip("./")
        for k_path, k_meta in ki_entries.items():
            deps = k_meta.get("depends_on", [])
            for dep in deps:
                norm_dep = dep.lstrip("./")
                if norm_dep.endswith("/") and norm_f.startswith(norm_dep):
                    matched_ki_for_file.append(k_path)
                    related_kis.add(k_path)
                    break
                elif norm_f == norm_dep or norm_f.endswith(norm_dep):
                    matched_ki_for_file.append(k_path)
                    related_kis.add(k_path)
                    break
        if matched_ki_for_file:
            scope_details.append(f"- `{f}` (Related KI: {', '.join(f'`{k}`' for k in matched_ki_for_file)})")
        else:
            scope_details.append(f"- `{f}`")

    # Build ADR document
    meta_headers = [f"<!-- created: {today} -->", f"<!-- status: {status} -->"]
    if supersedes_list:
        meta_headers.append(f"<!-- supersedes: {', '.join(supersedes_list)} -->")

    header_block = "\n".join(meta_headers)

    header_info = [
        f"**Status**: {status}  ",
        f"**Date**: {today}  "
    ]
    if superseded_links:
        header_info.append(f"**Supersedes**: {', '.join(superseded_links)}  ")
    if git_info:
        for g in git_info:
            header_info.append(f"{g}  ")
    header_info.append(f"**Environment**: {env_str}  ")

    body_sections = [
        f"## Context and Problem\n{context}",
        f"## Decisions Made\n{decision}",
        f"## Consequences\n{consequences}"
    ]

    if rejected_alternatives:
        body_sections.append(f"## Alternatives Considered & Rejected\n{rejected_alternatives}")

    if invariants:
        body_sections.append(f"## Invariants & Rules for AI\n{invariants}")

    if scope_details:
        body_sections.append("## Scope & Affected Files\n" + "\n".join(scope_details))

    if verification:
        body_sections.append(f"## Verification\n{verification}")

    adr_content = f"{header_block}\n# ADR {next_id}: {title}\n\n" + "\n".join(header_info) + "\n\n" + "\n\n".join(body_sections) + "\n"

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
        depends_on=sorted(list(related_kis)),
        summary=f"ADR {next_id}: {title}",
        status=status,
    )

    import sync_agents_md
    sync_res = sync_agents_md.sync_agents_md()

    msg_lines = [f"Created ADR {adr_filename} at {adr_abs_path}"]
    if updated_old_adrs:
        msg_lines.append(f"Updated superseded ADRs: {', '.join(updated_old_adrs)}")
    if related_kis:
        msg_lines.append(f"Linked to Knowledge Items: {', '.join(sorted(related_kis))}")
    msg_lines.append(reg_msg)
    msg_lines.append(sync_res)

    return {
        "content": [{
            "type": "text",
            "text": "\n".join(msg_lines)
        }]
    }


def tool_read_file(args: dict) -> Any:
    """Read a Knowledge Item or ADR file with optional section filtering and character limit."""
    rel_path = args.get("rel_path", "").strip()
    if not rel_path:
        return "Error: 'rel_path' is required."

    try:
        target = resolve_know_path(rel_path, must_exist=True)
    except FileNotFoundError:
        return f"File not found: '{rel_path}'."
    except Exception as e:
        return f"Error: {e}"

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

    offset = 0
    if args.get("offset") is not None:
        try:
            offset = max(0, int(args["offset"]))
        except (ValueError, TypeError):
            offset = 0

    max_chars = args.get("max_chars")
    if max_chars is not None:
        try:
            mc = int(max_chars)
            if mc > 0:
                total_len = len(content)
                chunk = content[offset : offset + mc]
                if offset + mc < total_len:
                    content = chunk + f"\n\n... [truncated to {mc} characters, offset {offset} of {total_len}]"
                else:
                    content = chunk
            elif offset > 0:
                content = content[offset:]
        except (ValueError, TypeError):
            if offset > 0:
                content = content[offset:]
    elif offset > 0:
        content = content[offset:]

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
                ki_table = ki_utils.get_ki_list_table()
                adr_table = ki_utils.get_adr_table()
                if adr_table and not adr_table.startswith("No ADRs found"):
                    return f"Knowledge Items for this project:\n\n{ki_table}\n\nArchitecture Decision Records (ADRs):\n\n{adr_table}"
                return f"Knowledge Items for this project:\n\n{ki_table}"
            else:
                wf_path = (_WORKFLOWS_DIR / f"{doc}.md").resolve()
                if ki_utils.is_subpath(str(wf_path), str(_WORKFLOWS_DIR)) and wf_path.exists():
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

        # ─── Registry ───
        if name == "ki_migrate_project":
            sys.path.insert(0, str(_PACKAGE_DIR / "tools"))
            import scaffold
            return scaffold.migrate_project(str(get_project_root()))
        if name == "ki_register_project":
            config_path = args.get("config_path", "")
            workspace = args.get("workspace")
            inline_config = args.get("inline_config")
            # Accept directory too
            if config_path and os.path.isdir(ki_utils.normalize_path(config_path)):
                config_path = os.path.join(ki_utils.normalize_path(config_path), "ki_config.json")
            ok, msg = ki_utils.register_project(config_path=config_path, workspace=workspace, inline_config=inline_config)
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
            surviving = {}
            for k, v in reg["projects"].items():
                cfg_p = v.get("config_path")
                if cfg_p and os.path.exists(cfg_p):
                    surviving[k] = v
                elif not cfg_p and os.path.exists(k):
                    surviving[k] = v
            reg["projects"] = surviving
            ki_utils.save_registry(reg)
            return f"Pruned {before - len(reg['projects'])} stale project(s)."

        # ─── Coverage / Analysis ───
        if name == "audit_coverage":
            return run_script("audit_coverage.py")

        if name == "generate_dir_index":
            return run_script("generate_dir_index.py")
        if name == "update_last_verified":
            return tool_update_last_verified(args)
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
        if name == "check_ki_drift":
            cmd_args = []
            if args.get("ki_name"):
                cmd_args += ["--ki", args["ki_name"]]
            elif args.get("ki"):
                cmd_args += ["--ki", args["ki"]]
            else:
                cmd_args.append("--all")
            return run_script("check_ki_drift.py", cmd_args)
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
        if name == "ki_split_analyze":
            ki_name = args.get("ki_name", "").strip()
            if not ki_name:
                return {"isError": True, "content": [{"type": "text", "text": "Error: 'ki_name' is required."}]}
            sys.path.insert(0, str(_SCRIPTS_DIR))
            import split_ki
            res = split_ki.analyze_split(ki_name)
            if res.get("isError"):
                return {"isError": True, "content": [{"type": "text", "text": res.get("message", "Split analysis failed.")}]}
            return {"content": [{"type": "text", "text": res.get("markdown_report", json.dumps(res, indent=2))}]}
        if name == "ki_split":
            ki_name = args.get("ki_name", "").strip()
            target_a = args.get("target_a")
            target_b = args.get("target_b")
            if not ki_name or not target_a or not target_b:
                return {"isError": True, "content": [{"type": "text", "text": "Error: 'ki_name', 'target_a', and 'target_b' are required."}]}
            sys.path.insert(0, str(_SCRIPTS_DIR))
            import split_ki
            res = split_ki.apply_split(ki_name, target_a, target_b)
            if res.get("isError"):
                return {"isError": True, "content": [{"type": "text", "text": res.get("message", "Split failed.")}]}
            return {"content": [{"type": "text", "text": res.get("message", "Split applied.")}]}

        # ─── Config & ADR Management ───
        if name == "add_ki_to_config":
            return tool_add_ki_to_config(args)
        if name == "edit_doc_config":
            return tool_edit_doc_config(args)
        if name == "sync_agents_md":
            return tool_sync_agents_md(args)
        if name == "create_adr":
            return tool_create_adr(args)
        if name == "ki_lint":
            return tool_ki_lint(args)
        if name == "ki_sync":
            return tool_ki_sync(args)

        # ─── File Ops ───
        if name == "read_know_file":
            p = resolve_know_path(args["rel_path"], must_exist=True)
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            offset = 0
            if args.get("offset") is not None:
                try:
                    offset = max(0, int(args["offset"]))
                except (ValueError, TypeError):
                    offset = 0
            max_chars = args.get("max_chars")
            if max_chars is not None:
                try:
                    mc = int(max_chars)
                    if mc > 0:
                        total_len = len(content)
                        chunk = content[offset : offset + mc]
                        if offset + mc < total_len:
                            return chunk + f"\n\n... [truncated to {mc} characters, offset {offset} of {total_len}]"
                        return chunk
                except (ValueError, TypeError):
                    pass
            if offset > 0:
                return content[offset:]
            return content
        if name == "write_know_file":
            p = resolve_know_path(args["rel_path"], is_write=True, must_exist=False)
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
            p = resolve_know_path(args["rel_path"], is_write=True, must_exist=True)
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

        # ─── Navigation, Search & Read ───
        if name == "ki_list":
            scope = args.get("scope", "all")
            fmt = args.get("format", "markdown")
            flt = args.get("filter")
            status = args.get("status", "active")
            data = ki_utils.get_ki_list_data(scope=scope, filter_query=flt, status=status)
            if fmt == "json":
                return json.dumps(data, ensure_ascii=False, indent=2)
            return ki_utils.format_ki_list_markdown(data)

        if name == "ki_search":
            query = args.get("query", "").strip()
            scope = args.get("scope", "all")
            limit = int(args.get("limit", 5))
            offset = int(args.get("offset", 0))
            page = args.get("page")
            if page is not None:
                try:
                    page = int(page)
                except (ValueError, TypeError):
                    page = None
            include_inactive = bool(args.get("include_inactive", False))
            fmt = args.get("format", "markdown")
            res = ki_search.search_knowledge(
                query,
                project_root=get_project_root(),
                scope=scope,
                limit=limit,
                offset=offset,
                page=page,
                include_inactive=include_inactive,
            )
            if fmt == "json":
                return json.dumps(res, ensure_ascii=False, indent=2)
            return ki_search.format_search_markdown(res)

        if name == "ki_read":
            return tool_read_file(args)

        if name == "ki_context_for":
            files = args.get("files")
            if not isinstance(files, list) or not files:
                return "Error: 'files' must be a non-empty list of file or directory paths."
            try:
                max_chars = int(args.get("max_chars", 2000))
            except (ValueError, TypeError):
                max_chars = 2000
            include_poc = bool(args.get("include_poc", True))
            force = bool(args.get("force", False))
            res = ki_context.get_context_for(
                files=files,
                max_chars=max_chars,
                include_poc=include_poc,
                force=force,
                project_root=get_project_root(),
            )
            return res["text"]

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

                active_tool_names = {t["name"] for t in tools_to_write}
                for existing_json in target_dir.glob("*.json"):
                    if existing_json.stem not in active_tool_names:
                        try:
                            existing_json.unlink()
                            safe_log(f"Removed inactive tool schema: {existing_json.name}")
                        except Exception:
                            pass

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
    """Извлекает workspace URI из _meta нового протокола (2026-07-28)."""
    meta = params.get("_meta", {})
    client_info = meta.get("io.modelcontextprotocol/clientInfo", {})
    return client_info.get("workspaceUri") or client_info.get("rootUri")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] in ("lint", "install-hooks", "install-skills", "hook", "--version", "-v"):
        from ki_manager import cli
        cli.main()
        return

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
                        ki_utils._CACHE.clear()
                        safe_log(f"SET workspace via roots/list: {ki_utils.ACTIVE_WORKSPACE_PATH}")
                continue

            rid = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            # Извлекаем workspace из _meta при каждом запросе
            _ws = _extract_workspace_from_meta(params)
            if _ws:
                norm_ws = ki_utils.normalize_path(_ws)
                if norm_ws != ki_utils.ACTIVE_WORKSPACE_PATH:
                    ki_utils.ACTIVE_WORKSPACE_PATH = norm_ws
                    ki_utils._CACHE.clear()
                    safe_log(f"SET workspace via _meta: {ki_utils.ACTIVE_WORKSPACE_PATH}")

            def send(result_data):
                resp = json.dumps({"jsonrpc": "2.0", "id": rid, "result": result_data})
                safe_log(f"RESP: {resp}")
                sys.stdout.write(resp + "\n")
                sys.stdout.flush()

            if method in ("initialize", "server/discover"):
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

                if root_uri:
                    ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(root_uri)
                    ki_utils._CACHE.clear()
                    safe_log(f"SET workspace via initialize: {ki_utils.ACTIVE_WORKSPACE_PATH}")

                try:
                    import ki_manager
                    server_version = getattr(ki_manager, "__version__", importlib.metadata.version("ki-manager"))
                except Exception:
                    server_version = "2.3.0"

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

            elif method == "notifications/initialized":
                # Request roots from client for workspace detection
                req_roots = json.dumps({"jsonrpc": "2.0", "id": "get_roots", "method": "roots/list", "params": {}})
                safe_log(f"SEND_REQ: {req_roots}")
                sys.stdout.write(req_roots + "\n")
                sys.stdout.flush()

            elif method == "tools/list":
                facade.sync_dispatch_schemas(MCP_TOOLS)
                tools_list = COMPACT_TOOLS if tool_mode == "compact" else MCP_TOOLS
                send({"tools": tools_list, "ttlMs": 300000, "cacheScope": "global"})

            elif method == "tools/call":
                tool_name = params["name"]
                tool_args = params.get("arguments", {})
                if not ki_utils.ACTIVE_WORKSPACE_PATH:
                    _ws_arg = tool_args.get("path") or tool_args.get("project_path")
                    if _ws_arg:
                        ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(_ws_arg)
                        ki_utils._CACHE.clear()
                        safe_log(f"SET workspace via tool args: {ki_utils.ACTIVE_WORKSPACE_PATH}")
                captured_stdout = io.StringIO()
                with contextlib.redirect_stdout(captured_stdout):
                    result = handle_tool_call(tool_name, tool_args)
                leaked = captured_stdout.getvalue()
                if leaked:
                    safe_log(f"STDOUT_CAPTURED ({tool_name}): {leaked.strip()}")
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
                        ki_table = ki_utils.get_ki_list_table()
                        adr_table = ki_utils.get_adr_table()
                        if adr_table and not adr_table.startswith("No ADRs found"):
                            content = f"Knowledge Items for this project:\n\n{ki_table}\n\nArchitecture Decision Records (ADRs):\n\n{adr_table}"
                        else:
                            content = f"Knowledge Items for this project:\n\n{ki_table}"
                else:
                    wf_path = (_WORKFLOWS_DIR / f"{prompt_name}.md").resolve()
                    if ki_utils.is_subpath(str(wf_path), str(_WORKFLOWS_DIR)) and wf_path.exists():
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
                    {"uri": "ki://agent-rules.md", "name": "agent-rules.md (Harness & Agent Instructions Guide)", "mimeType": "text/markdown"},
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
                elif uri == "ki://agent-rules.md":
                    wf_path = (_WORKFLOWS_DIR / "agent-rules.md").resolve()
                    if wf_path.exists():
                        with open(wf_path, "r", encoding="utf-8") as f:
                            raw = f.read()
                        know_name = os.path.basename(ki_utils.get_knowledge_root()) or ".ki-base"
                        content = facade.render_instruction(raw, CURRENT_TOOL_MODE, know_name)
                    else:
                        content = "agent-rules.md not found."
                elif uri == "ki://knowledge-items.md":
                    ki_table = ki_utils.get_ki_list_table()
                    adr_table = ki_utils.get_adr_table()
                    if adr_table and not adr_table.startswith("No ADRs found"):
                        content = f"Knowledge Items for this project:\n\n{ki_table}\n\nArchitecture Decision Records (ADRs):\n\n{adr_table}"
                    else:
                        content = f"Knowledge Items for this project:\n\n{ki_table}"
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
                    wf_path = (_WORKFLOWS_DIR / wf_name).resolve()
                    if ki_utils.is_subpath(str(wf_path), str(_WORKFLOWS_DIR)) and wf_path.exists():
                        with open(wf_path, "r", encoding="utf-8") as f:
                            raw = f.read()
                            know_name = os.path.basename(ki_utils.get_knowledge_root()) or ".ki-base"
                            content = facade.render_instruction(raw, CURRENT_TOOL_MODE, know_name)
                
                # Physical resources in jail
                elif jail and uri.startswith("ki://"):
                    fname = uri.replace("ki://", "")
                    try:
                        fpath = validate_path(fname, is_write=False)
                        if os.path.exists(fpath) and os.path.isfile(fpath):
                            with open(fpath, "r", encoding="utf-8") as f:
                                content = f.read()
                    except Exception:
                        content = None
                
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

