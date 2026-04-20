"""
test_generate_dir_index.py

Tests for generate_dir_index.py:
- generates a file at the expected path
- output contains project name
- hidden dirs (knowledge root) appear in tree when they are the knowledge root
- depth limit is respected
"""

import os
import sys
import pytest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def _reload_gdi(monkeypatch, tmp_project):
    if "ki_utils" in sys.modules:
        del sys.modules["ki_utils"]
    if "generate_dir_index" in sys.modules:
        del sys.modules["generate_dir_index"]

    from conftest import get_know_info
    know_name, know_path, config_path = get_know_info(tmp_project)
    config_path = str(config_path)
    monkeypatch.setattr(sys, "argv", ["prog", "--config", config_path])
    monkeypatch.chdir(tmp_project)

    import generate_dir_index
    return generate_dir_index


def test_generates_file(tmp_project, monkeypatch):
    """generate_dir_index writes DIR_INDEX.md."""
    gdi = _reload_gdi(monkeypatch, tmp_project)
    output = str(know_path / "DIR_INDEX.md")
    gdi.generate_dir_index(str(tmp_project), output, know_name, max_depth=3)
    assert Path(output).exists()


def test_output_contains_project_name(tmp_project, monkeypatch):
    """DIR_INDEX.md header uses the actual project folder name."""
    gdi = _reload_gdi(monkeypatch, tmp_project)
    output = str(know_path / "DIR_INDEX.md")
    gdi.generate_dir_index(str(tmp_project), output, know_name, max_depth=3)

    content = Path(output).read_text(encoding="utf-8")
    project_name = tmp_project.name
    assert project_name in content, f"Expected {project_name!r} in DIR_INDEX header"


def test_output_contains_src(tmp_project, monkeypatch):
    """DIR_INDEX.md contains the src/ directory."""
    gdi = _reload_gdi(monkeypatch, tmp_project)
    output = str(know_path / "DIR_INDEX.md")
    gdi.generate_dir_index(str(tmp_project), output, know_name, max_depth=3)

    content = Path(output).read_text(encoding="utf-8")
    assert "src/" in content


def test_count_files_in_dir(tmp_project, monkeypatch):
    """count_files_in_dir counts all files recursively."""
    gdi = _reload_gdi(monkeypatch, tmp_project)
    src = tmp_project / "src"
    count = gdi.count_files_in_dir(str(src))
    assert count >= 1  # at least code.py


def test_depth_limit(tmp_project, monkeypatch):
    """With max_depth=0, the tree should be empty (no sub-dirs shown at depth 1)."""
    gdi = _reload_gdi(monkeypatch, tmp_project)
    output = str(know_path / "DIR_INDEX_shallow.md")
    # depth=0 means only the root entry appears — no children
    gdi.generate_dir_index(str(tmp_project), output, know_name, max_depth=0)
    content = Path(output).read_text(encoding="utf-8")
    # The tree block should be short (just the root line, no subdirs)
    tree_block = content.split("```")[1] if "```" in content else ""
    lines_with_dirs = [l for l in tree_block.splitlines() if "|--" in l or "`--" in l]
    assert lines_with_dirs == [], f"Expected empty tree at depth 0, got: {lines_with_dirs}"
