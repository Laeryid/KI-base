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
def setup_mcp(monkeypatch, tmp_project):
    """Setup environment for MCP security tests."""
    import ki_utils
    import knowledge_mcp
    
    from conftest import get_know_info
    _, _, config_path = get_know_info(tmp_project)
    
    monkeypatch.setattr(ki_utils, "_CACHE", {})
    monkeypatch.setattr(sys, "argv", ["prog", "--config", str(config_path)])
    monkeypatch.chdir(tmp_project)
    return knowledge_mcp


@pytest.mark.positive
def test_valid_path_allowed(tmp_project, setup_mcp):
    from conftest import get_know_info
    know_name, _, _ = get_know_info(tmp_project)
    validate_path = setup_mcp.validate_path
    result = validate_path("knowledge/KI_template.md")
    assert know_name in result


@pytest.mark.negative
def test_parent_traversal_blocked(setup_mcp):
    validate_path = setup_mcp.validate_path
    with pytest.raises(PermissionError):
        validate_path("../src/secret.py")


@pytest.mark.negative
def test_absolute_path_blocked(setup_mcp):
    validate_path = setup_mcp.validate_path
    with pytest.raises(PermissionError):
        validate_path("/etc/passwd")


@pytest.mark.negative
def test_write_python_blocked(setup_mcp):
    validate_path = setup_mcp.validate_path
    with pytest.raises(PermissionError):
        validate_path("scripts/evil.py", is_write=True)


@pytest.mark.positive
def test_write_markdown_allowed(setup_mcp):
    validate_path = setup_mcp.validate_path
    # Should NOT raise
    result = validate_path("knowledge/new_ki.md", is_write=True)
    assert result.endswith("new_ki.md")
