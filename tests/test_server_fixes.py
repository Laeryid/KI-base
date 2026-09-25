import pytest
import os
import sys
import tempfile
import json
from ki_manager.server import handle_tool_call, MCP_TOOLS

def test_edit_know_file_crlf(monkeypatch, tmp_path):
    # Simulate ki_utils.ACTIVE_WORKSPACE_PATH and get_knowledge_root
    monkeypatch.setattr('ki_manager.scripts.ki_utils.ACTIVE_WORKSPACE_PATH', str(tmp_path))
    monkeypatch.setattr('ki_manager.server.get_jail_dir', lambda: str(tmp_path / '.ki-base'))
    
    jail = tmp_path / '.ki-base'
    jail.mkdir()
    
    test_file = jail / "test.md"
    # Write CRLF
    with open(test_file, 'wb') as f:
        f.write(b"line1\r\nline2\r\nline3\r\n")
    
    # Model sends \n
    args = {
        "rel_path": "test.md",
        "old_text": "line2\n",
        "new_text": "line2_changed\n"
    }
    
    result = handle_tool_call("edit_know_file", args)
    assert result == "File edited."
    
    with open(test_file, 'rb') as f:
        content = f.read()
    assert b"line2_changed" in content


def test_tool_schemas_valid():
    for tool in MCP_TOOLS:
        schema = tool.get("inputSchema", {})
        assert schema.get("type") == "object"
        # Must have properties dict
        assert "properties" in schema, f"Tool {tool['name']} is missing properties in schema"
        
        # Check rel_path description
        if "rel_path" in schema["properties"]:
            assert "description" in schema["properties"]["rel_path"], f"Tool {tool['name']} rel_path is missing description"

