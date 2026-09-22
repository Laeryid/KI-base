import os
import sys
import pytest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "src" / "ki_manager" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import find_unmapped_files as fum
import ki_utils


@pytest.mark.positive
def test_find_unmapped_files_basic(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    mapped = src_dir / "mapped.py"
    mapped.write_text("print('mapped')\n", encoding="utf-8")
    unmapped = src_dir / "unmapped.py"
    unmapped.write_text("print('unmapped')\n", encoding="utf-8")

    doc_config = {
        "knowledge_items": {
            "KI_test.md": {
                "depends_on": ["src/mapped.py"]
            }
        }
    }

    with patch.object(ki_utils, "get_project_root", return_value=str(tmp_path)), \
         patch.object(ki_utils, "get_doc_config", return_value=doc_config), \
         patch.object(ki_utils, "get_exclude_patterns", return_value={".git", "__pycache__"}), \
         patch("sys.stdout", new=StringIO()) as fake_out:
        fum.find_unmapped_files("src")
        out = fake_out.getvalue()
        lines = [line.strip().replace("\\", "/") for line in out.splitlines()]
        assert "- src/unmapped.py" in lines
        assert "- src/mapped.py" not in lines


@pytest.mark.positive
def test_find_unmapped_files_non_ascii_cyrillic(tmp_path):
    """Verifies that find_unmapped_files handles paths with Cyrillic / non-ASCII characters."""
    plan_dir = tmp_path / "планы"
    plan_dir.mkdir()
    doc_file = plan_dir / "план_работы.md"
    doc_file.write_text("Описание\n", encoding="utf-8")

    doc_config = {"knowledge_items": {}}

    with patch.object(ki_utils, "get_project_root", return_value=str(tmp_path)), \
         patch.object(ki_utils, "get_doc_config", return_value=doc_config), \
         patch.object(ki_utils, "get_exclude_patterns", return_value={".git"}), \
         patch("sys.stdout", new=StringIO()) as fake_out:
        fum.find_unmapped_files("планы")
        out = fake_out.getvalue()
        assert "план_работы.md" in out


@pytest.mark.positive
def test_find_unmapped_files_respects_exclude_patterns(tmp_path):
    """Verifies that directories/files in exclude_patterns are ignored."""
    brain_dir = tmp_path / "brain"
    brain_dir.mkdir()
    (brain_dir / "note.md").write_text("note\n", encoding="utf-8")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "keep.py").write_text("code\n", encoding="utf-8")

    doc_config = {"knowledge_items": {}}

    with patch.object(ki_utils, "get_project_root", return_value=str(tmp_path)), \
         patch.object(ki_utils, "get_doc_config", return_value=doc_config), \
         patch.object(ki_utils, "get_exclude_patterns", return_value={".git", "brain"}):
        with patch("sys.stdout", new=StringIO()) as fake_out:
            fum.find_unmapped_files(".")
            out = fake_out.getvalue()
            assert "keep.py" in out
            assert "brain" not in out
