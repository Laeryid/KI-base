import os
import sys
import json
import pytest
from pathlib import Path

# Add scripts to path for imports
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import ki_utils

@pytest.fixture
def mock_registry(tmp_path, monkeypatch):
    """Overrides registry path to a temp file for tests."""
    reg_file = tmp_path / "test_registry.json"
    monkeypatch.setattr(ki_utils, "get_registry_path", lambda: reg_file)
    return reg_file

def test_register_and_load_project(tmp_project, mock_registry):
    """Project can be registered and appears in registry."""
    from conftest import get_know_info
    _, know_path, ki_config_path = get_know_info(tmp_project)
    
    success, msg = ki_utils.register_project(str(ki_config_path))
    assert success is True
    assert str(tmp_project) in ki_utils.load_registry()["projects"]

def test_find_project_by_cwd_exact(tmp_project, mock_registry):
    """Registry finds project root when CWD is the root."""
    from conftest import get_know_info
    _, _, ki_config_path = get_know_info(tmp_project)
    ki_utils.register_project(str(ki_config_path))
    
    match = ki_utils.find_project_by_cwd(str(tmp_project))
    assert match is not None
    assert match["name"] == tmp_project.name

def test_find_project_by_cwd_deep(tmp_project, mock_registry):
    """Registry finds project root when CWD is deep inside the project."""
    from conftest import get_know_info
    _, _, ki_config_path = get_know_info(tmp_project)
    ki_utils.register_project(str(ki_config_path))
    
    deep_path = tmp_project / "src" / "module_a"
    match = ki_utils.find_project_by_cwd(str(deep_path))
    assert match is not None
    assert match["name"] == tmp_project.name

def test_find_project_context_switch(tmp_path, mock_registry):
    """Registry handles multiple projects and switches context correctly."""
    # Project A
    proj_a = tmp_path / "ProjA"
    proj_a.mkdir()
    know_a = proj_a / ".know"
    know_a.mkdir()
    config_a = know_a / "ki_config.json"
    config_a.write_text(json.dumps({"paths": {"project_root": ".."}}))
    ki_utils.register_project(str(config_a))
    
    # Project B
    proj_b = tmp_path / "ProjB"
    proj_b.mkdir()
    know_b = proj_b / ".know"
    know_b.mkdir()
    config_b = know_b / "ki_config.json"
    config_b.write_text(json.dumps({"paths": {"project_root": ".."}}))
    ki_utils.register_project(str(config_b))
    
    # Check A
    match_a = ki_utils.find_project_by_cwd(str(proj_a / "some_dir"))
    assert match_a["name"] == "ProjA"
    
    # Check B
    match_b = ki_utils.find_project_by_cwd(str(proj_b / "other_dir"))
    assert match_b["name"] == "ProjB"

def test_find_project_not_found(tmp_path, mock_registry):
    """Returns None if CWD is outside any registered project."""
    match = ki_utils.find_project_by_cwd(str(tmp_path / "unregistered"))
    assert match is None

def test_soft_init_preserves_config(tmp_project, mock_registry, monkeypatch):
    """init_ki_system preserves existing config fields while updating paths."""
    from conftest import get_know_info
    _, know_path, ki_config_path = get_know_info(tmp_project)
    
    # Pre-existing custom setting
    custom_cfg = {
        "paths": {"project_root": ".."},
        "custom_setting": "preserved"
    }
    ki_config_path.write_text(json.dumps(custom_cfg))
    
    # Run init
    import init_ki_system
    monkeypatch.chdir(tmp_project)
    monkeypatch.setattr(sys, "argv", ["init_ki_system.py"])
    init_ki_system.init_ki_system()
    
    # Verify
    import importlib
    importlib.reload(init_ki_system)
    updated_cfg = json.loads(ki_config_path.read_text())
    assert updated_cfg["custom_setting"] == "preserved"
    assert updated_cfg["paths"]["knowledge_root"] == ".know"
