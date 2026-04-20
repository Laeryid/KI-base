"""
test_mcp_security.py — tests for the MCP sandbox (validate_path).
"""

import os
import sys
import pytest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def patch_jail(tmp_project, monkeypatch):
    """Patch JAIL_DIR in knowledge_mcp to use the tmp knowledge root folder."""
    # We import validate_path directly after patching ki_utils
    if "ki_utils" in sys.modules:
        del sys.modules["ki_utils"]
    if "knowledge_mcp" in sys.modules:
        del sys.modules["knowledge_mcp"]

    from conftest import get_know_info
    _, _, config_path = get_know_info(tmp_project)
    config_path = str(config_path)
    monkeypatch.setattr(sys, "argv", ["prog", "--config", config_path])
    monkeypatch.chdir(tmp_project)


def get_validate_path(tmp_project):
    """Helper: import validate_path with JAIL_DIR set to tmp knowledge root."""
    import importlib
    import knowledge_mcp
    from conftest import get_know_info
    know_name, know_path, _ = get_know_info(tmp_project)
    knowledge_mcp.JAIL_DIR = str(know_path)
    return knowledge_mcp.validate_path


def test_valid_path_allowed(tmp_project):
    validate_path = get_validate_path(tmp_project)
    result = validate_path("knowledge/KI_template.md")
    assert know_name in result


def test_parent_traversal_blocked(tmp_project):
    validate_path = get_validate_path(tmp_project)
    with pytest.raises(PermissionError):
        validate_path("../src/secret.py")


def test_absolute_path_blocked(tmp_project):
    validate_path = get_validate_path(tmp_project)
    with pytest.raises(PermissionError):
        validate_path("/etc/passwd")


def test_write_python_blocked(tmp_project):
    validate_path = get_validate_path(tmp_project)
    with pytest.raises(PermissionError):
        validate_path("scripts/evil.py", is_write=True)


def test_write_markdown_allowed(tmp_project):
    validate_path = get_validate_path(tmp_project)
    # Should NOT raise
    result = validate_path("knowledge/new_ki.md", is_write=True)
    assert result.endswith("new_ki.md")
