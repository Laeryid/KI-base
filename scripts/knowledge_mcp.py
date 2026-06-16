import sys
import json
import os
import subprocess
from typing import Dict, Any, List

# Add the scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils

# --- Context Helpers ---
def get_jail_dir(): return ki_utils.get_knowledge_root()
def get_python_exe(): return ki_utils.get_python_exe()
def get_project_root(): return ki_utils.get_project_root()
def get_doc_config(): return ki_utils.get_doc_config()

def validate_path(rel_path: str, is_write: bool = False, forbidden_files: List[str] = None) -> str:
    jail = get_jail_dir()
    if not jail:
        raise PermissionError("Knowledge root not detected. Is this project registered?")
    normalized = os.path.normpath(rel_path)
    if normalized.startswith("..") or os.path.isabs(normalized):
        raise PermissionError(f"Access Denied: Path '{rel_path}' is outside sandbox.")
    target = os.path.abspath(os.path.join(jail, normalized))
    if not os.path.normcase(target).startswith(os.path.normcase(jail)):
        raise PermissionError(f"Access Denied: Jail breach detected.")
    if is_write:
        ext = os.path.splitext(target)[1].lower()
        if ext in {".py", ".pyc", ".bat", ".ps1", ".sh", ".exe", ".cmd", ".dll"}:
            raise PermissionError(f"Access Denied: Modifying scripts ({ext}) is forbidden.")
        if forbidden_files:
            filename = os.path.basename(target).lower()
            if filename in [f.lower() for f in forbidden_files]:
                raise PermissionError(f"Access Denied: Direct overwrite of '{filename}' is forbidden.")
    return target

# --- Tool Implementations ---

def run_script(script_name: str, args: List[str] = None):
    jail = get_jail_dir()
    if not jail: return "Error: Knowledge system not active for this path."
    script_path = os.path.join(jail, "scripts", script_name)
    if not os.path.exists(script_path): return f"Error: Script {script_name} not found."
    cmd = [get_python_exe(), script_path]
    if args: cmd.extend(args)
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=get_project_root())
    return result.stdout + (result.stderr if result.stderr else "")

# --- MCP Definitions ---

