"""
test_ki_utils.py — tests for ki_utils config loading and path resolution.
"""

import os
import sys
import json
import pytest
from pathlib import Path


@pytest.mark.positive
def test_resolve_knowledge_root_from_scripts(tmp_project, monkeypatch):
    """resolve_knowledge_root finds knowledge root when ki_utils is in scripts/."""
    import ki_utils
    monkeypatch.setattr(ki_utils, "_CACHE", {})
    monkeypatch.chdir(tmp_project)

    from conftest import get_know_info
    _, _, config_path = get_know_info(tmp_project)
    monkeypatch.setattr(sys, "argv", ["prog", "--config", str(config_path)])

    root = ki_utils.get_knowledge_root()
    assert root != "", "KNOWLEDGE_ROOT should be resolved"
    assert os.path.exists(ki_utils.get_doc_config_path()), "doc_config.json must exist"


@pytest.mark.positive
def test_get_doc_config_returns_dict(tmp_project, monkeypatch):
    """get_doc_config() returns a non-empty dict when config exists."""
    import ki_utils
    monkeypatch.setattr(ki_utils, "_CACHE", {})
    monkeypatch.chdir(tmp_project)

    from conftest import get_know_info
    _, _, config_path = get_know_info(tmp_project)
    monkeypatch.setattr(sys, "argv", ["prog", "--config", str(config_path)])

    cfg = ki_utils.get_doc_config()
    assert "coverage_settings" in cfg
    assert "knowledge_items" in cfg


@pytest.mark.negative
def test_get_doc_config_missing_file(tmp_path, monkeypatch):
    """get_doc_config() returns empty dict when no config exists."""
    import ki_utils
    monkeypatch.setattr(ki_utils, "_CACHE", {})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["prog", "--config", "missing.json"])

    # Patch os.path.exists to prevent finding the real project root during fallbacks
    real_exists = os.path.exists
    def mock_exists(path):
        if "doc_config.json" in str(path) or "ki_config.json" in str(path):
            if "missing.json" in str(path): return False
            return False if str(tmp_path) not in str(os.path.abspath(path)) else real_exists(path)
        return real_exists(path)
    monkeypatch.setattr(os.path, "exists", mock_exists)

    cfg = ki_utils.get_doc_config()
    assert cfg == {}


@pytest.mark.positive
def test_exclude_patterns_loading(tmp_project, monkeypatch):
    """get_exclude_patterns loads patterns from config.json and defaults."""
    import ki_utils
    monkeypatch.setattr(ki_utils, "_CACHE", {})
    monkeypatch.chdir(tmp_project)

    from conftest import get_know_info
    _, know_path, config_path = get_know_info(tmp_project)
    monkeypatch.setattr(sys, "argv", ["prog", "--config", str(config_path)])

    # Write config.json with custom patterns
    local_cfg_path = know_path / "config.json"
    local_cfg = {
        "exclude_patterns": ["brain", "logs", "scratch", "tmp", "MagicMock", "*.log"]
    }
    local_cfg_path.write_text(json.dumps(local_cfg), encoding="utf-8")

    patterns = ki_utils.get_exclude_patterns()
    assert ".git" in patterns
    assert "brain" in patterns
    assert "MagicMock" in patterns
    assert "*.log" in patterns


@pytest.mark.positive
def test_should_exclude():
    """should_exclude checks exact names, components, and glob patterns."""
    import ki_utils
    patterns = {".git", "brain", "scratch", "tmp", "*.bak", "logs/*"}

    assert ki_utils.should_exclude(".git", "", patterns) is True
    assert ki_utils.should_exclude("brain", "brain", patterns) is True
    assert ki_utils.should_exclude("test.bak", "foo/test.bak", patterns) is True
    assert ki_utils.should_exclude("file.txt", "logs/file.txt", patterns) is True
    assert ki_utils.should_exclude("main.py", "src/main.py", patterns) is False


@pytest.mark.positive
def test_is_subpath(tmp_path):
    """is_subpath correctly determines directory containment and guards against prefix traversal."""
    import ki_utils
    root = tmp_path / "project"
    root.mkdir()
    child = root / "sub" / "file.txt"
    sibling_evil = tmp_path / "project_evil" / "file.txt"

    assert ki_utils.is_subpath(str(child), str(root)) is True
    assert ki_utils.is_subpath(str(root), str(root)) is True
    assert ki_utils.is_subpath(str(tmp_path), str(root)) is False
    assert ki_utils.is_subpath(str(sibling_evil), str(root)) is False


@pytest.mark.positive
def test_is_ki_filename():
    """is_ki_filename correctly recognizes valid KI files and handles _OVERVIEW."""
    import ki_utils
    assert ki_utils.is_ki_filename("auth.ki.md") is True
    assert ki_utils.is_ki_filename("user_service.ki.md") is True
    assert ki_utils.is_ki_filename("_OVERVIEW.ki.md", include_overview=False) is False
    assert ki_utils.is_ki_filename("_OVERVIEW.ki.md", include_overview=True) is True
    assert ki_utils.is_ki_filename("notes.md") is False
    assert ki_utils.is_ki_filename("ki.md") is False
    assert ki_utils.is_ki_filename("something.txt") is False


