"""
test_knowledge_engine.py — tests for KnowledgeEngine (hashing, state, change detection).
"""

import os
import json
import pytest
from pathlib import Path
from knowledge_engine import KnowledgeEngine


@pytest.mark.positive
def test_capture_and_save_state(tmp_project):
    """Engine captures state and writes doc_state.json."""
    from conftest import get_know_info
    know_name, know_path, _ = get_know_info(tmp_project)

    ke = KnowledgeEngine(str(tmp_project), know_name)
    state = ke.capture_full_state()
    ke.save_state(state)

    state_file = know_path / "doc_state.json"
    assert state_file.exists(), "doc_state.json should be created"

    loaded = json.loads(state_file.read_text(encoding="utf-8"))
    # At least the src file should be tracked via artifacts depends_on
    assert isinstance(loaded, dict)


@pytest.mark.positive
def test_no_changes_after_save(tmp_project):
    """No changes reported immediately after saving state."""
    from conftest import get_know_info
    know_name, _, _ = get_know_info(tmp_project)
    ke = KnowledgeEngine(str(tmp_project), know_name)
    state = ke.capture_full_state()
    ke.save_state(state)

    modified, new, deleted = ke.check_for_changes()
    assert modified == [], f"Unexpected modifications: {modified}"
    assert deleted == [], f"Unexpected deletions: {deleted}"


@pytest.mark.positive
def test_detects_modified_file(tmp_project):
    """Engine detects a file modification after save."""
    from conftest import get_know_info
    know_name, _, _ = get_know_info(tmp_project)
    ke = KnowledgeEngine(str(tmp_project), know_name)
    state = ke.capture_full_state()
    ke.save_state(state)

    # Modify a tracked file
    code_file = tmp_project / "src" / "module_a" / "code.py"
    code_file.write_text("def hello(): return 42\n", encoding="utf-8")
    # Force mtime to be newer
    import time
    time.sleep(0.05)
    os.utime(str(code_file), None)

    modified, new, deleted = ke.check_for_changes()
    assert len(modified) > 0, "Modified file should be detected"


@pytest.mark.positive
def test_detects_new_file(tmp_project):
    """Engine detects a new file that wasn't in the saved state."""
    from conftest import get_know_info
    know_name, _, _ = get_know_info(tmp_project)
    ke = KnowledgeEngine(str(tmp_project), know_name)
    state = ke.capture_full_state()
    ke.save_state(state)

    new_file = tmp_project / "src" / "module_a" / "extra.py"
    new_file.write_text("x = 1\n", encoding="utf-8")

    _, new, _ = ke.check_for_changes()
    assert any("extra.py" in f for f in new), "New file should be detected"
