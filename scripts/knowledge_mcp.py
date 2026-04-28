import sys
import json
import os
import subprocess
import argparse
from typing import Dict, Any, List

# --- Configuration and Security ---
# Add the scripts directory to path so ki_utils is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils

def get_jail_dir(): return ki_utils.get_knowledge_root_strict()
def get_python_exe(): return ki_utils.get_python_exe()
def get_project_root(): return ki_utils.get_project_root()
def get_doc_config(): return ki_utils.get_doc_config()

def get_ms_cfg(): return ki_utils.get_ki_cfg().get("knowledge_system", {}).get("mcp_server", {})
def get_tools_cfg(): return DEFAULT_TOOLS


def validate_path(rel_path: str, is_write: bool = False, forbidden_files: List[str] = None) -> str:
    jail = get_jail_dir()
    if not jail:
        raise PermissionError("Knowledge root not initialized.")
    normalized = os.path.normpath(rel_path)
    if normalized.startswith("..") or os.path.isabs(normalized):
        raise PermissionError(f"Access Denied: Path '{rel_path}' is outside sandbox.")

    target = os.path.abspath(os.path.join(jail, normalized))
    
    # Windows/macOS case-insensitive filesystem check
    if not os.path.normcase(target).startswith(os.path.normcase(jail)):
        raise PermissionError(f"Access Denied: Jail breach detected for '{rel_path}'.")

    if is_write:
        ext = os.path.splitext(target)[1].lower()
        if ext in {".py", ".pyc", ".bat", ".ps1", ".sh", ".exe", ".cmd", ".dll"}:
            raise PermissionError(
                f"Access Denied: Modifying executable or script files ({ext}) is forbidden."
            )
        
        if forbidden_files:
            filename = os.path.basename(target).lower()
            if filename in [f.lower() for f in forbidden_files]:
                raise PermissionError(
                    f"Access Denied: Direct overwrite of '{filename}' is forbidden. Use 'edit_know_file' for partial updates."
                )

    return target


# --- Tool Definitions ---

