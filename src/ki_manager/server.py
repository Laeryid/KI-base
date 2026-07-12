"""
ki_manager/server.py

MCP server entry point for ki-manager.
Implements MCP stdio protocol (JSON-RPC 2.0).

Usage:
    uvx ki-manager
    uvx ki-manager --workspace /path/to/project
    python -m ki_manager.server
"""

import sys
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

# ─── Package paths ────────────────────────────────────────────────────────────
_PACKAGE_DIR = Path(__file__).parent
_SCRIPTS_DIR = _PACKAGE_DIR / "scripts"
_WORKFLOWS_DIR = _PACKAGE_DIR / "workflows"

# Make ki_utils importable for server.py itself
sys.path.insert(0, str(_SCRIPTS_DIR))
import ki_utils

# ─── Logging ──────────────────────────────────────────────────────────────────
_LOG_DIR = Path.home() / ".ki_base" / "logs"


def safe_log(msg: str):
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = _LOG_DIR / f"mcp_{os.getpid()}.log"
        with open(log_file, "a", encoding="utf-8") as lf:
            lf.write(msg + "\n")
    except Exception:
        pass


# ─── Context helpers ──────────────────────────────────────────────────────────

def get_jail_dir() -> str:
    return ki_utils.get_knowledge_root()


def get_project_root() -> str:
    return ki_utils.get_project_root()


def get_doc_config() -> dict:
    return ki_utils.get_doc_config()


# ─── Global Virtual Content ───────────────────────────────────────────────────

GLOBAL_INSTRUCTIONS = """\
# Global AI Instructions for ki-manager

## 1. Project Navigation
- **`DIR_INDEX.md`** (`.ki-base/DIR_INDEX.md`) — project directory tree.
- **`doc_config.json`** (`.ki-base/doc_config.json`) — manifest of tracked artifacts.
- All Knowledge Items (KI) live in `.ki-base/knowledge/`.
- Architecture Decision Records (ADR) live in `.ki-base/decisions/` or `decisions/`.
- Start here: `.ki-base/knowledge/_OVERVIEW.ki.md`

## 2. Forced Efficiency (Anti-Hallucinations)
1. **Mandatory Planning Template**:
   Before making code changes, your initial plan (Implementation Plan) **MUST** include:
   - **Affected layers**: [which subsystems are affected]
   - **Read KIs**: [LIST of files from `.ki-base/knowledge/` which you read for this task]. *If the list is empty — read KIs before writing code!*
   - **KIs Constraints**: [which approaches are prohibited by current architecture]

2. **Strict Adherence**:
   - Always read relevant KIs before modifying a module.
   - After significant changes, run `audit_coverage` via MCP.
   - Use `git_checkpoint` to save knowledge snapshots.
   
## 3. Workflow-driven Execution
1. Check `ki://workflows/` resources or MCP Prompts if the user asks for a complex documentation task.
2. These workflows are your "operating system". You **MUST** follow their steps exactly as written.
"""

def get_adr_list(project_root: str, jail: str) -> str:
    """Dynamically scan for ADR files in decisions/ or .ki-base/decisions/."""
    candidates = [
        os.path.join(project_root, "decisions"),
        os.path.join(jail, "decisions")
    ]
    lines = ["# Architecture Decision Records (ADRs)\n"]
    found = False
    for c in candidates:
        if os.path.exists(c) and os.path.isdir(c):
            lines.append(f"Found in: {os.path.relpath(c, project_root)}")
            for f in sorted(os.listdir(c)):
                if f.endswith(".md"):
                    lines.append(f"- {f}")
                    found = True
            lines.append("")
    
    if not found:
        lines.append("No ADRs found in this project.")
    return "\n".join(lines)


# ─── Security ─────────────────────────────────────────────────────────────────

_FORBIDDEN_WRITE_EXT = {".py", ".pyc", ".bat", ".ps1", ".sh", ".exe", ".cmd", ".dll"}
_FORBIDDEN_WRITE_FILES = {"doc_config.json"}  # can only be modified via dedicated tools


def validate_path(rel_path: str, is_write: bool = False) -> str:
    jail = get_jail_dir()
    if not jail:
        raise PermissionError("Knowledge root not initialized. Run ki_init_project first.")

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


