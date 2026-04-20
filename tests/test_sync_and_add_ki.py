"""
test_sync_and_add_ki.py

Tests for:
  - sync_agents_md.py: table update, missing table header handling
  - add_ki_to_config.py: registers KI, handles missing knowledge_items section
"""

import os
import sys
import json
import pytest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _setup_modules(monkeypatch, tmp_project):
    """Reload ki_utils for a given tmp_project context."""
    for mod in ["ki_utils", "sync_agents_md", "add_ki_to_config"]:
        if mod in sys.modules:
            del sys.modules[mod]
    from conftest import get_know_info
    _, _, config_path = get_know_info(tmp_project)
    config_path = str(config_path)
    monkeypatch.setattr(sys, "argv", ["prog", "--config", config_path])
    monkeypatch.chdir(tmp_project)


def _make_agents_md(tmp_project, extra_ki_rows=""):
    agents = tmp_project / "AGENTS.md"
    agents.write_text(
        "# AGENTS\n\n"
        "## Knowledge Items (KI)\n\n"
        "| File | Topic |\n"
        "|------|-------|\n"
        + extra_ki_rows,
        encoding="utf-8"
    )
    return agents


# ─── sync_agents_md tests ─────────────────────────────────────────────────────

def test_sync_empty_ki_list(tmp_project, monkeypatch):
    """With no KIs in doc_config, sync leaves the table header intact but empty."""
    _setup_modules(monkeypatch, tmp_project)
    agents = _make_agents_md(tmp_project)

    import sync_agents_md
    sync_agents_md.sync_agents_md()

    content = agents.read_text(encoding="utf-8")
    assert "| File | Topic |" in content
    # No data rows should be present (no KIs registered)
    rows = [l for l in content.splitlines()
            if l.strip().startswith("|") and "File" not in l and "---" not in l]
    assert rows == [], f"Expected no KI rows, got: {rows}"


def test_sync_adds_ki_rows(tmp_project, monkeypatch):
    """After registering a KI in doc_config, sync_agents_md adds its row."""
    from conftest import get_know_info
    know_name, know_path, _ = get_know_info(tmp_project)
    cfg_path = know_path / "doc_config.json"
    cfg = json.loads(cfg_path.read_text())
    cfg["knowledge_items"]["KI_module_a.md"] = {
        "description": "Module A documentation",
        "covers": ["Module A"],
        "depends_on": []
    }
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    _setup_modules(monkeypatch, tmp_project)
    agents = _make_agents_md(tmp_project)

    import sync_agents_md
    sync_agents_md.sync_agents_md()

    content = agents.read_text(encoding="utf-8")
    assert "KI_module_a.md" in content
    assert "Module A documentation" in content


def test_sync_replaces_stale_rows(tmp_project, monkeypatch):
    """Stale rows from a previous sync are replaced, not duplicated."""
    from conftest import get_know_info
    know_name, know_path, _ = get_know_info(tmp_project)
    cfg_path = know_path / "doc_config.json"
    cfg = json.loads(cfg_path.read_text())
    cfg["knowledge_items"]["KI_new.md"] = {"description": "New KI", "covers": [], "depends_on": []}
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    _setup_modules(monkeypatch, tmp_project)
    # Prime AGENTS.md with an old stale row
    agents = _make_agents_md(tmp_project, "| `KI_old.md` | Old stuff |\n")

    import sync_agents_md
    sync_agents_md.sync_agents_md()

    content = agents.read_text(encoding="utf-8")
    assert "KI_old.md" not in content, "Stale row should be removed"
    assert "KI_new.md" in content


def test_sync_missing_table_is_graceful(tmp_project, monkeypatch):
    """sync_agents_md exits gracefully when AGENTS.md has no KI table."""
    _setup_modules(monkeypatch, tmp_project)
    agents = tmp_project / "AGENTS.md"
    agents.write_text("# AGENTS\n\nNo KI table here.\n", encoding="utf-8")

    import sync_agents_md
    # Should not raise
    sync_agents_md.sync_agents_md()
    # File should be unchanged
    assert "No KI table here." in agents.read_text(encoding="utf-8")


# ─── add_ki_to_config tests ───────────────────────────────────────────────────

def test_add_ki_registers_entry(tmp_project, monkeypatch):
    """add_ki() writes the new KI entry to doc_config.json."""
    _setup_modules(monkeypatch, tmp_project)

    import add_ki_to_config
    add_ki_to_config.add_ki(
        ki_name="KI_utils.md",
        description="Utility helpers",
        covers=["Utilities"],
        depends_on=["src/utils/"]
    )

    from conftest import get_know_info
    _, know_path, _ = get_know_info(tmp_project)
    cfg = json.loads((know_path / "doc_config.json").read_text())
    assert "KI_utils.md" in cfg["knowledge_items"]
    ki = cfg["knowledge_items"]["KI_utils.md"]
    assert ki["description"] == "Utility helpers"
    assert "src/utils/" in ki["depends_on"]


def test_add_ki_idempotent_update(tmp_project, monkeypatch):
    """Calling add_ki twice with the same key overwrites cleanly."""
    _setup_modules(monkeypatch, tmp_project)

    import add_ki_to_config
    add_ki_to_config.add_ki("KI_x.md", "First", ["A"], [])
    add_ki_to_config.add_ki("KI_x.md", "Second", ["B"], ["src/"])

    from conftest import get_know_info
    _, know_path, _ = get_know_info(tmp_project)
    cfg = json.loads((know_path / "doc_config.json").read_text())
    assert cfg["knowledge_items"]["KI_x.md"]["description"] == "Second"


def test_add_ki_creates_knowledge_items_key(tmp_project, monkeypatch):
    """add_ki() creates the knowledge_items key if it was missing."""
    from conftest import get_know_info
    _, know_path, _ = get_know_info(tmp_project)
    cfg_path = know_path / "doc_config.json"
    cfg = json.loads(cfg_path.read_text())
    del cfg["knowledge_items"]
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    _setup_modules(monkeypatch, tmp_project)

    import add_ki_to_config
    add_ki_to_config.add_ki("KI_fresh.md", "Fresh", [], [])

    cfg_after = json.loads(cfg_path.read_text())
    assert "knowledge_items" in cfg_after
    assert "KI_fresh.md" in cfg_after["knowledge_items"]
