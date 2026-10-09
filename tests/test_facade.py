import json
import subprocess
import sys
import pytest
from pathlib import Path
from ki_manager import server
from ki_manager.tools import facade


def test_tools_counts_and_compact_definition():
    assert len(server.COMPACT_TOOLS) == 6
    compact_names = [t["name"] for t in server.COMPACT_TOOLS]
    assert compact_names == [
        "ki_instructions",
        "ki_search",
        "ki_read",
        "ki_tools",
        "ki_call",
        "ki_mutate",
    ]
    # MCP_TOOLS should have 34 tools (31 original + ki_search + ki_read + check_ki_drift)
    assert len(server.MCP_TOOLS) == 34
    assert "check_ki_drift" in [t["name"] for t in server.MCP_TOOLS]


def test_ki_tools_catalog():
    # Listing all
    catalog = server.handle_tool_call("ki_tools", {})
    assert "ki-manager Tools Catalog" in catalog
    assert "audit_coverage" in catalog
    assert "ki_call" in catalog

    # Filter by group
    grp_catalog = server.handle_tool_call("ki_tools", {"group": "coverage_analysis"})
    assert "audit_coverage" in grp_catalog
    assert "ki_init_project" not in grp_catalog

    # Inspect schema
    schema_str = server.handle_tool_call("ki_tools", {"name": "audit_coverage"})
    schema = json.loads(schema_str)
    assert schema["name"] == "audit_coverage"
    assert "inputSchema" in schema

    # Unknown tool
    unknown = server.handle_tool_call("ki_tools", {"name": "non_existent_tool"})
    assert "not found" in unknown.lower()


def test_ki_call_enforcement():
    # Calling a read-only tool via ki_call should succeed (or return expected tool response)
    res = server.handle_tool_call("ki_call", {"tool": "ki_instructions", "args": {"document": "overview"}})
    assert "Global AI Instructions" in res

    # Calling a mutating tool via ki_call MUST be rejected
    res_mutate = server.handle_tool_call("ki_call", {"tool": "write_know_file", "args": {"rel_path": "a.md", "content": "x"}})
    assert "state-modifying and cannot be called via ki_call" in res_mutate
    assert "ki_mutate" in res_mutate

    # Calling nested ki_call should be rejected
    res_nested = server.handle_tool_call("ki_call", {"tool": "ki_call", "args": {}})
    assert "Cannot nest" in res_nested

    # Missing required argument validation
    res_invalid = server.handle_tool_call("ki_call", {"tool": "ki_instructions", "args": {}})
    assert "Missing required parameter" in res_invalid or "Required Schema:" in res_invalid


def test_ki_mutate_enforcement():
    # Calling a read-only tool via ki_mutate MUST be rejected
    res_ro = server.handle_tool_call("ki_mutate", {"tool": "audit_coverage", "args": {}})
    assert "read-only" in res_ro
    assert "ki_call" in res_ro

    # Calling nested dispatcher
    res_nested = server.handle_tool_call("ki_mutate", {"tool": "ki_mutate", "args": {}})
    assert "Cannot nest" in res_nested


def test_ki_read_features(tmp_path, monkeypatch):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    ki_dir = project_dir / ".ki-base" / "knowledge"
    ki_dir.mkdir(parents=True)

    test_file = ki_dir / "test_item.ki.md"
    test_file.write_text(
        "# Main Title\n\n"
        "Intro text.\n\n"
        "## Architecture Section\n"
        "Here is the detailed architecture information.\n"
        "It spans multiple lines.\n\n"
        "## Next Section\n"
        "Different content.\n",
        encoding="utf-8"
    )

    monkeypatch.setattr(server, "get_jail_dir", lambda: str(ki_dir))
    monkeypatch.setattr(server, "get_project_root", lambda: str(project_dir))

    # 1. Full read
    content = server.handle_tool_call("ki_read", {"rel_path": "test_item.ki.md"})
    assert "Main Title" in content
    assert "Different content." in content

    # 1b. Test with jail set to .ki-base root and reading via various prefix forms
    monkeypatch.setattr(server, "get_jail_dir", lambda: str(project_dir / ".ki-base"))
    # (a) Basename lookup
    content_base = server.handle_tool_call("ki_read", {"rel_path": "test_item.ki.md"})
    assert "Main Title" in content_base
    # (b) Path relative to jail
    content_jail = server.handle_tool_call("ki_read", {"rel_path": "knowledge/test_item.ki.md"})
    assert "Main Title" in content_jail
    # (c) Path relative to project root with root folder prefix
    content_proj = server.handle_tool_call("ki_read", {"rel_path": ".ki-base/knowledge/test_item.ki.md"})
    assert "Main Title" in content_proj

    # 2. Section read
    sec_content = server.handle_tool_call("ki_read", {"rel_path": "test_item.ki.md", "section": "Architecture"})
    assert "Architecture Section" in sec_content
    assert "detailed architecture information" in sec_content
    assert "Different content." not in sec_content

    # 3. max_chars truncation and offset
    trunc_content = server.handle_tool_call("ki_read", {"rel_path": "test_item.ki.md", "max_chars": 30})
    assert len(trunc_content) < 120
    assert "truncated to 30" in trunc_content

    offset_content = server.handle_tool_call("ki_read", {"rel_path": "test_item.ki.md", "offset": 10, "max_chars": 30})
    assert offset_content.startswith(content[10:40])

    # 4. File not found
    not_found = server.handle_tool_call("ki_read", {"rel_path": "missing.ki.md"})
    assert "File not found" in not_found

    # 5. ki_search through server.handle_tool_call (markdown and json formats)
    search_md = server.handle_tool_call("ki_search", {"query": "Architecture"})
    assert "Found 1 result(s)" in search_md
    assert "test_item.ki.md" in search_md

    search_json = server.handle_tool_call("ki_search", {"query": "Architecture", "format": "json"})
    assert '"results": [' in search_json



def test_compact_mode_via_cli():
    # Test server in compact mode returns only 6 tools
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    cmd = [
        sys.executable,
        "-m",
        "ki_manager.server",
        "--tool-mode",
        "compact",
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, _ = proc.communicate(input=req + "\n", timeout=10)
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    resp = json.loads(lines[0])
    tools = resp["result"]["tools"]
    assert len(tools) == 6
    names = [t["name"] for t in tools]
    assert "ki_call" in names
    assert "ki_mutate" in names
    assert "ki_tools" in names
    assert "ki_instructions" in names


def test_full_mode_via_cli():
    # Test server in full mode returns all 34 tools
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    cmd = [
        sys.executable,
        "-m",
        "ki_manager.server",
        "--tool-mode",
        "full",
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, _ = proc.communicate(input=req + "\n", timeout=10)
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    resp = json.loads(lines[0])
    tools = resp["result"]["tools"]
    assert len(tools) == 34
