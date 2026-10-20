import os
import pytest
from pathlib import Path
from ki_manager.scripts.check_ki_drift import (
    parse_ki_file,
    check_single_ki,
    format_drift_markdown,
    run_drift_check
)


def test_parse_ki_file(tmp_path):
    ki_file = tmp_path / "KI_sample.md"
    ki_file.write_text(
        "<!-- scaffold: true -->\n"
        "<!-- last_verified: 2026-05-01 -->\n"
        "# KI: Sample Module\n\n"
        "## Overview\nSample overview text.\n\n"
        "## Key Components\n"
        "| Class / Function | File | Purpose |\n"
        "|---|---|---|\n"
        "| `Worker` | `src/worker.py` | Runs jobs |\n"
        "| `do_work` | `src/worker.py` | Processes task |\n\n"
        "## Related KIs\n"
        "- [[KI_other.md]]\n",
        encoding="utf-8"
    )

    data = parse_ki_file(ki_file)
    assert data["last_verified"] == "2026-05-01"
    assert data["is_scaffold"] is True
    assert len(data["table_symbols"]) == 2
    assert data["table_symbols"][0] == {"symbol": "Worker", "file": "src/worker.py"}
    assert "KI_other.md" in data["wiki_links"]


def test_drift_detection_dead_and_unmapped(tmp_path):
    project_root = tmp_path / "project"
    knowledge_dir = project_root / ".ki-base" / "knowledge"
    src_dir = project_root / "src"
    knowledge_dir.mkdir(parents=True)
    src_dir.mkdir(parents=True)

    # Source code with a new function and missing old function
    py_file = src_dir / "worker.py"
    py_file.write_text(
        "class Worker:\n    pass\n\n"
        "def new_function():\n    pass\n",
        encoding="utf-8"
    )

    # KI references obsolete `deleted_function`
    ki_path = knowledge_dir / "KI_worker.md"
    ki_path.write_text(
        "<!-- last_verified: 2026-01-01 -->\n"
        "# KI: Worker Module\n\n"
        "## Key Components\n"
        "| Class / Function | File | Purpose |\n"
        "|---|---|---|\n"
        "| `Worker` | `src/worker.py` | Active |\n"
        "| `deleted_function` | `src/worker.py` | Removed in code |\n\n"
        "## Related KIs\n"
        "- [[KI_nonexistent.md]]\n",
        encoding="utf-8"
    )

    doc_config = {
        "knowledge_items": {
            "KI_worker.md": {
                "depends_on": ["src/worker.py"]
            }
        }
    }

    result = check_single_ki(
        "KI_worker.md",
        ki_path,
        doc_config,
        str(project_root),
        knowledge_dir
    )

    assert result["drift_count"] > 0
    dead = [d["symbol"] for d in result["dead_symbols"]]
    assert "deleted_function" in dead

    unmapped = [u["symbol"] for u in result["unmapped_symbols"]]
    assert "new_function" in unmapped

    assert "KI_nonexistent.md" in result["broken_links"]


def test_format_drift_markdown_clean():
    clean_results = [{"ki": "KI_clean.md", "drift_count": 0}]
    md = format_drift_markdown(clean_results)
    assert "No drift detected" in md



def test_parse_ki_file_skips_table_without_file_column(tmp_path):
    """Verifies that tables lacking a File/Path column (e.g. Tool | Access | Purpose) are ignored."""
    ki_file = tmp_path / "KI_facade.md"
    ki_file.write_text(
        "# KI: Facade\n\n"
        "## Key Components\n"
        "| Tool | Access | Purpose |\n"
        "|---|---|---|\n"
        "| `ki_read` | read-only | Reads content |\n"
        "| `ki_mutate` | mutating | Updates content |\n",
        encoding="utf-8"
    )

    data = parse_ki_file(ki_file)
    assert len(data["table_symbols"]) == 0


def test_check_single_ki_no_spurious_missing_file_for_access_table(tmp_path):
    """Verifies that check_single_ki does NOT report 'Missing file: Access' or 'Missing file: read-only'."""
    project_root = tmp_path / "project"
    knowledge_dir = project_root / ".ki-base" / "knowledge"
    knowledge_dir.mkdir(parents=True)

    ki_path = knowledge_dir / "KI_facade.md"
    ki_path.write_text(
        "# KI: Facade\n\n"
        "## Key Components\n"
        "| Tool | Access | Purpose |\n"
        "|---|---|---|\n"
        "| `ki_read` | read-only | Reads content |\n"
        "| `ki_mutate` | mutating | Updates content |\n",
        encoding="utf-8"
    )

    doc_config = {
        "knowledge_items": {
            "KI_facade.md": {
                "depends_on": []
            }
        }
    }

    result = check_single_ki(
        "KI_facade.md",
        ki_path,
        doc_config,
        str(project_root),
        knowledge_dir
    )

    assert result["missing_files"] == []
    assert result["dead_symbols"] == []


def test_parse_ki_file_with_custom_file_column_position(tmp_path):
    """Verifies that column ordering with File Path in 3rd column is correctly extracted."""
    ki_file = tmp_path / "KI_custom.md"
    ki_file.write_text(
        "# KI: Custom\n\n"
        "## Key Components\n"
        "| Method | Description | File Path |\n"
        "|:---|:---|:---|\n"
        "| `execute_task` | Runs the task | `src/executor.py` |\n",
        encoding="utf-8"
    )

    data = parse_ki_file(ki_file)
    assert len(data["table_symbols"]) == 1
    assert data["table_symbols"][0] == {"symbol": "execute_task", "file": "src/executor.py"}
