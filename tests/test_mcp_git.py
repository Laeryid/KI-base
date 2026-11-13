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
def test_git_checkpoint_disabled_by_default(tmp_project, setup_git_mcp):
    mcp = setup_git_mcp

    doc_config = Path(tmp_project) / ".know" / "doc_config.json"
    with open(doc_config, "w") as f:
        f.write('{"test": true}')

    res = mcp.tool_git_checkpoint({"message": "Should not commit"})
    text = res["content"][0]["text"]
    assert "auto-commit is disabled" in text
    assert "doc_config.json" in text

    # Ensure no commit was created
    rev = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=tmp_project, capture_output=True, text=True,
    )
    assert rev.returncode != 0


@pytest.mark.positive
def test_git_checkpoint_success(tmp_project, setup_git_mcp):
    mcp = setup_git_mcp
    
    # Modify a tracked file and doc_state.json
    doc_config = Path(tmp_project) / ".know" / "doc_config.json"
    with open(doc_config, "w") as f:
        f.write('{"test": true}')
    doc_state = Path(tmp_project) / ".know" / "doc_state.json"
    with open(doc_state, "w") as f:
        f.write('{"src/module_a/code.py": {"hash": "abc"}}')
    
    # Explicit commit=True
    res = mcp.tool_git_checkpoint({"message": "Test checkpoint", "commit": True})
    assert "Checkpoint created" in res["content"][0]["text"]
    assert "[AI] Test checkpoint" in res["content"][0]["text"]
    
    # Verify via git log and committed files
    log = subprocess.run(
        ["git", "log", "-1", "--format=%B%an<%ae>"], 
        cwd=tmp_project, capture_output=True, text=True
    ).stdout
    
    assert "[AI] Test checkpoint" in log
    assert "ki-manager<ki-manager@bot>" in log

    show_files = subprocess.run(
        ["git", "show", "--name-only", "--format=", "HEAD"],
        cwd=tmp_project, capture_output=True, text=True
    ).stdout
    assert "doc_state.json" in show_files
    assert "doc_config.json" in show_files


@pytest.mark.positive
def test_git_checkpoint_auto_enabled_in_config(tmp_project, setup_git_mcp):
    import json
    mcp = setup_git_mcp

    ki_cfg_path = Path(tmp_project) / ".know" / "ki_config.json"
    cfg = json.loads(ki_cfg_path.read_text(encoding="utf-8"))
    cfg["auto_git_checkpoint"] = True
    ki_cfg_path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")

    res = mcp.tool_git_checkpoint({"message": "Config auto commit"})
    assert "Checkpoint created" in res["content"][0]["text"]


@pytest.mark.positive
def test_git_checkpoint_no_changes(setup_git_mcp):
    mcp = setup_git_mcp
    # First commit anything to have a clean state
    mcp.tool_git_checkpoint({"message": "Initial", "commit": True})
    
    # Call again with no changes
    res = mcp.tool_git_checkpoint({"message": "No changes test", "commit": True})
    assert "No changes to checkpoint" in res["content"][0]["text"]


@pytest.mark.positive
def test_git_restore_file(tmp_project, setup_git_mcp):
    mcp = setup_git_mcp
    doc_config = Path(tmp_project) / ".know" / "doc_config.json"
    
    # 1. Initial state and checkpoint
    with open(doc_config, "w") as f:
        f.write("original content")
    mcp.tool_git_checkpoint({"message": "Original state", "commit": True})
    
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
    assert "escapes sandbox" in res["content"][0]["text"]
