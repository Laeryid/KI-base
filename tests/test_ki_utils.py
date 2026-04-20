"""
test_ki_utils.py — tests for ki_utils config loading and path resolution.
"""

import os
import sys
import json
import pytest
from pathlib import Path


def test_resolve_knowledge_root_from_scripts(tmp_project, monkeypatch):
    """resolve_knowledge_root finds knowledge root when ki_utils is in scripts/."""
    import importlib

    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    monkeypatch.chdir(tmp_project)

    # Reload ki_utils so it re-resolves paths in the tmp_project context
    if "ki_utils" in sys.modules:
        del sys.modules["ki_utils"]

    from conftest import get_know_info
    know_name, _, config_path = get_know_info(tmp_project)
    config_path = str(config_path)
    monkeypatch.setattr(sys, "argv", ["prog", "--config", config_path])

    import ki_utils
    assert ki_utils.KNOWLEDGE_ROOT != "", "KNOWLEDGE_ROOT should be resolved"
    assert os.path.exists(ki_utils.DOC_CONFIG_PATH), "doc_config.json must exist"


def test_get_doc_config_returns_dict(tmp_project, monkeypatch):
    """get_doc_config() returns a non-empty dict when config exists."""
    from conftest import get_know_info
    _, _, config_path = get_know_info(tmp_project)
    monkeypatch.chdir(tmp_project)
    if "ki_utils" in sys.modules:
        del sys.modules["ki_utils"]

    config_path = str(config_path)
    monkeypatch.setattr(sys, "argv", ["prog", "--config", config_path])

    import ki_utils
    cfg = ki_utils.get_doc_config()
    assert "coverage_settings" in cfg
    assert "knowledge_items" in cfg