DEFAULT_TOOLS = [
    {
        "name": "audit_coverage",
        "description": "Run knowledge base coverage audit. Returns coverage matrix and recommendations.",
        "method": "audit_coverage",
        "args": []
    },
    {
        "name": "sync_agents_md",
        "description": "Synchronize AGENTS.md with current KI state.",
        "method": "sync_agents_md",
        "args": []
    },
    {
        "name": "generate_dir_index",
        "description": "Generate or update DIR_INDEX.md.",
        "method": "generate_dir_index",
        "args": []
    },
    {
        "name": "check_changes",
        "description": "Check changes in tracked project files.",
        "method": "check_changes",
        "args": []
    },
    {
        "name": "restore_mapping",
        "description": "Restore doc_config.json mapping from KI markdown files.",
        "method": "restore_mapping",
        "args": []
    },
    {
        "name": "save_state",
        "description": "Commit current hash state (doc_state.json).",
        "method": "save_state",
        "args": []
    },
    {
        "name": "analyze_dependencies",
        "description": "Analyze Python/TS imports to update 'Related KIs'.",
        "method": "analyze_dependencies",
        "args": [
            {"name": "ki_name", "type": "string", "description": "Specific KI file to analyze"},
            {"name": "only_changed", "type": "boolean", "description": "Analyze only modified Files/KIs"}
        ]
    },
    {
        "name": "analyze_all_dependencies",
        "description": "Analyze all KIs in doc_config.json and update their 'Related KIs'.",
        "method": "analyze_all_dependencies",
        "args": []
    },
    {
        "name": "find_unmapped_files",
        "description": "Find files in a directory that are not covered by any KI.",
        "method": "find_unmapped_files",
        "args": [
            {"name": "path", "type": "string", "description": "Relative path from project root to scan"}
        ]
    },
    {
        "name": "analyze_module",
        "description": "Analyze directory stats with knowledge coverage context.",
        "method": "analyze_module",
        "args": [
            {"name": "path", "type": "string", "description": "Path to analyze"},
            {"name": "recursive", "type": "boolean", "description": "Depth of analysis"}
        ]
    },
    {
        "name": "read_know_file",
        "description": "Read file inside .know.",
        "method": "read_file",
        "args": [
            {"name": "rel_path", "type": "string", "description": "Path relative to .know/"}
        ]
    },
    {
        "name": "write_know_file",
        "description": "Safely create or overwrite file inside .know.",
        "method": "write_file",
        "args": [
            {"name": "rel_path", "type": "string", "description": "Path relative to .know/"},
            {"name": "content", "type": "string", "description": "File content"}
        ]
    },
    {
        "name": "edit_know_file",
        "description": "Safely edit file inside .know via text replacement.",
        "method": "edit_file",
        "args": [
            {"name": "rel_path", "type": "string", "description": "Path relative to .know/"},
            {"name": "old_text", "type": "string", "description": "Text to replace"},
            {"name": "new_text", "type": "string", "description": "New text"}
        ]
    },
    {
        "name": "make_know_dir",
        "description": "Create new directory inside .know.",
        "method": "make_dir",
        "args": [
            {"name": "rel_path", "type": "string", "description": "Path relative to .know/"}
        ]
    },
    {
        "name": "git_checkpoint",
        "description": "Save current knowledge state (doc_config and KIs) to Git.",
        "method": "git_checkpoint",
        "args": [
            {"name": "message", "type": "string", "description": "Commit message"}
        ]
    },
    {
        "name": "git_restore",
        "description": "Restore knowledge files from Git.",
        "method": "git_restore",
        "args": [
            {"name": "target", "type": "string", "description": "Path to restore (e.g. 'doc_config.json' or '.')"},
            {"name": "revision", "type": "string", "description": "Git revision (e.g. 'HEAD', 'HEAD~1', or commit hash)"}
        ]
    },
    {
        "name": "git_diff_secured",
        "description": "Get git diff for core project files with path safety and git tracking checks (Safe-to-run).",
        "method": "git_diff_secured",
        "args": []
    },
    {
        "name": "update_last_verified",
        "description": "Update last_verified date in KIs affected by code changes.",
        "method": "update_last_verified",
        "args": []
    }
]



# --- Tool Implementations ---

def run_script(script_name: str, args: List[str] = None):
    jail = get_jail_dir()
    if not jail:
        return {"isError": True, "content": [{"type": "text",
                "text": "Error: Knowledge system not active here."}]}

    scripts_dir = os.path.join(jail, "scripts")
    script_path = os.path.join(scripts_dir, script_name)

    if not os.path.exists(script_path):
        script_path = os.path.join(jail, script_name)

    if not os.path.exists(script_path):
        return {"isError": True, "content": [{"type": "text",
                "text": f"Error: Script {script_name} not found."}]}

    cmd = [get_python_exe(), script_path]
    if args:
        cmd.extend(args)

    result = subprocess.run(
        cmd,
        capture_output=True, text=True, encoding="utf-8",
        cwd=get_project_root()  # run from project root
    )
    return {"content": [{"type": "text",
            "text": result.stdout + (result.stderr if result.stderr else "")}]}


def tool_audit_coverage(args):   return run_script("audit_coverage.py")
def tool_sync_agents_md(args):   return run_script("sync_agents_md.py")
def tool_generate_dir_index(args): return run_script("generate_dir_index.py")


def tool_analyze_module(args):
    path = args.get("path", ".")
    recursive = args.get("recursive", False)
    cmd_args = [path]
    if recursive:
        cmd_args.append("--recursive")
    return run_script("analyze_module.py", cmd_args)


def tool_find_unmapped_files(args):
    path = args.get("path", ".")
    return run_script("find_unmapped_files.py", [path])


