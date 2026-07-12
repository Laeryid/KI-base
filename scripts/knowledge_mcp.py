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
        raise PermissionError("Knowledge root not initialized.")
    normalized = ki_utils.normalize_path(rel_path, make_absolute=False)
    if not os.path.isabs(normalized):
        if normalized.startswith(".."):
            raise PermissionError(f"Access Denied: Path '{rel_path}' is outside sandbox.")
        target = os.path.abspath(os.path.join(jail, normalized))
    else:
        target = os.path.abspath(normalized)
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
    if not jail:
        return {"isError": True, "content": [{"type": "text", "text": "Error: Knowledge system not active for this path."}]}
    script_path = os.path.join(jail, "scripts", script_name)
    if not os.path.exists(script_path):
        return {"isError": True, "content": [{"type": "text", "text": f"Error: Script {script_name} not found."}]}
    cmd = [get_python_exe(), script_path]
    if args: cmd.extend(args)
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=get_project_root())
    output = result.stdout + (result.stderr if result.stderr else "")
    return {"content": [{"type": "text", "text": output}]}

# --- MCP Definitions ---

MCP_TOOLS = [
    # Registry Management
    {"name": "ki_register_project", "description": "Register a project in the global KI registry.", "inputSchema": {"type": "object", "properties": {"config_path": {"type": "string"}}}},
    {"name": "ki_list_projects", "description": "List all registered projects.", "inputSchema": {"type": "object"}},
    {"name": "ki_status", "description": "Check current project context.", "inputSchema": {"type": "object"}},
    {"name": "ki_prune_registry", "description": "Remove dead projects from registry.", "inputSchema": {"type": "object"}},
    
    # Core Knowledge Tools
    {"name": "audit_coverage", "description": "Run knowledge base coverage audit. Note: All project folders, including utility or empty ones, must be documented via KIs.", "inputSchema": {"type": "object"}},
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

# --- Tool Wrappers for Tests and MCP ---

def tool_audit_coverage(args: dict = None):
    return run_script("audit_coverage.py")

def tool_sync_agents_md(args: dict = None):
    return run_script("sync_agents_md.py")

def tool_generate_dir_index(args: dict = None):
    return run_script("generate_dir_index.py")

def tool_analyze_module(args: dict):
    p = args.get("path", ".")
    a = [p]
    if args.get("recursive"): a.append("--recursive")
    return run_script("analyze_module.py", a)

def tool_find_unmapped_files(args: dict):
    p = args.get("path", ".")
    return run_script("find_unmapped_files.py", [p])

def tool_analyze_dependencies(args: dict):
    ki_name = args.get("ki_name")
    only_changed = args.get("only_changed", False)
    cmd_args = []
    if ki_name:
        cmd_args.extend(["--ki", ki_name])
    if only_changed:
        cmd_args.append("--changed")
    if not cmd_args:
        return {"isError": True, "content": [{"type": "text", "text": "Error: Either 'ki_name' or 'only_changed' must be provided."}]}
    return run_script("ki_dependency_analyzer.py", cmd_args)

def tool_analyze_all_dependencies(args: dict = None):
    return run_script("ki_dependency_analyzer.py", ["--all"])

def tool_update_last_verified(args: dict = None):
    return run_script("update_last_verified.py")

def tool_git_checkpoint(args: dict):
    jail = get_jail_dir()
    if not jail:
        return {"isError": True, "content": [{"type": "text", "text": "Error: Knowledge root not found."}]}
    project_root = get_project_root()
    know_rel = os.path.relpath(jail, project_root)
    targets = [
        os.path.join(know_rel, "doc_config.json"),
        os.path.join(know_rel, "knowledge"),
        os.path.join(know_rel, "decisions")
    ]
    try:
        for t in targets:
            abs_t = os.path.join(project_root, t)
            if os.path.exists(abs_t):
                subprocess.run(["git", "add", t], cwd=project_root, check=True, capture_output=True)
        status = subprocess.run(["git", "diff", "--quiet", "--cached"], cwd=project_root)
        if status.returncode == 0:
            return {"content": [{"type": "text", "text": "No changes to checkpoint."}]}
        user_msg = args.get("message", "Checkpoint")
        message = f"[AI] {user_msg}"
        result = subprocess.run(
            ["git", "commit", "-m", message, "--author=Antigravity AI <ai-assistant@ki.base>"], 
            cwd=project_root, 
            capture_output=True, text=True, encoding="utf-8",
            check=True
        )
        return {"content": [{"type": "text", "text": f"Checkpoint created: {message}\n{result.stdout}"}]}
    except subprocess.CalledProcessError as e:
        stderr = e.stderr if e.stderr else str(e)
        return {"isError": True, "content": [{"type": "text", "text": f"Git Error: {stderr}"}]}

def tool_git_restore(args: dict):
    target_rel = args.get("target", "doc_config.json")
    revision = args.get("revision", "HEAD")
    jail = get_jail_dir()
    if revision.startswith("-") or ";" in revision or "|" in revision:
        return {"isError": True, "content": [{"type": "text", "text": "Error: Invalid or suspicious revision string."}]}
    try:
        target_abs = validate_path(target_rel)
    except PermissionError as e:
        return {"isError": True, "content": [{"type": "text", "text": str(e)}]}
    try:
        result = subprocess.run(
            ["git", "checkout", revision, "--", target_abs],
            cwd=get_project_root(),
            capture_output=True, text=True, encoding="utf-8",
            check=True
        )
        return {"content": [{"type": "text", "text": f"Restored '{target_rel}' from {revision}.\n{result.stdout}"}]}
    except subprocess.CalledProcessError as e:
        stderr = e.stderr if e.stderr else str(e)
        return {"isError": True, "content": [{"type": "text", "text": f"Git Error: {stderr}"}]}

def tool_git_diff_secured(args: dict):
    p = args.get("paths", "").split(",") if args.get("paths") else []
    return run_script("git_diff_secured.py", p)

# --- Handlers ---

def handle_tool_call(name, args):
    try:
        if name == "ki_register_project": return ki_utils.register_project(args.get("config_path"))[1]
        if name == "ki_list_projects":
            reg = ki_utils.load_registry()
            return "\n".join([f"- {v['name']}: {k}" for k,v in reg['projects'].items()]) if reg['projects'] else "Empty."
        if name == "ki_status":
            match = ki_utils.find_project_by_cwd(args.get("path"))
            return f"Active: {match['name']} at {match['know_root']}" if match else "Not registered."
        if name == "ki_prune_registry":
            reg = ki_utils.load_registry()
            initial = len(reg["projects"])
            reg["projects"] = {k: v for k, v in reg["projects"].items() if os.path.exists(v["config_path"])}
            ki_utils.save_registry(reg)
            return f"Pruned {initial - len(reg['projects'])} projects."

        # Engine-based scripts
        if name == "audit_coverage": return tool_audit_coverage(args)
        if name == "sync_agents_md": return tool_sync_agents_md(args)
        if name == "generate_dir_index": return tool_generate_dir_index(args)
        if name == "update_last_verified": return tool_update_last_verified(args)
        if name == "analyze_all_dependencies": return tool_analyze_all_dependencies(args)
        if name == "analyze_dependencies": return tool_analyze_dependencies(args)
        if name == "find_unmapped_files": return tool_find_unmapped_files(args)
        if name == "analyze_module": return tool_analyze_module(args)

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
        if name == "git_checkpoint": return tool_git_checkpoint(args)
        if name == "git_restore": return tool_git_restore(args)
        if name == "git_diff_secured": return tool_git_diff_secured(args)

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

def safe_log(msg: str):
    try:
        log_file = f"C:\\Experiments\\ki-global-server\\mcp_debug_{os.getpid()}.log"
        with open(log_file, "a", encoding="utf-8") as lf:
            lf.write(msg + "\n")
    except Exception:
        pass

def main():
    safe_log(f"MCP Server started (PID: {os.getpid()})")
    while True:
        line = sys.stdin.readline()
        if not line: break
        
        safe_log(f"REQ: {line.strip()}")
        
        rid = None
        try:
            req = json.loads(line)
            rid = req.get("id")
            
            # Перехватываем ответ на наш запрос get_roots
            if req.get("id") == "get_roots":
                result = req.get("result", {})
                roots = result.get("roots", [])
                if roots and isinstance(roots, list) and len(roots) > 0:
                    root_uri = roots[0].get("uri")
                    if root_uri:
                        ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(root_uri)
                        safe_log(f"SET ACTIVE_WORKSPACE_PATH via get_roots to: {ki_utils.ACTIVE_WORKSPACE_PATH}")
                continue

            rid, method, params = req.get("id"), req.get("method"), req.get("params", {})
            
            def send_res(result_data):
                resp = {"jsonrpc": "2.0", "id": rid, "result": result_data}
                resp_str = json.dumps(resp)
                safe_log(f"RESP: {resp_str}")
                sys.stdout.write(resp_str + "\n")
                sys.stdout.flush()

            if method == "initialize":
                root_uri = params.get("rootUri")
                if not root_uri and params.get("workspaceFolders"):
                    folders = params.get("workspaceFolders")
                    if folders and isinstance(folders, list) and len(folders) > 0:
                        root_uri = folders[0].get("uri")
                if not root_uri:
                    # Recursive search for any file:/// uri in params
                    def find_uri(d):
                        if isinstance(d, dict):
                            for v in d.values():
                                res = find_uri(v)
                                if res: return res
                        elif isinstance(d, list):
                            for v in d:
                                res = find_uri(v)
                                if res: return res
                        elif isinstance(d, str) and (d.startswith("file://") or (len(d) > 2 and d[1] == ':' and '\\' in d)):
                            return d
                        return None
                    root_uri = find_uri(params)

                if root_uri:
                    ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(root_uri)
                    safe_log(f"SET ACTIVE_WORKSPACE_PATH to: {ki_utils.ACTIVE_WORKSPACE_PATH}")

                res = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}, "prompts": {}, "resources": {}},
                    "serverInfo": {"name": "ki-universal", "version": "1.2.0"}
                }
                send_res(res)
            
            elif method == "notifications/initialized":
                # Отправляем запрос roots/list клиенту
                req_roots = {"jsonrpc": "2.0", "id": "get_roots", "method": "roots/list", "params": {}}
                req_str = json.dumps(req_roots)
                safe_log(f"SEND_REQ: {req_str}")
                sys.stdout.write(req_str + "\n")
                sys.stdout.flush()
            
            elif method == "tools/list":
                send_res({"tools": MCP_TOOLS})
            
            elif method == "tools/call":
                res_val = handle_tool_call(params["name"], params.get("arguments", {}))
                if isinstance(res_val, dict) and "content" in res_val:
                    send_res(res_val)
                else:
                    send_res({"content": [{"type": "text", "text": str(res_val)}]})
            
            elif method == "prompts/list":
                send_res({"prompts": MCP_PROMPTS})
            
            elif method == "prompts/get":
                name = params.get("name")
                match = ki_utils.find_project_by_cwd()
                if not match: content = "No registered project context."
                else:
                    if name == "knowledge-instructions": content = ki_utils.get_instructions()
                    elif name == "knowledge-items": content = f"Review KIs before work:\n\n{ki_utils.get_ki_list_table()}"
                    else: content = "Unknown prompt."
                send_res({"messages": [{"role": "user", "content": {"type": "text", "text": content}}]})
            
            elif method == "resources/list":
                jail = get_jail_dir()
                res = []
                if jail:
                    for f in ["doc_config.json", "DIR_INDEX.md"]:
                        if os.path.exists(os.path.join(jail, f)):
                            res.append({"uri": f"ki://{f}", "name": f, "mimeType": "text/plain"})
                send_res({"resources": res})

        except Exception as e:
            safe_log(f"ERROR: {str(e)}")
            try:
                resp = {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "error": {
                        "code": -32603,
                        "message": str(e)
                    }
                }
                resp_str = json.dumps(resp)
                sys.stdout.write(resp_str + "\n")
                sys.stdout.flush()
            except Exception as internal_err:
                safe_log(f"CRITICAL ERROR sending error response: {str(internal_err)}")

if __name__ == "__main__":
    main()
