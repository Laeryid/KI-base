"""
Tests for ki-manager flexible configuration loading, registry inline_config,
custom knowledge_root names, and positive/negative scenarios.
"""

import json
import os
import sys
import pytest
from pathlib import Path

# Add scripts and src to path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(SRC_DIR / "ki_manager" / "scripts"))

from ki_manager.scripts import ki_utils
from ki_manager.tools import scaffold


@pytest.fixture
def mock_registry(tmp_path, monkeypatch):
    """Overrides registry path to a temp file for tests."""
    reg_file = tmp_path / "test_registry.json"
    monkeypatch.setattr(ki_utils, "get_registry_path", lambda: reg_file)
    return reg_file


# ==============================================================================
# Positive Scenarios
# ==============================================================================

@pytest.mark.positive
def test_register_with_inline_config(tmp_path, mock_registry, monkeypatch):
    """A project can be registered with pure inline_config without any file on disk."""
    ws = tmp_path / "PureInlineProject"
    ws.mkdir()
    monkeypatch.setattr(ki_utils, "ACTIVE_WORKSPACE_PATH", str(ws))

    success, msg = ki_utils.register_project(
        workspace=str(ws),
        inline_config={"paths": {"knowledge_root": "custom_docs"}, "project_name": "InlineProj"}
    )
    assert success is True
    assert "registered at" in msg

    # Verify registry content
    reg = ki_utils.load_registry()
    norm_ws = ki_utils.normalize_path(str(ws))
    assert norm_ws in reg["projects"]
    assert reg["projects"][norm_ws]["config"]["project_name"] == "InlineProj"

    # Verify ki_utils resolves config and knowledge_root
    cfg = ki_utils.load_ki_config()
    assert cfg.get("project_name") == "InlineProj"
    assert ki_utils.get_knowledge_root() == os.path.join(str(ws), "custom_docs")
    assert ki_utils.get_project_root() == str(ws)


@pytest.mark.positive
@pytest.mark.parametrize("loc_type,sub_path", [
    ("root", "ki_config.json"),
    ("dot_config", os.path.join(".config", "ki_config.json")),
    ("config_dir", os.path.join("config", "ki_config.json")),
    ("ki_base", os.path.join(".ki-base", "ki_config.json")),
    ("know_dir", os.path.join(".know", "ki_config.json")),
])
def test_load_config_from_various_locations(tmp_path, mock_registry, monkeypatch, loc_type, sub_path):
    """ki_utils finds ki_config.json across standard search hierarchy locations."""
    ws = tmp_path / f"Proj_{loc_type}"
    target_cfg = ws / sub_path
    target_cfg.parent.mkdir(parents=True, exist_ok=True)
    target_cfg.write_text(json.dumps({
        "project_name": f"Proj_{loc_type}",
        "paths": {"knowledge_root": ".ki-base"}
    }), encoding="utf-8")

    monkeypatch.setattr(ki_utils, "ACTIVE_WORKSPACE_PATH", str(ws))

    cfg = ki_utils.load_ki_config()
    assert cfg.get("project_name") == f"Proj_{loc_type}"
    assert ki_utils.normalize_path(cfg.get("_loaded_from")) == ki_utils.normalize_path(str(target_cfg))
    assert ki_utils.normalize_path(ki_utils.get_project_root()) == ki_utils.normalize_path(str(ws))


@pytest.mark.positive
def test_custom_knowledge_root_resolution(tmp_path, mock_registry, monkeypatch):
    """Custom paths.knowledge_root in ki_config.json correctly defines knowledge_root."""
    ws = tmp_path / "CustomKBProj"
    ws.mkdir()
    cfg_file = ws / "ki_config.json"
    cfg_file.write_text(json.dumps({
        "project_name": "CustomKB",
        "paths": {"knowledge_root": "my_knowledge_folder"}
    }), encoding="utf-8")

    monkeypatch.setattr(ki_utils, "ACTIVE_WORKSPACE_PATH", str(ws))

    assert ki_utils.get_knowledge_root() == os.path.join(str(ws), "my_knowledge_folder")
    assert ki_utils.get_project_root() == str(ws)


@pytest.mark.positive
def test_init_project_with_custom_knowledge_root_and_root_config(tmp_path, mock_registry, monkeypatch):
    """scaffold.init_project supports custom knowledge_root and placing ki_config.json in project root."""
    ws = tmp_path / "ScaffoldCustomProj"
    ws.mkdir()
    monkeypatch.setattr(ki_utils, "ACTIVE_WORKSPACE_PATH", str(ws))

    res = scaffold.init_project({
        "project_path": str(ws),
        "knowledge_root": "team_docs",
        "config_location": "root"
    })
    assert "Initialization complete" in res

    # Verify file system structure
    assert (ws / "ki_config.json").exists()
    assert (ws / "team_docs").exists()
    assert (ws / "team_docs" / "doc_config.json").exists()
    assert (ws / "team_docs" / "DIR_INDEX.md").exists()
    assert (ws / "team_docs" / "knowledge" / "_OVERVIEW.ki.md").exists()

    # Verify ki_config content has custom knowledge_root
    ki_cfg = json.loads((ws / "ki_config.json").read_text(encoding="utf-8"))
    assert ki_cfg["paths"]["knowledge_root"] == "team_docs"

    # Verify ki_utils picks it up
    assert ki_utils.get_knowledge_root() == str(ws / "team_docs")


# ==============================================================================
# Negative Scenarios
# ==============================================================================

@pytest.mark.negative
def test_register_no_workspace_and_no_config(mock_registry):
    """register_project returns error when neither config_path nor workspace is provided."""
    success, msg = ki_utils.register_project(config_path=None, workspace=None)
    assert success is False
    assert "Must provide config_path or workspace" in msg


@pytest.mark.negative
def test_register_nonexistent_config_path(tmp_path, mock_registry):
    """register_project returns error when specified config_path does not exist."""
    fake_path = tmp_path / "does_not_exist" / "ki_config.json"
    success, msg = ki_utils.register_project(config_path=str(fake_path))
    assert success is False
    assert "Config not found" in msg


@pytest.mark.negative
def test_register_invalid_json_config(tmp_path, mock_registry):
    """register_project returns error when specified config file is not valid JSON."""
    bad_cfg = tmp_path / "broken_config.json"
    bad_cfg.write_text("{ this is not valid json : [", encoding="utf-8")

    success, msg = ki_utils.register_project(config_path=str(bad_cfg))
    assert success is False
    assert "Invalid JSON in config" in msg


@pytest.mark.negative
def test_init_project_missing_project_path():
    """init_project returns error when project_path argument is missing."""
    res = scaffold.init_project({})
    assert "Error: project_path is required" in res


@pytest.mark.negative
def test_init_project_nonexistent_project_path(tmp_path):
    """init_project returns error when project_path directory does not exist."""
    missing_dir = tmp_path / "definitely_nonexistent_dir_12345"
    res = scaffold.init_project({"project_path": str(missing_dir)})
    assert "Error: project_path does not exist" in res
