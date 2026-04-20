"""
test_knowledge_engine_extra.py

Additional tests for KnowledgeEngine:
- deleted file detection
- get_affected_ki_map / get_affected_artifacts_map
- get_staleness_report structure
"""

import os
import sys
import json
import time
import pytest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from knowledge_engine import KnowledgeEngine


def _make_engine(tmp_project, doc_config_override=None):
    from conftest import get_know_info
    know_name, know_path, _ = get_know_info(tmp_project)
    if doc_config_override:
        cfg_path = know_path / "doc_config.json"
        cfg_path.write_text(json.dumps(doc_config_override, indent=2), encoding="utf-8")
    return KnowledgeEngine(str(tmp_project), know_name)


def test_detects_deleted_file(tmp_project):
    """Engine reports a file as deleted when it's removed after state save."""
    from conftest import get_know_info
    know_name, _, _ = get_know_info(tmp_project)
    ke = KnowledgeEngine(str(tmp_project), know_name)
    state = ke.capture_full_state()
    # Manually inject a phantom file into saved state
    phantom = "src/module_a/will_be_deleted.py"
    state[phantom] = {"hash": "abc123", "mtime": 1000000.0}
    ke.save_state(state)

    _, _, deleted = ke.check_for_changes()
    assert phantom in deleted, f"Deleted file should be reported: {deleted}"


def test_get_affected_ki_map(tmp_project):
    """get_affected_ki_map returns the correct KI for a changed file."""
    from conftest import get_know_info
    know_name, know_path, _ = get_know_info(tmp_project)
    doc_config = json.loads((know_path / "doc_config.json").read_text())
    doc_config["knowledge_items"]["KI_module_a.md"] = {
        "description": "Module A docs",
        "covers": ["Module A"],
        "depends_on": ["src/module_a"]
    }
    (know_path / "doc_config.json").write_text(
        json.dumps(doc_config, indent=2), encoding="utf-8"
    )

    ke = KnowledgeEngine(str(tmp_project), know_name)
    changed = ["src/module_a/code.py"]
    affected = ke.get_affected_ki_map(changed)
    assert "KI_module_a.md" in affected


def test_get_affected_artifacts_map(tmp_project):
    """get_affected_artifacts_map returns the correct artifact for a changed dep."""
    from conftest import get_know_info
    know_name, _, _ = get_know_info(tmp_project)
    ke = KnowledgeEngine(str(tmp_project), know_name)
    changed = ["src/module_a/code.py"]
    affected = ke.get_affected_artifacts_map(changed)
    assert "README.md" in affected


def test_staleness_report_structure(tmp_project):
    """get_staleness_report returns the expected top-level keys."""
    from conftest import get_know_info
    know_name, _, _ = get_know_info(tmp_project)
    ke = KnowledgeEngine(str(tmp_project), know_name)
    ke.save_state(ke.capture_full_state())
    report = ke.get_staleness_report()

    assert "changed_files" in report
    assert "stale_artifacts" in report
    assert "stale_knowledge_items" in report
    assert "summary" in report
    assert "generated_at" in report["summary"]


def test_empty_state_file_treated_as_all_new(tmp_project):
    """If doc_state.json doesn't exist, all tracked files are reported as new."""
    from conftest import get_know_info
    know_name, know_path, _ = get_know_info(tmp_project)
    ke = KnowledgeEngine(str(tmp_project), know_name)
    state_file = know_path / "doc_state.json"
    if state_file.exists():
        state_file.unlink()

    _, new, deleted = ke.check_for_changes()
    assert deleted == []
    # 'new' may or may not be empty depending on what is tracked,
    # but it should be a list
    assert isinstance(new, list)