def tool_analyze_dependencies(args):
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


def tool_analyze_all_dependencies(args):
    return run_script("ki_dependency_analyzer.py", ["--all"])


def tool_check_changes(args):
    jail = get_jail_dir()
    if not jail:
        return {"isError": True, "content": [{"type": "text", "text": "Error: Knowledge system not active."}]}
    sys.path.insert(0, os.path.join(jail, "scripts"))
    from knowledge_engine import KnowledgeEngine
    project_root = get_project_root()
    knowledge_root_name = os.path.basename(jail)
    ke = KnowledgeEngine(project_root, knowledge_root_name)
    modified, new, deleted = ke.check_for_changes()
    res = f"Modified: {modified}\nNew: {new}\nDeleted: {deleted}"
    return {"content": [{"type": "text", "text": res}]}


def tool_restore_mapping(args):
    jail = get_jail_dir()
    if not jail:
        return {"isError": True, "content": [{"type": "text", "text": "Error: Knowledge system not active."}]}
    sys.path.insert(0, os.path.join(jail, "scripts"))
    from knowledge_engine import KnowledgeEngine
    project_root = get_project_root()
    knowledge_root_name = os.path.basename(jail)
    ke = KnowledgeEngine(project_root, knowledge_root_name)
    res = ke.restore_mapping()
    return {"content": [{"type": "text", "text": res}]}


def tool_save_state(args):
    jail = get_jail_dir()
    if not jail:
        return {"isError": True, "content": [{"type": "text", "text": "Error: Knowledge system not active."}]}
    sys.path.insert(0, os.path.join(jail, "scripts"))
    from knowledge_engine import KnowledgeEngine
    project_root = get_project_root()
    knowledge_root_name = os.path.basename(jail)
    ke = KnowledgeEngine(project_root, knowledge_root_name)
    state = ke.capture_full_state()
    ke.save_state(state)
    return {"content": [{"type": "text", "text": f"State saved: {len(state)} files tracked."}]}


def tool_write_file(args):
    path = validate_path(args.get("rel_path"), is_write=True, forbidden_files=["doc_config.json"])
    content = args.get("content", "")
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return {"content": [{"type": "text", "text": f"File created/updated: {args.get('rel_path')}"}]}


def tool_edit_file(args):
    path = validate_path(args.get("rel_path"), is_write=True)
    old_text = args.get("old_text")
    new_text = args.get("new_text")

    if not os.path.exists(path):
        return {"isError": True, "content": [{"type": "text",
                "text": f"Error: File {args.get('rel_path')} not found."}]}

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if old_text not in content:
        return {"isError": True, "content": [{"type": "text",
                "text": "Error: old_text not found in file."}]}

    new_content = content.replace(old_text, new_text)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    return {"content": [{"type": "text", "text": f"File edited: {args.get('rel_path')}"}]}


def tool_make_dir(args):
    path = validate_path(args.get("rel_path"))
    os.makedirs(path, exist_ok=True)
    return {"content": [{"type": "text", "text": f"Directory created: {args.get('rel_path')}"}]}


def tool_git_checkpoint(args):
    user_msg = args.get("message", "Knowledge checkpoint")
    message = f"[AI] {user_msg}"
    
    jail = get_jail_dir()
    if not jail:
        return {"isError": True, "content": [{"type": "text", "text": "Error: Knowledge root not found."}]}
    
    project_root = get_project_root()
    know_rel = os.path.relpath(jail, project_root)
    
    # We stage allowed files (knowledge, decisions, doc_config.json)
    # Using relative paths is more reliable for Git across different OS
    targets = [
        os.path.join(know_rel, "doc_config.json"),
        os.path.join(know_rel, "knowledge"),
        os.path.join(know_rel, "decisions")
    ]
    
    try:
        # 1. Add files (only if they exist)
        for t in targets:
            abs_t = os.path.join(project_root, t)
            if os.path.exists(abs_t):
                subprocess.run(["git", "add", t], cwd=project_root, check=True, capture_output=True)
        
        # 2. Check if there are changes to commit
        status = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=project_root)
        if status.returncode == 0:
            return {"content": [{"type": "text", "text": "No changes to checkpoint."}]}

        # 3. Commit with specific author metadata
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


