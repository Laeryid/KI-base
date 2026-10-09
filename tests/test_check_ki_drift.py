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
