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


@pytest.mark.positive
def test_find_unmapped_files_respects_gitignore(tmp_path):
    """Verifies that .gitignore rules in project root are loaded and applied."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("data/\n*.tmp\n# comment\n", encoding="utf-8")

    data_dir = tmp_path / "data" / "market"
    data_dir.mkdir(parents=True)
    (data_dir / "quotes.csv").write_text("1,2,3\n", encoding="utf-8")

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "valid.py").write_text("print(1)\n", encoding="utf-8")
    (src_dir / "temp.tmp").write_text("temp\n", encoding="utf-8")

    doc_config = {"knowledge_items": {}}

    with patch.object(ki_utils, "get_project_root", return_value=str(tmp_path)), \
         patch.object(ki_utils, "get_doc_config", return_value=doc_config):
        unmapped = fum.get_unmapped_files(".")
        assert "src/valid.py" in unmapped
        assert not any("data" in f for f in unmapped)
        assert not any(f.endswith(".tmp") for f in unmapped)


@pytest.mark.positive
def test_find_unmapped_files_respects_exclude_section(tmp_path):
    """Verifies that 'exclude' (alongside 'exclude_patterns') in doc_config is respected."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("print('app')\n", encoding="utf-8")
    (src_dir / "secret.py").write_text("secret\n", encoding="utf-8")

    doc_config = {
        "coverage_settings": {
            "exclude": ["src/secret.py"]
        },
        "knowledge_items": {}
    }

    with patch.object(ki_utils, "get_project_root", return_value=str(tmp_path)), \
         patch.object(ki_utils, "get_doc_config", return_value=doc_config):
        unmapped = fum.get_unmapped_files("src")
        assert "src/app.py" in unmapped
        assert "src/secret.py" not in unmapped


@pytest.mark.positive
def test_find_unmapped_files_scopes_to_tracked_modules_on_default(tmp_path):
    """Verifies that scanning with target_path='.' scopes to tracked_modules when defined."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "module.py").write_text("print('module')\n", encoding="utf-8")

    market_dir = tmp_path / "data" / "market"
    market_dir.mkdir(parents=True)
    (market_dir / "huge_data.bin_data").write_text("data\n", encoding="utf-8")

    doc_config = {
        "coverage_settings": {
            "tracked_modules": [["src", "Source code", 8]]
        },
        "knowledge_items": {}
    }

    with patch.object(ki_utils, "get_project_root", return_value=str(tmp_path)), \
         patch.object(ki_utils, "get_doc_config", return_value=doc_config):
        unmapped = fum.get_unmapped_files(".")
        assert "src/module.py" in unmapped
        # data/market must not even be scanned
        assert not any("data" in f for f in unmapped)