def tool_git_restore(args):
    target_rel = args.get("target", "doc_config.json")
    revision = args.get("revision", "HEAD")
    jail = get_jail_dir()
    
    # 1. Security: Basic revision validation (prevent flag injection)
    if revision.startswith("-") or ";" in revision or "|" in revision:
        return {"isError": True, "content": [{"type": "text", "text": "Error: Invalid or suspicious revision string."}]}

    # 2. Validate target is inside .know
    try:
        target_abs = validate_path(target_rel)
    except PermissionError as e:
        return {"isError": True, "content": [{"type": "text", "text": str(e)}]}

    try:
        # 3. Use git checkout (stable across versions)
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


def tool_git_diff_secured(args):
    project_root = get_project_root()
    # Fixed paths for security and specificity
    targets = [
        "app/core/orchestration/nodes/agent_node.py",
        "app/core/orchestration/nodes/router_node.py"
    ]
    
    results = []
    for t in targets:
        # Use project_root to ensure we stay within the workspace
        abs_t = os.path.normpath(os.path.join(project_root, t))
        
        # Security: ensure the path is actually inside project_root
        if not os.path.abspath(abs_t).startswith(os.path.abspath(project_root)):
            results.append(f"Error: Path safety violation for '{t}'.")
            continue

        # Check 1: File exists on disk
        if not os.path.exists(abs_t):
            results.append(f"Error: File '{t}' not found on disk.")
            continue
            
        # Check 2: File is tracked by Git
        git_check = subprocess.run(
            ["git", "ls-files", "--error-unmatch", t],
            cwd=project_root, capture_output=True, text=True
        )
        if git_check.returncode != 0:
            results.append(f"Error: File '{t}' is not tracked by Git or not in this repository.")
            continue
        
        # Get diff
        diff_res = subprocess.run(
            ["git", "diff", t],
            cwd=project_root, capture_output=True, text=True, encoding="utf-8"
        )
        
        if diff_res.returncode != 0:
            results.append(f"Error: Failed to get diff for '{t}'. {diff_res.stderr}")
        elif diff_res.stdout:
            results.append(f"--- Diff for {t} ---\n{diff_res.stdout}")
        else:
            results.append(f"No changes in {t}.")
            
    return {"content": [{"type": "text", "text": "\n\n".join(results)}]}


