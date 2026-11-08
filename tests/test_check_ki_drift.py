import os
import pytest
from pathlib import Path
from ki_manager.scripts.check_ki_drift import (
    parse_ki_file,
    check_single_ki,
    format_drift_markdown,
    run_drift_check,
    extract_cell_symbols,
    extract_all_defined_names,
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


def test_extract_cell_symbols_handling():
    # Regular single symbols
    assert extract_cell_symbols("`Worker`") == ["Worker"]
    assert extract_cell_symbols("Worker") == ["Worker"]
    assert extract_cell_symbols("`do_work()`") == ["do_work"]

    # Compound symbols
    assert extract_cell_symbols("`cell_len / set_cell_size`") == ["cell_len", "set_cell_size"]
    assert extract_cell_symbols("`cell_len` / `set_cell_size`") == ["cell_len", "set_cell_size"]
    assert extract_cell_symbols("`words`, `divide_line`") == ["words", "divide_line"]
    assert extract_cell_symbols("`func_a; func_b`") == ["func_a", "func_b"]

    # Qualified symbols
    assert extract_cell_symbols("`Worker.process`") == ["Worker.process"]

    # Descriptive markers that should be ignored (return empty list)
    assert extract_cell_symbols("*(lookup table)*") == []
    assert extract_cell_symbols("*(file)*") == []
    assert extract_cell_symbols("(constants)") == []
    assert extract_cell_symbols("—") == []
    assert extract_cell_symbols("-") == []
    assert extract_cell_symbols("N/A") == []
    assert extract_cell_symbols("`*(lookup table)*`") == []
    assert extract_cell_symbols("*various helpers*") == []


def test_drift_constants_and_compound_symbols(tmp_path):
    """Verifies that UPPER_CASE/snake_case constants and compound symbols do not trigger dead symbol warnings."""
    project_root = tmp_path / "project"
    knowledge_dir = project_root / ".ki-base" / "knowledge"
    src_dir = project_root / "src"
    knowledge_dir.mkdir(parents=True)
    src_dir.mkdir(parents=True)

    py_file = src_dir / "utils.py"
    py_file.write_text(
        "DEFAULT_STYLES = {'dark': True}\n"
        "SPINNERS: list = ['dots']\n"
        "def cell_len(s):\n    return len(s)\n"
        "def set_cell_size(s, size):\n    pass\n"
        "def helper_one():\n    pass\n"
        "def helper_two():\n    pass\n",
        encoding="utf-8"
    )

    ki_path = knowledge_dir / "KI_utils.md"
    ki_path.write_text(
        "<!-- last_verified: 2026-05-01 -->\n"
        "# KI: Utils\n\n"
        "## Key Components\n"
        "| Class / Function | File | Purpose |\n"
        "|---|---|---|\n"
        "| `DEFAULT_STYLES` | `src/utils.py` | Theme map |\n"
        "| `SPINNERS` | `src/utils.py` | Spinner list |\n"
        "| `cell_len / set_cell_size` | `src/utils.py` | String sizing |\n"
        "| *(lookup table)* | `src/utils.py` | Data reference |\n",
        encoding="utf-8"
    )

    doc_config = {
        "knowledge_items": {
            "KI_utils.md": {
                "depends_on": ["src/utils.py"]
            }
        }
    }

    result = check_single_ki(
        "KI_utils.md",
        ki_path,
        doc_config,
        str(project_root),
        knowledge_dir
    )

    # All defined constants, compound functions, and descriptive marker must have no dead symbols
    assert result["dead_symbols"] == []
    assert result["missing_files"] == []
    assert result["broken_links"] == []
    # Unmapped symbols should not increment drift_count
    assert result["drift_count"] == 0


def test_drift_compound_symbol_detects_actual_dead_subsymbol(tmp_path):
    """Verifies that if one function in a compound cell is deleted, it is correctly identified as dead."""
    project_root = tmp_path / "project"
    knowledge_dir = project_root / ".ki-base" / "knowledge"
    src_dir = project_root / "src"
    knowledge_dir.mkdir(parents=True)
    src_dir.mkdir(parents=True)

    py_file = src_dir / "utils.py"
    py_file.write_text(
        "def cell_len(s):\n    return len(s)\n",
        encoding="utf-8"
    )

    ki_path = knowledge_dir / "KI_utils.md"
    ki_path.write_text(
        "# KI: Utils\n\n"
        "## Key Components\n"
        "| Class / Function | File | Purpose |\n"
        "|---|---|---|\n"
        "| `cell_len / deleted_function` | `src/utils.py` | String sizing |\n",
        encoding="utf-8"
    )

    doc_config = {
        "knowledge_items": {
            "KI_utils.md": {
                "depends_on": ["src/utils.py"]
            }
        }
    }

    result = check_single_ki(
        "KI_utils.md",
        ki_path,
        doc_config,
        str(project_root),
        knowledge_dir
    )

    dead = [d["symbol"] for d in result["dead_symbols"]]
    assert "deleted_function" in dead
    assert "cell_len" not in dead
    assert result["drift_count"] == 1


def test_unmapped_symbols_not_in_drift_count_and_clean_format():
    """Verifies that clean KI with only unmapped advisory symbols formats as 'No drift detected'."""
    clean_results = [{
        "ki": "KI_clean.md",
        "drift_count": 0,
        "dead_symbols": [],
        "missing_files": [],
        "broken_links": [],
        "date_drifts": [],
        "integrity_issues": [],
        "unmapped_symbols": [{"symbol": "auxiliary_tool", "kind": "function", "file": "src/tool.py"}],
    }]
    md = format_drift_markdown(clean_results)
    assert "No drift detected" in md
    assert "⚠️" not in md
