"""
test_edge_cases.py — More negative/edge case tests for the knowledge system.
"""

import os
import sys
import json
import pytest
from pathlib import Path
from knowledge_engine import KnowledgeEngine

@pytest.mark.negative
def test_knowledge_engine_malformed_json(tmp_project):
    """KnowledgeEngine handles malformed doc_state.json gracefully."""
    from conftest import get_know_info
    know_name, know_path, _ = get_know_info(tmp_project)
    
    state_file = know_path / "doc_state.json"
    state_file.write_text("{ \"incomplete\": ", encoding="utf-8")
    
    ke = KnowledgeEngine(str(tmp_project), know_name)
    # Should catch JSONDecodeError and return empty or partial state
    # check_for_changes will see everything as "new" if state can't be loaded
    modified, new, deleted = ke.check_for_changes()
    assert len(new) > 0


@pytest.mark.negative
def test_knowledge_engine_permission_error(tmp_project, monkeypatch):
    """KnowledgeEngine handles file access errors gracefully."""
    from conftest import get_know_info
    know_name, _, _ = get_know_info(tmp_project)
    ke = KnowledgeEngine(str(tmp_project), know_name)
    
    def mock_os_error(path):
        raise OSError("Permission denied")

    import os
    monkeypatch.setattr(os.path, "getmtime", mock_os_error)
    
    # scan_tracked_files uses getmtime and catches OSError
    # capture_full_state uses scan_tracked_files
    state = ke.capture_full_state()
    assert state == {}


@pytest.mark.negative
def test_ki_utils_no_root_found(tmp_path, monkeypatch):
    """ki_utils handles environments where no knowledge root can be found."""
    import ki_utils
    monkeypatch.setattr(ki_utils, "_CACHE", {})
    # Chdir to empty temp path, no .know, no scripts folder nearby
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["prog"])
    
    # Patch os.path.exists to prevent finding the real project root
    real_exists = os.path.exists
    def mock_exists(path):
        if "doc_config.json" in str(path):
            return False
        return real_exists(path)
    monkeypatch.setattr(os.path, "exists", mock_exists)
    
    assert ki_utils.get_knowledge_root() == ""
    assert ki_utils.get_doc_config() == {}


@pytest.mark.negative
def test_knowledge_mcp_unauthorized_jail(monkeypatch):
    """knowledge_mcp rejects paths if JAIL_DIR is not set."""
    import knowledge_mcp
    import ki_utils
    monkeypatch.setattr(ki_utils, "_CACHE", {"knowledge_root": ""})
    
    with pytest.raises(PermissionError, match="Knowledge root not initialized"):
        knowledge_mcp.validate_path("some/file.md")

