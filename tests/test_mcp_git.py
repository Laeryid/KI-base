"""
test_mcp_git.py — tests for the MCP Git tools (checkpoint and restore).
"""

import os
import sys
import pytest
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def setup_git_mcp(monkeypatch, tmp_project):
    """Setup environment for MCP Git tests."""
    import ki_utils
    import knowledge_mcp
    
    from conftest import get_know_info
    _, _, config_path = get_know_info(tmp_project)
    
    # Initialize Git in the temp project
    subprocess.run(["git", "init"], cwd=tmp_project, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_project, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_project, check=True)
    
    monkeypatch.setattr(ki_utils, "_CACHE", {})
    monkeypatch.setattr(sys, "argv", ["prog", "--config", str(config_path)])
    monkeypatch.chdir(tmp_project)
    return knowledge_mcp


@pytest.mark.positive
def test_git_checkpoint_success(tmp_project, setup_git_mcp):
    mcp = setup_git_mcp
    
    # Modify a tracked file
    doc_config = Path(tmp_project) / ".know" / "doc_config.json"
    with open(doc_config, "w") as f:
        f.write('{"test": true}')
    
    # Call checkpoint
    res = mcp.tool_git_checkpoint({"message": "Test checkpoint"})
    assert "Checkpoint created" in res["content"][0]["text"]
    assert "[AI] Test checkpoint" in res["content"][0]["text"]
    
    # Verify via git log
    log = subprocess.run(
        ["git", "log", "-1", "--format=%B%an<%ae>"], 
        cwd=tmp_project, capture_output=True, text=True
    ).stdout
    
    assert "[AI] Test checkpoint" in log
    assert "Antigravity AI<ai-assistant@ki.base>" in log


@pytest.mark.positive
def test_git_checkpoint_no_changes(setup_git_mcp):
    mcp = setup_git_mcp
    # First commit anything to have a clean state
    mcp.tool_git_checkpoint({"message": "Initial"})
    
    # Call again with no changes
    res = mcp.tool_git_checkpoint({"message": "No changes test"})
    assert "No changes to checkpoint" in res["content"][0]["text"]


@pytest.mark.positive
def test_git_restore_file(tmp_project, setup_git_mcp):
    mcp = setup_git_mcp
    doc_config = Path(tmp_project) / ".know" / "doc_config.json"
    
    # 1. Initial state and checkpoint
    with open(doc_config, "w") as f:
        f.write("original content")
    mcp.tool_git_checkpoint({"message": "Original state"})
    
    # 2. Modify
    with open(doc_config, "w") as f:
        f.write("corrupted content")
    
    # 3. Restore
    res = mcp.tool_git_restore({"target": "doc_config.json", "revision": "HEAD"})
    assert "Restored 'doc_config.json'" in res["content"][0]["text"]
    
    # 4. Verify content
    with open(doc_config, "r") as f:
        assert f.read() == "original content"


@pytest.mark.negative
def test_git_restore_outside_jail(setup_git_mcp):
    mcp = setup_git_mcp
    # Attempt to restore something outside .know
    res = mcp.tool_git_restore({"target": "../README.md", "revision": "HEAD"})
    assert res.get("isError") is True
    assert "outside sandbox" in res["content"][0]["text"]