# ─── Script runner ────────────────────────────────────────────────────────────

def run_script(script_name: str, args: List[str] = None) -> dict:
    """Run a bundled analysis script in the context of the active project."""
    jail = get_jail_dir()
    if not jail:
        return {"isError": True, "content": [{"type": "text",
            "text": "Error: No active project. Run ki_init_project first."}]}

    script_path = _SCRIPTS_DIR / script_name
    if not script_path.exists():
        return {"isError": True, "content": [{"type": "text",
            "text": f"Error: Script '{script_name}' not found in package."}]}

    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=get_project_root(),
    )
    output = result.stdout + (result.stderr if result.stderr else "")
    return {"content": [{"type": "text", "text": output}]}


# ─── MCP Tool Definitions ─────────────────────────────────────────────────────

MCP_TOOLS = [
    # ── Initialization ──
    {
        "name": "ki_init_project",
        "description": (
            "Initialize .ki-base/ knowledge structure in a project directory. "
            "Creates ki_config.json, doc_config.json, AGENTS.md, DIR_INDEX.md, "
            "and a starter _OVERVIEW.ki.md. Registers the project in the global registry. "
            "Run this ONCE when adding ki-manager to a new project."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Absolute path to the project root"},
                "project_name": {"type": "string", "description": "Human-readable project name (optional, defaults to folder name)"},
                "language": {"type": "string", "description": "Primary language: python, typescript, etc. (default: python)"},
                "venv_python": {"type": "string", "description": "Explicit path to venv python.exe (auto-detected if omitted)"},
                "force": {"type": "boolean", "description": "Overwrite existing files (default: false)"},
            },
            "required": ["project_path"],
        },
    },
    # ── Registry ──
    {
        "name": "ki_migrate_project",
        "description": "Migrate a legacy .know/ project to the modern .ki-base/ architecture. Renames directories, updates config, and ensures _OVERVIEW.ki.md exists.",
        "inputSchema": {"type": "object"},
    },
    {
        "name": "ki_register_project",
        "description": "Register an existing project (with .ki-base/ki_config.json) in the global registry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "config_path": {"type": "string", "description": "Path to ki_config.json or .ki-base/ directory"},
            },
        },
    },
    {
        "name": "ki_list_projects",
        "description": "List all projects registered in the global KI registry.",
        "inputSchema": {"type": "object"},
    },
    {
        "name": "ki_status",
        "description": "Check which project is active for the current workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path to check (defaults to workspace root)"}},
        },
    },
    {
        "name": "ki_prune_registry",
        "description": "Remove projects from the registry whose directories no longer exist.",
        "inputSchema": {"type": "object"},
    },
    # ── Coverage & Audit ──
    {
        "name": "audit_coverage",
        "description": (
            "Run a knowledge base coverage audit. Compares tracked modules against "
            "registered KIs. Returns a coverage matrix with priority gaps. "
            "NOTE: every project folder, including utility/empty ones, must have a KI. "
            "CRITICAL AGENT RULE: After making significant architectural changes or creating "
            "new modules, you MUST run this tool to ensure documentation remains in sync."
        ),
        "inputSchema": {"type": "object"},
    },

    {
        "name": "generate_dir_index",
        "description": "Generate or update .ki-base/DIR_INDEX.md with directory structure.",
        "inputSchema": {"type": "object"},
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
    },
    {
        "name": "analyze_all_dependencies",
        "description": "Analyze all KI files and update their 'Related KIs' sections.",
        "inputSchema": {"type": "object"},
    },
    {
        "name": "find_unmapped_files",
        "description": "Find source files not covered by any KI.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Subdirectory to scan (optional)"}},
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
    },
    {
        "name": "update_last_verified",
        "description": "Update the last_verified date in all KI files to today.",
        "inputSchema": {"type": "object"},
    },
    # ── File Operations ──
    {
        "name": "read_know_file",
        "description": (
            "Read a Knowledge Item (KI) file inside the .ki-base/ directory. "
            "CRITICAL AGENT RULE: In this project, code is documented using ki-manager. "
            "Before planning implementation or modifying any code, you MUST use this tool "
            "to read .ki-base/knowledge/_OVERVIEW.ki.md and any other relevant KIs to "
            "understand the architecture, rules, and constraints."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"rel_path": {"type": "string", "description": "Path relative to .ki-base/"}},
            "required": ["rel_path"],
        },
    },
    {
        "name": "write_know_file",
        "description": "Create or overwrite a file inside .ki-base/ (scripts and executables are protected).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rel_path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["rel_path", "content"],
        },
    },
    {
        "name": "edit_know_file",
        "description": "Edit a file inside .ki-base/ by replacing a specific text fragment.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rel_path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["rel_path", "old_text", "new_text"],
        },
    },
    {
        "name": "make_know_dir",
        "description": "Create a new subdirectory inside .ki-base/.",
        "inputSchema": {
            "type": "object",
            "properties": {"rel_path": {"type": "string"}},
            "required": ["rel_path"],
        },
    },
    # ── Git Operations ──
    {
        "name": "git_checkpoint",
        "description": "Stage and commit all .ki-base/ changes to git.",
        "inputSchema": {
            "type": "object",
            "properties": {"message": {"type": "string", "description": "Commit message suffix"}},
        },
    },
    {
        "name": "git_restore",
        "description": "Restore a file inside .ki-base/ from a git revision.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "File path relative to .ki-base/"},
                "revision": {"type": "string", "description": "Git revision (default: HEAD)"},
            },
        },
    },
    {
        "name": "git_diff_secured",
        "description": "Get git diff for project files (sandboxed).",
        "inputSchema": {
            "type": "object",
            "properties": {"paths": {"type": "string", "description": "Comma-separated paths"}},
        },
    },
    # ── State ──
    {
        "name": "save_state",
        "description": "Capture and save file hash state to doc_state.json.",
        "inputSchema": {"type": "object"},
    },
    {
        "name": "restore_mapping",
        "description": "Restore doc_config.json from existing KI files.",
        "inputSchema": {"type": "object"},
    },
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