MCP_TOOLS = [
    # Registry Management
    {"name": "ki_register_project", "description": "Register a project in the global KI registry.", "inputSchema": {"type": "object", "properties": {"config_path": {"type": "string"}}}},
    {"name": "ki_list_projects", "description": "List all registered projects.", "inputSchema": {"type": "object"}},
    {"name": "ki_status", "description": "Check current project context.", "inputSchema": {"type": "object"}},
    {"name": "ki_prune_registry", "description": "Remove dead projects from registry.", "inputSchema": {"type": "object"}},
    
    # Core Knowledge Tools
    {"name": "audit_coverage", "description": "Run knowledge base coverage audit.", "inputSchema": {"type": "object"}},
    {"name": "sync_agents_md", "description": "Sync AGENTS.md with current KI state.", "inputSchema": {"type": "object"}},
    {"name": "generate_dir_index", "description": "Generate or update DIR_INDEX.md.", "inputSchema": {"type": "object"}},
    {"name": "analyze_dependencies", "description": "Analyze Python/TS imports to update 'Related KIs'.", "inputSchema": {"type": "object", "properties": {"ki_name": {"type": "string"}, "only_changed": {"type": "boolean"}}}},
    {"name": "analyze_all_dependencies", "description": "Analyze all KIs and update 'Related KIs'.", "inputSchema": {"type": "object"}},
    {"name": "find_unmapped_files", "description": "Find files not covered by any KI.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "analyze_module", "description": "Analyze directory stats with knowledge context.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "recursive": {"type": "boolean"}}}},
    {"name": "update_last_verified", "description": "Update last_verified date in KIs.", "inputSchema": {"type": "object"}},
    
    # File Operations
    {"name": "read_know_file", "description": "Read file inside .know.", "inputSchema": {"type": "object", "properties": {"rel_path": {"type": "string"}}}},
    {"name": "write_know_file", "description": "Safely create/overwrite file inside .know.", "inputSchema": {"type": "object", "properties": {"rel_path": {"type": "string"}, "content": {"type": "string"}}}},
    {"name": "edit_know_file", "description": "Safely edit file inside .know via replacement.", "inputSchema": {"type": "object", "properties": {"rel_path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}}},
    {"name": "make_know_dir", "description": "Create new directory inside .know.", "inputSchema": {"type": "object", "properties": {"rel_path": {"type": "string"}}}},
    
    # Git Operations
    {"name": "git_checkpoint", "description": "Save current knowledge state to Git.", "inputSchema": {"type": "object", "properties": {"message": {"type": "string"}}}},
    {"name": "git_restore", "description": "Restore knowledge files from Git.", "inputSchema": {"type": "object", "properties": {"target": {"type": "string"}, "revision": {"type": "string"}}}},
    {"name": "git_diff_secured", "description": "Get git diff for project files with safety checks.", "inputSchema": {"type": "object", "properties": {"paths": {"type": "string"}}}},
    
    # State
    {"name": "save_state", "description": "Commit current hash state.", "inputSchema": {"type": "object"}},
    {"name": "restore_mapping", "description": "Restore doc_config.json from KI files.", "inputSchema": {"type": "object"}}
]

MCP_PROMPTS = [
    {"name": "knowledge-instructions", "description": "Static instructions for AI agents (Forced Efficiency, Navigation, Security)."},
    {"name": "knowledge-items", "description": "Dynamic table of all available Knowledge Items (KI)."}
]

# --- Handlers ---

def handle_tool_call(name, args):
    try:
        if name == "ki_register_project": return ki_utils.register_project(args.get("config_path"))[1]
        if name == "ki_list_projects":
            reg = ki_utils.load_registry()
            return "\n".join([f"- {v['name']}: {k}" for k,v in reg['projects'].items()]) if reg['projects'] else "Empty."
        if name == "ki_status":
            match = ki_utils.find_project_by_cwd()
            return f"Active: {match['name']} at {match['know_root']}" if match else "Not registered."
        if name == "ki_prune_registry":
            reg = ki_utils.load_registry()
            initial = len(reg["projects"])
            reg["projects"] = {k: v for k, v in reg["projects"].items() if os.path.exists(v["config_path"])}
            ki_utils.save_registry(reg)
            return f"Pruned {initial - len(reg['projects'])} projects."

        # Engine-based scripts
        if name in ["audit_coverage", "sync_agents_md", "generate_dir_index", "update_last_verified"]:
            return run_script(f"{name}.py")
        if name == "analyze_all_dependencies": return run_script("ki_dependency_analyzer.py", ["--all"])
        if name == "analyze_dependencies":
            a = []
            if args.get("ki_name"): a.extend(["--ki", args["ki_name"]])
            if args.get("only_changed"): a.append("--changed")
            return run_script("ki_dependency_analyzer.py", a)
        if name == "find_unmapped_files": return run_script("find_unmapped_files.py", [args.get("path", ".")])
        if name == "analyze_module":
            a = [args.get("path", ".")]
            if args.get("recursive"): a.append("--recursive")
            return run_script("analyze_module.py", a)

        # File Ops
        if name == "read_know_file":
            with open(validate_path(args["rel_path"]), "r", encoding="utf-8") as f: return f.read()
        if name == "write_know_file":
            with open(validate_path(args["rel_path"], True), "w", encoding="utf-8") as f: f.write(args["content"])
            return "File updated."
        if name == "edit_know_file":
            p = validate_path(args["rel_path"], True)
            with open(p, "r", encoding="utf-8") as f: c = f.read()
            if args["old_text"] not in c: return "Error: old_text not found."
            with open(p, "w", encoding="utf-8") as f: f.write(c.replace(args["old_text"], args["new_text"]))
            return "File edited."
        if name == "make_know_dir":
            os.makedirs(validate_path(args["rel_path"]), exist_ok=True)
            return "Dir created."

        # Git
        if name == "git_checkpoint":
            jail, proj = get_jail_dir(), get_project_root()
            subprocess.run(["git", "add", os.path.relpath(jail, proj)], cwd=proj)
            return subprocess.run(["git", "commit", "-m", f"[AI] {args.get('message', 'Checkpoint')}"], cwd=proj, capture_output=True, text=True).stdout
        if name == "git_restore":
            return subprocess.run(["git", "checkout", args.get("revision", "HEAD"), "--", validate_path(args["target"])], cwd=get_project_root(), capture_output=True, text=True).stdout
        if name == "git_diff_secured":
            p = args.get("paths", "").split(",") if args.get("paths") else []
            return run_script("git_diff_secured.py", p) # Assuming specific script or engine call

        # State
        if name in ["save_state", "restore_mapping"]:
            jail = get_jail_dir()
            sys.path.insert(0, os.path.join(jail, "scripts"))
            from knowledge_engine import KnowledgeEngine
            ke = KnowledgeEngine(get_project_root(), os.path.basename(jail))
            return ke.restore_mapping() if name == "restore_mapping" else str(ke.save_state(ke.capture_full_state()))

        return f"Unknown tool: {name}"
    except Exception as e: return f"Error: {str(e)}"

# --- Main Loop ---

def main():
    while True:
        line = sys.stdin.readline()
        if not line: break
        try:
            req = json.loads(line)
            rid, method, params = req.get("id"), req.get("method"), req.get("params", {})
            
            if method == "initialize":
                res = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}, "prompts": {}, "resources": {}},
                    "serverInfo": {"name": "ki-universal", "version": "1.2.0"}
                }
                sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": res}) + "\n")
            
            elif method == "tools/list":
                sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"tools": MCP_TOOLS}}) + "\n")
            
            elif method == "tools/call":
                txt = handle_tool_call(params["name"], params.get("arguments", {}))
                sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": str(txt)}]}}) + "\n")
            
            elif method == "prompts/list":
                sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"prompts": MCP_PROMPTS}}) + "\n")
            
            elif method == "prompts/get":
                name = params.get("name")
                match = ki_utils.find_project_by_cwd()
                if not match: content = "No registered project context."
                else:
                    if name == "knowledge-instructions": content = ki_utils.get_instructions()
                    elif name == "knowledge-items": content = f"Review KIs before work:\n\n{ki_utils.get_ki_list_table()}"
                    else: content = "Unknown prompt."
                sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"messages": [{"role": "user", "content": {"type": "text", "text": content}}]}}) + "\n")
            
            elif method == "resources/list":
                jail = get_jail_dir()
                res = []
                if jail:
                    for f in ["doc_config.json", "DIR_INDEX.md"]:
                        if os.path.exists(os.path.join(jail, f)):
                            res.append({"uri": f"ki://{f}", "name": f, "mimeType": "text/plain"})
                sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"resources": res}}) + "\n")

            sys.stdout.flush()
        except Exception: pass

if __name__ == "__main__": main()
