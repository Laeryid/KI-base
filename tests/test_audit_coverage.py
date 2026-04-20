"""
test_audit_coverage.py

Tests for audit_coverage.py:
- build_coverage_matrix with no KIs
- build_coverage_matrix after registering a KI
- format_markdown output structure
- untracked dirs detection
"""

import os
import sys
import json
import pytest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def setup_ki_utils(monkeypatch, tmp_project):
    """Setup ki_utils for testing without reloading modules."""
    from conftest import get_know_info
    _, _, config_path = get_know_info(tmp_project)
    
    import ki_utils
    # Clear cache and set config path
    monkeypatch.setattr(ki_utils, "_CACHE", {})
    monkeypatch.setattr(sys, "argv", ["prog", "--config", str(config_path)])
    monkeypatch.chdir(tmp_project)
    
    # Pre-import audit_coverage if not already present
    if "audit_coverage" not in sys.modules:
        import audit_coverage
    return sys.modules["audit_coverage"]


@pytest.mark.positive
def test_no_ki_gives_uncovered(tmp_project, setup_ki_utils):
    """Without any KI, the module should be marked as not covered."""
    ac = setup_ki_utils
    tracked = [["src/module_a", "Module A", 5]]
    data = ac.build_coverage_matrix(str(tmp_project), tracked)

    assert len(data["rows"]) == 1
    row = data["rows"][0]
    assert row["has_ki"] is False
    assert row["coverage_pct"] == 0.0


@pytest.mark.positive
def test_registered_ki_gives_coverage(tmp_project, setup_ki_utils):
    """After registering a KI with depends_on pointing to the module, coverage improves."""
    from conftest import get_know_info
    know_name, know_path, _ = get_know_info(tmp_project)
    cfg_path = know_path / "doc_config.json"
    cfg = json.loads(cfg_path.read_text())
    cfg["knowledge_items"]["KI_module_a.md"] = {
        "description": "Module A",
        "covers": ["Module A"],
        "depends_on": ["src/module_a/code.py"]
    }
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    # Create the KI file so get_ki_size can read it
    ki_file = know_path / "knowledge" / "KI_module_a.md"
    ki_file.write_text("# KI: Module A\n\nSome content here.\n", encoding="utf-8")

    ac = setup_ki_utils
    tracked = [["src/module_a", "Module A", 5]]
    data = ac.build_coverage_matrix(str(tmp_project), tracked)

    row = data["rows"][0]
    assert row["has_ki"] is True
    assert row["coverage_pct"] == 100.0
    assert row["status"] == "✅ Covered"


@pytest.mark.positive
def test_format_markdown_contains_table(tmp_project, setup_ki_utils):
    """format_markdown output contains module table header."""
    ac = setup_ki_utils
    tracked = [["src/module_a", "Module A", 5]]
    data = ac.build_coverage_matrix(str(tmp_project), tracked)
    md = ac.format_markdown(data, "2026-01-01")

    assert "## Module Coverage" in md
    assert "| Module |" in md
    assert "## Summary" in md


@pytest.mark.positive
def test_untracked_dirs_detected(tmp_project, setup_ki_utils):
    """Directories with code that are not tracked should appear in untracked."""
    # Create a new directory not in tracked_modules
    hidden_src = tmp_project / "untracked_module"
    hidden_src.mkdir()
    (hidden_src / "helper.py").write_text("x = 1\n", encoding="utf-8")

    ac = setup_ki_utils
    tracked = [["src/module_a", "Module A", 5]]
    data = ac.build_coverage_matrix(str(tmp_project), tracked)

    # 'untracked_module' should appear in untracked (it has code, not tracked)
    untracked_names = [os.path.basename(u) for u in data["untracked"]]
    assert "untracked_module" in untracked_names


@pytest.mark.positive
def test_priority_label():
    """priority_label returns correct emoji-prefixed strings."""
    import audit_coverage as ac
    assert "🔴" in ac.priority_label(10)
    assert "🟡" in ac.priority_label(6)
    assert "🟢" in ac.priority_label(2)