# ─── Tool Implementations ─────────────────────────────────────────────────────

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
                subprocess.run(["git", "add", t], cwd=project_root, check=True, capture_output=True)
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


# ─── Tool Dispatcher ──────────────────────────────────────────────────────────

def handle_tool_call(name: str, args: dict) -> Any:
    try:
        # ── Init ──
        if name == "ki_init_project":
            sys.path.insert(0, str(_PACKAGE_DIR / "tools"))
            from scaffold import init_project
            return init_project(args)

        # ── Registry ──
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
            return (f"Active: {match['name']} at {match['know_root']}" if match
                    else "No project active for current workspace.")
        if name == "ki_prune_registry":
            reg = ki_utils.load_registry()
            before = len(reg["projects"])
            reg["projects"] = {k: v for k, v in reg["projects"].items()
                               if os.path.exists(v["config_path"])}
            ki_utils.save_registry(reg)
            return f"Pruned {before - len(reg['projects'])} stale project(s)."

        # ── Coverage / Analysis ──
        if name == "audit_coverage":
            return run_script("audit_coverage.py")

        if name == "generate_dir_index":
            return run_script("generate_dir_index.py")
        if name == "update_last_verified":
            return run_script("update_last_verified.py")
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
        if name == "find_unmapped_files":
            return run_script("find_unmapped_files.py", [args.get("path", ".")])
        if name == "analyze_module":
            cmd_args = [args.get("path", ".")]
            if args.get("recursive"):
                cmd_args.append("--recursive")
            return run_script("analyze_module.py", cmd_args)

        # ── File Ops ──
        if name == "read_know_file":
            with open(validate_path(args["rel_path"]), "r", encoding="utf-8") as f:
                return f.read()
        if name == "write_know_file":
            p = validate_path(args["rel_path"], is_write=True)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(args["content"])
            return "File written."
        if name == "edit_know_file":
            p = validate_path(args["rel_path"], is_write=True)
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            if args["old_text"] not in content:
                return "Error: old_text not found in file."
            with open(p, "w", encoding="utf-8") as f:
                f.write(content.replace(args["old_text"], args["new_text"], 1))
            return "File edited."
        if name == "make_know_dir":
            os.makedirs(validate_path(args["rel_path"]), exist_ok=True)
            return "Directory created."

        # ── Git ──
        if name == "git_checkpoint":
            return tool_git_checkpoint(args)
        if name == "git_restore":
            return tool_git_restore(args)
        if name == "git_diff_secured":
            paths = args.get("paths", "").split(",") if args.get("paths") else []
            return run_script("git_diff_secured.py", paths)

        # ── State ──
        if name in ("save_state", "restore_mapping"):
            jail = get_jail_dir()
            sys.path.insert(0, str(_SCRIPTS_DIR))
            from knowledge_engine import KnowledgeEngine
            ke = KnowledgeEngine(get_project_root(), os.path.basename(jail))
            if name == "restore_mapping":
                return ke.restore_mapping()
            return str(ke.save_state(ke.capture_full_state()))

        return f"Unknown tool: {name}"

    except Exception as e:
        return f"Error in {name}: {str(e)}"