def tool_update_last_verified(args):
    jail = get_jail_dir()
    if not jail:
        return {"isError": True, "content": [{"type": "text", "text": "Error: Knowledge system not active."}]}
    
    sys.path.insert(0, os.path.join(jail, "scripts"))
    from knowledge_engine import KnowledgeEngine
    import re
    from datetime import datetime
    
    project_root = get_project_root()
    knowledge_root_name = os.path.basename(jail)
    ke = KnowledgeEngine(project_root, knowledge_root_name)
    
    # 1. Identify changed code files
    modified, new, deleted = ke.check_for_changes()
    changed_code = [f for f in (modified + new) if not f.startswith((".know", ".git"))]
    
    if not changed_code:
        return {"content": [{"type": "text", "text": "No code changes detected. No KIs updated."}]}
    
    # 2. Map code changes to KIs
    affected_ki_map = ke.get_affected_ki_map(changed_code)
    
    if not affected_ki_map:
        return {"content": [{"type": "text", "text": "No KIs depend on the changed code files."}]}
    
    today = datetime.now().strftime("%Y-%m-%d")
    updated_kis = []
    
    # 3. Update each affected KI
    for ki_rel_path in affected_ki_map.keys():
        # ki_rel_path is something like "knowledge/KI_name.md" relative to .know/
        abs_ki_path = os.path.join(jail, ki_rel_path)
        
        if not os.path.exists(abs_ki_path):
            continue
            
        with open(abs_ki_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Regex to find and replace last_verified: YYYY-MM-DD
        new_content = re.sub(
            r'last_verified: \d{4}-\d{2}-\d{2}',
            f'last_verified: {today}',
            content
        )
        
        # If the tag is missing, we could add it, but for now we follow the rule
        # of updating existing ones.
        if new_content != content:
            with open(abs_ki_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            updated_kis.append(ki_rel_path)
            
    if not updated_kis:
        return {"content": [{"type": "text", "text": "No KIs contained the 'last_verified' tag to update."}]}
        
    res = f"Updated 'last_verified' to {today} for {len(updated_kis)} KI files:\n" + "\n".join(updated_kis)
    return {"content": [{"type": "text", "text": res}]}


def tool_read_file(args):
    path = validate_path(args.get("rel_path"))
    if not os.path.exists(path):
        return {"isError": True, "content": [{"type": "text",
                "text": f"Error: File {args.get('rel_path')} not found."}]}
    if os.path.isdir(path):
        return {"isError": True, "content": [{"type": "text",
                "text": f"Error: {args.get('rel_path')} is a directory."}]}

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"content": [{"type": "text", "text": content}]}


METHODS = {
    "audit_coverage":    tool_audit_coverage,
    "sync_agents_md":    tool_sync_agents_md,
    "generate_dir_index": tool_generate_dir_index,
    "check_changes":     tool_check_changes,
    "restore_mapping":   tool_restore_mapping,
    "save_state":        tool_save_state,
    "write_file":        tool_write_file,
    "edit_file":         tool_edit_file,
    "make_dir":          tool_make_dir,
    "read_file":         tool_read_file,
    "analyze_module":     tool_analyze_module,
    "analyze_dependencies": tool_analyze_dependencies,
    "analyze_all_dependencies": tool_analyze_all_dependencies,
    "find_unmapped_files": tool_find_unmapped_files,
    "git_checkpoint": tool_git_checkpoint,
    "git_restore": tool_git_restore,
    "git_diff_secured": tool_git_diff_secured,
    "update_last_verified": tool_update_last_verified,
}


# --- MCP Protocol (JSON-RPC) ---

def send_response(request_id, result=None, error=None):
    response = {"jsonrpc": "2.0", "id": request_id}
    if result is not None:
        response["result"] = result
    if error is not None:
        response["error"] = error
    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    # Windows UTF-8 fix
    if sys.platform == "win32":
        import io
        sys.stdin  = io.TextIOWrapper(sys.stdin.buffer,  encoding="utf-8", errors="replace")
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        req_id  = request.get("id")
        method  = request.get("method")
        params  = request.get("params", {})

        if method == "initialize":
            jail = get_jail_dir()
            send_response(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "prompts": {},
                    "resources": {"subscribe": True},
                    "roots": {"listChanged": True}
                },
                "serverInfo": {
                    "name":    get_ms_cfg().get("name",    "KnowledgeManager"),
                    "version": get_ms_cfg().get("version", "1.1.0"),
                    "description": f"Serving knowledge from: {jail}"
                }
            })

        elif method == "tools/list":
            if not get_jail_dir():
                send_response(req_id, {"tools": []})
                continue

            tools = []
            for t in get_tools_cfg():
                tool_def = {
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": {"type": "object", "properties": {}, "required": []}
                }
                for arg in t.get("args", []):
                    tool_def["inputSchema"]["properties"][arg["name"]] = {
                        "type": arg["type"],
                        "description": arg["description"]
                    }
                    tool_def["inputSchema"]["required"].append(arg["name"])
                tools.append(tool_def)
            send_response(req_id, {"tools": tools})

        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})

            tools_cfg = get_tools_cfg()
            target_tool = next((t for t in tools_cfg if t["name"] == tool_name), None)
            if not target_tool:
                send_response(req_id, error={"code": -32601,
                              "message": f"Tool {tool_name} not found"})
                continue

            internal_method = target_tool.get("method") or target_tool["name"]
            if internal_method in METHODS:
                try:
                    result = METHODS[internal_method](tool_args)
                    send_response(req_id, result)
                except Exception as e:
                    send_response(req_id, result={"isError": True, "content": [
                        {"type": "text", "text": f"Runtime Error: {str(e)}"}
                    ]})
            else:
                send_response(req_id, error={"code": -32601,
                              "message": f"Internal method {internal_method} not implemented"})

        elif method == "prompts/list":
            send_response(req_id, {
                "prompts": [
                    {
                        "name": "knowledge-instructions",
                        "description": "Static instructions for AI agents (Forced Efficiency, Navigation, Security)."
                    },
                    {
                        "name": "knowledge-items",
                        "description": "Dynamic table of all available Knowledge Items (KI)."
                    }
                ]
            })

        elif method == "prompts/get":
            prompt_name = params.get("name")
            if prompt_name == "knowledge-instructions":
                content = ki_utils.get_instructions()
                send_response(req_id, {
                    "description": "AI Agent Core Instructions",
                    "messages": [{"role": "user", "content": {"type": "text", "text": content}}]
                })
            elif prompt_name == "knowledge-items":
                content = "Before starting work — **be sure to read** the relevant KIs in `.know/knowledge/`:\n\n"
                content += ki_utils.get_ki_list_table()
                send_response(req_id, {
                    "description": "Available Knowledge Items",
                    "messages": [{"role": "user", "content": {"type": "text", "text": content}}]
                })
            else:
                send_response(req_id, error={"code": -32601, "message": f"Prompt {prompt_name} not found"})

        elif method == "resources/list":
            jail = get_jail_dir()
            resources = []
            if jail:
                # Add core files
                for f in ["doc_config.json", "DIR_INDEX.md"]:
                    if os.path.exists(os.path.join(jail, f)):
                        resources.append({
                            "uri": f"ki://{f}",
                            "name": f,
                            "mimeType": "application/json" if f.endswith(".json") else "text/markdown"
                        })
                
                # Add workflows dynamically
                wf_dir = os.path.join(jail, "workflows")
                if os.path.exists(wf_dir):
                    for f in os.listdir(wf_dir):
                        if f.endswith(".md"):
                            resources.append({
                                "uri": f"ki://workflows/{f}",
                                "name": f"Workflow: {f[:-3]}",
                                "mimeType": "text/markdown"
                            })
            send_response(req_id, {"resources": resources})

        elif method == "resources/read":
            uri = params.get("uri", "")
            jail = get_jail_dir()
            if uri.startswith("ki://") and jail:
                rel_path = uri.replace("ki://", "")
                # Security: prevent path traversal if any
                rel_path = os.path.normpath(rel_path).replace("..", "")
                path = os.path.join(jail, rel_path)
                
                if os.path.exists(path) and os.path.isfile(path):
                    with open(path, "r", encoding="utf-8") as f:
                        send_response(req_id, {"contents": [{
                            "uri": uri,
                            "mimeType": "text/markdown" if path.endswith(".md") else "text/plain",
                            "text": f.read()
                        }]})
                    continue
            send_response(req_id, error={"code": -32602, "message": f"Resource {uri} not found"})

        elif method == "roots/list":
            jail = get_jail_dir()
            roots = []
            if jail:
                # Add the knowledge folder as a root
                roots.append({
                    "uri": f"file:///{jail.replace('\\', '/')}",
                    "name": "Knowledge Base"
                })
            send_response(req_id, {"roots": roots})

        elif method == "notifications/initialized":
            pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