@pytest.mark.positive
def test_normalize_status_and_superseding_chain():
    """normalize_status handles aliases/case and resolve_superseding_chain detects chains and cycles."""
    import ki_utils

    assert ki_utils.normalize_status(None, "adr") == "accepted"
    assert ki_utils.normalize_status("Accepted", "adr") == "accepted"
    assert ki_utils.normalize_status("Proposed", "adr") == "draft"
    assert ki_utils.normalize_status("Superseded by ADR 129", "adr") == "superseded"
    assert ki_utils.normalize_status("POC", "adr") == "poc"
    assert ki_utils.normalize_status("Archived", "adr") == "archived"

    assert ki_utils.normalize_status("", "ki") == "active"
    assert ki_utils.normalize_status("STALE", "ki") == "stale"
    assert ki_utils.normalize_status("archived", "ki") == "archived"
    assert ki_utils.normalize_status("poc", "ki") == "poc"

    records = [
        {"id": "120", "superseded_by": "128"},
        {"id": "128", "superseded_by": "129"},
        {"id": "129", "superseded_by": None},
        {"id": "200", "superseded_by": "201"},
        {"id": "201", "superseded_by": "200"},
    ]
    assert ki_utils.resolve_superseding_chain("120", records) == ["128", "129"]
    assert ki_utils.resolve_superseding_chain("200", records) == ["201"]


@pytest.mark.positive
def test_agents_diet_and_ki_list_status_filtering(tmp_path, monkeypatch):
    """get_adr_table and get_ki_list_table omit inactive items and sync_agents_md does not duplicate notes."""
    import ki_utils
    import sync_agents_md

    proj = tmp_path / "proj"
    ki_base = proj / ".ki-base"
    know = ki_base / "knowledge"
    dec = ki_base / "decisions"
    know.mkdir(parents=True)
    dec.mkdir(parents=True)

    (ki_base / "ki_config.json").write_text(
        json.dumps({"project_name": "proj", "sync_agents_md": True, "paths": {"knowledge_root": ".ki-base", "project_root": ".."}}),
        encoding="utf-8",
    )
    (know / "core.ki.md").write_text("# Core\n\nActive KI.\n", encoding="utf-8")
    (know / "exp_poc.ki.md").write_text("<!-- status: poc -->\n# PoC\n\nPrototype KI.\n", encoding="utf-8")
    (know / "old.ki.md").write_text("<!-- status: archived -->\n# Old\n\nArchived KI.\n", encoding="utf-8")

    (ki_base / "doc_config.json").write_text(
        json.dumps({
            "knowledge_items": {
                "core.ki.md": {"summary": "Core logic", "status": "active"},
                "exp_poc.ki.md": {"summary": "PoC idea", "status": "poc"},
                "old.ki.md": {"summary": "Legacy module", "status": "archived"},
            }
        }),
        encoding="utf-8",
    )

    (dec / "001_active.md").write_text("<!-- status: accepted -->\n# ADR 001: Active\n\n## Context\nActive rule.\n", encoding="utf-8")
    (dec / "002_poc.md").write_text("<!-- status: poc -->\n# ADR 002: PoC Trial\n\n## Context\nTrying option.\n", encoding="utf-8")
    for i in range(3, 15):
        (dec / f"{i:03d}_old.md").write_text(
            f"<!-- status: superseded -->\n<!-- superseded_by: 001 -->\n# ADR {i:03d}: Old {i}\n\n## Context\nOld.\n",
            encoding="utf-8",
        )

    (proj / "AGENTS.md").write_text("# AGENTS\n\n## Knowledge Items\n\n| File | Topic / Summary |\n|------|-----------------|\n\n## Key Files\n", encoding="utf-8")

    monkeypatch.setattr(ki_utils, "_CACHE", {})
    monkeypatch.setattr(ki_utils, "ACTIVE_WORKSPACE_PATH", str(proj))

    adr_table = ki_utils.get_adr_table()
    assert "| 001 | Active | accepted |" in adr_table
    assert "| 002 | PoC Trial | poc [POC] |" in adr_table
    assert "003_old.md" not in adr_table
    assert "12 inactive ADR(s) omitted (superseded: 12)" in adr_table

    ki_table = ki_utils.get_ki_list_table()
    assert "core.ki.md" in ki_table
    assert "[POC] PoC idea" in ki_table
    assert "old.ki.md" not in ki_table
    assert "1 archived/inactive item(s) omitted" in ki_table

    # Ensure repeated sync_agents_md does not duplicate omitted note
    sync_agents_md.sync_agents_md()
    sync_agents_md.sync_agents_md()
    agents_text = (proj / "AGENTS.md").read_text(encoding="utf-8")
    assert agents_text.count("archived/inactive item(s) omitted") == 1

    # Check ki_list status filter
    active_data = ki_utils.get_ki_list_data(status="active")
    assert active_data["total_ki"] == 2
    assert active_data["total_adr"] == 2

    all_data = ki_utils.get_ki_list_data(status="all")
    assert all_data["total_ki"] == 3
    assert all_data["total_adr"] == 14

    sup_data = ki_utils.get_ki_list_data(scope="adr", status="superseded")
    assert sup_data["total_adr"] == 12
    assert sup_data["adrs"][0]["superseded_by"] == "001"