# ─── MCP Main Loop ────────────────────────────────────────────────────────────

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
    content = GLOBAL_INSTRUCTIONS
    for target_dir in candidates:
        # Only write if the parent MCP folder already exists (IDE is installed)
        if target_dir.parent.parent.exists():
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                instructions_path = target_dir / "instructions.md"
                instructions_path.write_text(content, encoding="utf-8")
                safe_log(f"Wrote instructions.md → {instructions_path}")
            except Exception as e:
                safe_log(f"Could not write instructions.md to {target_dir}: {e}")


def main():
    # Apply --workspace early so registry lookup works
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--workspace", type=str)
    known, _ = parser.parse_known_args()
    if known.workspace:
        ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(known.workspace)

    safe_log(f"ki-manager MCP server started (PID: {os.getpid()})")
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

            def send(result_data):
                resp = json.dumps({"jsonrpc": "2.0", "id": rid, "result": result_data})
                safe_log(f"RESP: {resp}")
                sys.stdout.write(resp + "\n")
                sys.stdout.flush()

            if method == "initialize":
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
                    safe_log(f"SET workspace via initialize: {ki_utils.ACTIVE_WORKSPACE_PATH}")

                send({
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}, "prompts": {}, "resources": {}},
                    "serverInfo": {"name": "ki-manager", "version": "2.0.0"},
                })

            elif method == "notifications/initialized":
                # Request roots from client for workspace detection
                req_roots = json.dumps({"jsonrpc": "2.0", "id": "get_roots", "method": "roots/list", "params": {}})
                safe_log(f"SEND_REQ: {req_roots}")
                sys.stdout.write(req_roots + "\n")
                sys.stdout.flush()

            elif method == "tools/list":
                send({"tools": MCP_TOOLS})

            elif method == "tools/call":
                result = handle_tool_call(params["name"], params.get("arguments", {}))
                if isinstance(result, dict) and "content" in result:
                    send(result)
                else:
                    send({"content": [{"type": "text", "text": str(result)}]})

            elif method == "prompts/list":
                send({"prompts": get_mcp_prompts()})

            elif method == "prompts/get":
                prompt_name = params.get("name")
                match = ki_utils.find_project_by_cwd()
                content = None
                if not match:
                    content = "No registered project. Run ki_init_project first."
                elif prompt_name == "knowledge-instructions":
                    content = GLOBAL_INSTRUCTIONS
                elif prompt_name == "knowledge-items":
                    content = f"Knowledge Items for this project:\n\n{ki_utils.get_ki_list_table()}"
                else:
                    wf_path = _WORKFLOWS_DIR / f"{prompt_name}.md"
                    if wf_path.exists():
                        with open(wf_path, "r", encoding="utf-8") as f:
                            content = f.read()
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
                send({"resources": resources})

            elif method == "resources/read":
                uri = params.get("uri", "")
                jail = get_jail_dir()
                content = None
                
                # Virtual resources
                if uri == "ki://instructions.md":
                    content = GLOBAL_INSTRUCTIONS
                elif uri == "ki://knowledge-items.md":
                    content = f"Knowledge Items for this project:\n\n{ki_utils.get_ki_list_table()}"
                elif uri == "ki://adr-list.md":
                    content = get_adr_list(get_project_root(), jail) if jail else "No active project."
                
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
