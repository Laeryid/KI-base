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

JAIL_DIR = ki_utils.KNOWLEDGE_ROOT
PYTHON_EXE = ki_utils.PYTHON_EXE
DOC_CONFIG = ki_utils.get_doc_config()
MS_CFG = DOC_CONFIG.get("knowledge_system", {}).get("mcp_server", {})
TOOLS_CFG = DOC_CONFIG.get("knowledge_system", {}).get("tools", [])


def validate_path(rel_path: str, is_write: bool = False) -> str:
    if not JAIL_DIR:
        raise PermissionError("Knowledge root not initialized.")
    normalized = os.path.normpath(rel_path)
    if normalized.startswith("..") or os.path.isabs(normalized):
        raise PermissionError(f"Access Denied: Path '{rel_path}' is outside sandbox.")

    target = os.path.abspath(os.path.join(JAIL_DIR, normalized))
    if not target.startswith(JAIL_DIR):
        raise PermissionError(f"Access Denied: Jail breach detected for '{rel_path}'.")

    if is_write:
        ext = os.path.splitext(target)[1].lower()
        if ext in {".py", ".pyc", ".bat", ".ps1", ".sh", ".exe", ".cmd", ".dll"}:
            raise PermissionError(
                f"Access Denied: Modifying executable or script files ({ext}) is forbidden."
            )

    return target


# --- Tool Implementations ---

def run_script(script_name: str):
    if not JAIL_DIR:
        return {"isError": True, "content": [{"type": "text",
                "text": "Error: Knowledge system not active here."}]}

    scripts_dir = os.path.join(JAIL_DIR, "scripts")
    script_path = os.path.join(scripts_dir, script_name)

    if not os.path.exists(script_path):
        script_path = os.path.join(JAIL_DIR, script_name)

    if not os.path.exists(script_path):
        return {"isError": True, "content": [{"type": "text",
                "text": f"Error: Script {script_name} not found."}]}

    result = subprocess.run(
        [PYTHON_EXE, script_path],
        capture_output=True, text=True, encoding="utf-8",
        cwd=ki_utils.PROJECT_ROOT  # run from project root
    )
    return {"content": [{"type": "text",
            "text": result.stdout + (result.stderr if result.stderr else "")}]}


def tool_audit_coverage(args):   return run_script("audit_coverage.py")
def tool_sync_agents_md(args):   return run_script("sync_agents_md.py")
def tool_generate_dir_index(args): return run_script("generate_dir_index.py")


def tool_check_changes(args):
    if not JAIL_DIR:
        return {"isError": True, "content": [{"type": "text", "text": "Error: Knowledge system not active."}]}
    sys.path.insert(0, os.path.join(JAIL_DIR, "scripts"))
    from knowledge_engine import KnowledgeEngine
    project_root = ki_utils.PROJECT_ROOT
    knowledge_root_name = os.path.basename(JAIL_DIR)
    ke = KnowledgeEngine(project_root, knowledge_root_name)
    modified, new, deleted = ke.check_for_changes()
    res = f"Modified: {modified}\nNew: {new}\nDeleted: {deleted}"
    return {"content": [{"type": "text", "text": res}]}


def tool_save_state(args):
    if not JAIL_DIR:
        return {"isError": True, "content": [{"type": "text", "text": "Error: Knowledge system not active."}]}
    sys.path.insert(0, os.path.join(JAIL_DIR, "scripts"))
    from knowledge_engine import KnowledgeEngine
    project_root = ki_utils.PROJECT_ROOT
    knowledge_root_name = os.path.basename(JAIL_DIR)
    ke = KnowledgeEngine(project_root, knowledge_root_name)
    state = ke.capture_full_state()
    ke.save_state(state)
    return {"content": [{"type": "text", "text": f"State saved: {len(state)} files tracked."}]}


def tool_write_file(args):
    path = validate_path(args.get("rel_path"), is_write=True)
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
    "save_state":        tool_save_state,
    "write_file":        tool_write_file,
    "edit_file":         tool_edit_file,
    "make_dir":          tool_make_dir,
    "read_file":         tool_read_file,
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
            send_response(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name":    MS_CFG.get("name",    "KnowledgeManager"),
                    "version": MS_CFG.get("version", "1.0.0")
                }
            })

        elif method == "tools/list":
            if not JAIL_DIR:
                send_response(req_id, {"tools": []})
                continue

            tools = []
            for t in TOOLS_CFG:
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

            target_tool = next((t for t in TOOLS_CFG if t["name"] == tool_name), None)
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
