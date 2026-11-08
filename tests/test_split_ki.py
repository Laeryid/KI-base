"""
test_split_ki.py

Tests for split_ki.py:
- analyze_split: identifies dependencies and splits overloaded KI into two balanced groups
- apply_split: atomic creation of two KIs, removal of original if renamed, validation of no lost files
"""

import os
import json
import pytest
from pathlib import Path

from ki_manager.scripts import split_ki, ki_utils


@pytest.fixture
def mini_split_project(tmp_path, monkeypatch):
    """Sets up a project with an overloaded KI (12 files) for split testing."""
    src_dir = tmp_path / "rich"
    src_dir.mkdir()

    # Create 12 files: 6 low-level primitives, 6 high-level components
    primitives = ["color.py", "color_triplet.py", "palette.py", "style.py", "box.py", "cells.py"]
    components = ["table.py", "panel.py", "columns.py", "progress.py", "live.py", "prompt.py"]

    for p in primitives:
        (src_dir / p).write_text(f"# Primitive {p}\nclass {p[:-3].capitalize()}Core:\n    pass\n", encoding="utf-8")

    for c in components:
        # components import primitives
        code = f"# Component {c}\nfrom .color import ColorCore\nfrom .style import StyleCore\nclass {c[:-3].capitalize()}Widget:\n    pass\n"
        (src_dir / c).write_text(code, encoding="utf-8")

    ki_base = tmp_path / ".ki-base"
    ki_dir = ki_base / "knowledge"
    ki_dir.mkdir(parents=True)

    ki_config = {
        "project_name": "mini_rich",
        "paths": {"knowledge_root": ".ki-base", "project_root": "."}
    }
    (ki_base / "ki_config.json").write_text(json.dumps(ki_config), encoding="utf-8")

    all_files = [f"rich/{p}" for p in primitives] + [f"rich/{c}" for c in components]

    original_ki_content = (
        "# KI: Rich All-In-One\n\n"
        "## Overview\nSingle huge KI covering everything.\n\n"
        "## Key Components\nLots of components here.\n"
    )
    (ki_dir / "KI_rich.md").write_text(original_ki_content, encoding="utf-8")

    doc_cfg = {
        "project_name": "mini_rich",
        "coverage_settings": {
            "tracked_modules": [["rich", "Rich Module", 8]]
        },
        "knowledge_items": {
            "KI_rich.md": {
                "summary": "Rich overloaded KI",
                "depends_on": all_files
            }
        }
    }
    (ki_base / "doc_config.json").write_text(json.dumps(doc_cfg, indent=2), encoding="utf-8")

    monkeypatch.setattr(ki_utils, "ACTIVE_WORKSPACE_PATH", str(tmp_path))
    monkeypatch.setattr(ki_utils, "_CACHE", {})
    monkeypatch.chdir(tmp_path)

    return tmp_path, ki_base, all_files


@pytest.mark.positive
def test_analyze_split_bisection(mini_split_project):
    """analyze_split divides 12 files into two balanced groups (each between 4 and 8 files)."""
    tmp_path, ki_base, all_files = mini_split_project

    result = split_ki.analyze_split("KI_rich.md", project_root=str(tmp_path))

    assert result["ki_name"] == "KI_rich.md"
    assert result["total_files"] == 12

    group_a = result["group_a"]["files"]
    group_b = result["group_b"]["files"]

    assert len(group_a) >= 4
    assert len(group_b) >= 4
    assert len(group_a) + len(group_b) == 12
    assert set(group_a).isdisjoint(set(group_b))
    assert set(group_a) | set(group_b) == set(all_files)
    assert "suggested_ki_name" in result["group_a"]
    assert "suggested_ki_name" in result["group_b"]
    assert "markdown_report" in result


@pytest.mark.positive
def test_apply_split_valid(mini_split_project):
    """apply_split creates two new KIs, removes original, and updates doc_config.json."""
    tmp_path, ki_base, all_files = mini_split_project

    analysis = split_ki.analyze_split("KI_rich.md", project_root=str(tmp_path))
    group_a_files = analysis["group_a"]["files"]
    group_b_files = analysis["group_b"]["files"]

    target_a = {
        "ki_name": "KI_rich_primitives.md",
        "summary": "Rich Primitives and Styles",
        "depends_on": group_a_files,
        "content": "# KI: Rich Primitives\n\n## Overview\nPrimitives overview.\n"
    }
    target_b = {
        "ki_name": "KI_rich_widgets.md",
        "summary": "Rich Widgets and Renderables",
        "depends_on": group_b_files,
        "content": "# KI: Rich Widgets\n\n## Overview\nWidgets overview.\n"
    }

    res = split_ki.apply_split("KI_rich.md", target_a, target_b, project_root=str(tmp_path))
    assert res.get("isError") is not True

    # Check files on disk
    ki_dir = ki_base / "knowledge"
    assert not (ki_dir / "KI_rich.md").exists()
    assert (ki_dir / "KI_rich_primitives.md").exists()
    assert (ki_dir / "KI_rich_widgets.md").exists()

    # Check doc_config.json
    cfg = json.loads((ki_base / "doc_config.json").read_text(encoding="utf-8"))
    assert "KI_rich.md" not in cfg["knowledge_items"]
    assert "KI_rich_primitives.md" in cfg["knowledge_items"]
    assert "KI_rich_widgets.md" in cfg["knowledge_items"]
    assert set(cfg["knowledge_items"]["KI_rich_primitives.md"]["depends_on"]) == set(group_a_files)
    assert set(cfg["knowledge_items"]["KI_rich_widgets.md"]["depends_on"]) == set(group_b_files)


@pytest.mark.negative
def test_apply_split_fails_if_files_lost(mini_split_project):
    """apply_split refuses to execute if any files from original KI are missing in the targets."""
    tmp_path, ki_base, all_files = mini_split_project

    target_a = {
        "ki_name": "KI_rich_a.md",
        "summary": "Group A",
        "depends_on": all_files[:5],
        "content": "# A"
    }
    target_b = {
        "ki_name": "KI_rich_b.md",
        "summary": "Group B",
        "depends_on": all_files[5:10], # Missing 2 files!
        "content": "# B"
    }

    res = split_ki.apply_split("KI_rich.md", target_a, target_b, project_root=str(tmp_path))
    assert res.get("isError") is True
    assert "lost" in res["message"].lower() or "missing" in res["message"].lower()

    # Original KI must still exist
    assert (ki_base / "knowledge" / "KI_rich.md").exists()
