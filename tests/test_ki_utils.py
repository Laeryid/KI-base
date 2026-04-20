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
