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
def get_tools_cfg(): return ki_utils.get_ki_cfg().get("knowledge_system", {}).get("tools", [])


def validate_path(rel_path: str, is_write: bool = False, forbidden_files: List[str] = None) -> str:
    jail = get_jail_dir()
    if not jail:
        raise PermissionError("Knowledge root not initialized.")
    normalized = os.path.normpath(rel_path)
    if normalized.startswith("..") or os.path.isabs(normalized):
        raise PermissionError(f"Access Denied: Path '{rel_path}' is outside sandbox.")

    target = os.path.abspath(os.path.join(jail, normalized))
    if not target.startswith(jail):
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
    }
]

def get_ms_cfg(): return ki_utils.get_ki_cfg().get("knowledge_system", {}).get("mcp_server", {})
def get_tools_cfg(): return DEFAULT_TOOLS


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
    os.makedirs(os.path.dirname(path), exist_ok=True)
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
    "find_unmapped_files": tool_find_unmapped_files,
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
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name":    get_ms_cfg().get("name",    "KnowledgeManager"),
                    "version": get_ms_cfg().get("version", "1.0.0"),
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

        elif method == "notifications/initialized":
            pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
