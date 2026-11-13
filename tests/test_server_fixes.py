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


def test_update_last_verified_all_formats(monkeypatch, tmp_path):
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")

    project_dir = tmp_path / "my_project"
    project_dir.mkdir()
    know_dir = project_dir / ".ki-base" / "knowledge"
    know_dir.mkdir(parents=True)

    monkeypatch.setattr('ki_manager.scripts.ki_utils.ACTIVE_WORKSPACE_PATH', str(project_dir))
    monkeypatch.setattr('ki_manager.server.get_jail_dir', lambda: str(project_dir / ".ki-base"))
    monkeypatch.setattr('ki_manager.server.get_project_root', lambda: str(project_dir))

    # 1. HTML comment format
    f1 = know_dir / "item1.ki.md"
    f1.write_text("# Item 1\n<!-- last_verified: 2020-01-01 -->\nContent", encoding="utf-8")

    # 2. YAML frontmatter format
    f2 = know_dir / "item2.ki.md"
    f2.write_text("---\nlast_verified: 2020-01-01\n---\n# Item 2", encoding="utf-8")

    # 3. Markdown bold format
    f3 = know_dir / "item3.ki.md"
    f3.write_text("# Item 3\n**Last verified**: 2020-01-01\nContent", encoding="utf-8")

    # 4. No tag format (should insert)
    f4 = know_dir / "item4.ki.md"
    f4.write_text("# Item 4\n\n## Section\nContent", encoding="utf-8")

    res = handle_tool_call("update_last_verified", {"all_files": True})
    assert "in 4 files" in res

    assert f"<!-- last_verified: {today} -->" in f1.read_text(encoding="utf-8")
    assert today in f2.read_text(encoding="utf-8")
    assert f"**Last verified**: {today}" in f3.read_text(encoding="utf-8")
    assert f"<!-- last_verified: {today} -->" in f4.read_text(encoding="utf-8")

    # Running again when already today must not duplicate tags
    res_again = handle_tool_call("update_last_verified", {"all_files": True})
    assert "in 0 files" in res_again


def test_update_last_verified_targeted_only_affected(monkeypatch, tmp_path):
    import subprocess
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "src" / "a").mkdir(parents=True)
    (project_dir / "src" / "b").mkdir(parents=True)
    file_a = project_dir / "src" / "a" / "mod_a.py"
    file_b = project_dir / "src" / "b" / "mod_b.py"
    file_a.write_text("x = 1\n", encoding="utf-8")
    file_b.write_text("y = 2\n", encoding="utf-8")

    jail = project_dir / ".ki-base"
    know_dir = jail / "knowledge"
    know_dir.mkdir(parents=True)

    ki_a = know_dir / "a.ki.md"
    ki_b = know_dir / "b.ki.md"
    ki_a.write_text("# KI A\n<!-- last_verified: 2020-01-01 -->\n", encoding="utf-8")
    ki_b.write_text("# KI B\n<!-- last_verified: 2020-01-01 -->\n", encoding="utf-8")

    doc_cfg = {
        "knowledge_items": {
            "a.ki.md": {"depends_on": ["src/a/mod_a.py"]},
            "b.ki.md": {"depends_on": ["src/b/mod_b.py"]},
        }
    }
    (jail / "doc_config.json").write_text(json.dumps(doc_cfg), encoding="utf-8")
    (jail / "ki_config.json").write_text(json.dumps({"paths": {"knowledge_root": ".ki-base"}}), encoding="utf-8")

    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=project_dir, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=project_dir, check=True)
    subprocess.run(["git", "add", "."], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=project_dir, check=True, capture_output=True)

    monkeypatch.setattr('ki_manager.scripts.ki_utils.ACTIVE_WORKSPACE_PATH', str(project_dir))
    monkeypatch.setattr('ki_manager.scripts.ki_utils._CACHE', {})
    monkeypatch.setattr('ki_manager.server.get_jail_dir', lambda: str(jail))
    monkeypatch.setattr('ki_manager.server.get_project_root', lambda: str(project_dir))

    # No changes -> 0 files updated
    res_none = handle_tool_call("update_last_verified", {})
    assert "in 0 files" in res_none

    # Modify only src/a/mod_a.py -> only a.ki.md should be updated
    file_a.write_text("x = 2\n", encoding="utf-8")
    res_a = handle_tool_call("update_last_verified", {})
    assert "in 1 files: a.ki.md" in res_a
    assert today in ki_a.read_text(encoding="utf-8")
    assert "2020-01-01" in ki_b.read_text(encoding="utf-8")

    # Explicit ki_files -> updates b.ki.md
    res_explicit = handle_tool_call("update_last_verified", {"ki_files": ["b.ki.md"]})
    assert "in 1 files: b.ki.md" in res_explicit
    assert today in ki_b.read_text(encoding="utf-8")


def test_git_diff_secured_guards(monkeypatch, tmp_path):
    from ki_manager.scripts import git_diff_secured

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    monkeypatch.setattr('ki_manager.scripts.ki_utils.ACTIVE_WORKSPACE_PATH', str(project_dir))
    monkeypatch.setattr('ki_manager.scripts.ki_utils.get_project_root', lambda: str(project_dir))

    res_flag = git_diff_secured.git_diff_secured(["--output=evil.txt"])
    assert "Suspicious argument" in res_flag

    res_shell = git_diff_secured.git_diff_secured(["file.txt; rm -rf /"])
    assert "Suspicious argument" in res_shell

    res_escape = git_diff_secured.git_diff_secured(["../outside.txt"])
    assert "Access Denied" in res_escape

