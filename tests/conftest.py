"""
conftest.py — shared fixtures for KI_base tests.
"""

import os
import sys
import json
import tempfile
import pytest
from pathlib import Path

# Make scripts importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def tmp_project(tmp_path):
    """
    Creates a minimal fake project structure:
        tmp_path/
            src/
                module_a/
                    code.py
            {know_name}/
                doc_config.json
                ki_config.json
                knowledge/
                decisions/
    """
    know_name = os.environ.get("KNOWLEDGE_DIR_NAME", ".know")
    know = tmp_path / know_name
    know.mkdir()
    (know / "knowledge").mkdir()
    (know / "decisions").mkdir()

    src = tmp_path / "src" / "module_a"
    src.mkdir(parents=True)
    (src / "code.py").write_text("def hello(): pass\n", encoding="utf-8")

    doc_config = {
        "coverage_settings": {
            "tracked_modules": [
                ["src/module_a", "Module A", 5]
            ],
            "thresholds": {"density": 50.0, "complexity": 10}
        },
        "artifacts": {
            "README.md": {"description": "docs", "depends_on": ["src/"]}
        },
        "knowledge_items": {},
        "knowledge_system": {
            "mcp_server": {"name": "KnowledgeManager", "version": "1.0.0", "jail_dir": know_name},
            "tools": []
        }
    }
    (know / "doc_config.json").write_text(
        json.dumps(doc_config, indent=4), encoding="utf-8"
    )

    ki_config = {
        "paths": {
            "knowledge_root": know_name,
            "agent_instructions": "AGENTS.md",
            "workflows_dir": ".agent/workflows",
            "venv_python": sys.executable
        },
        "auto_resolve": True
    }
    (know / "ki_config.json").write_text(
        json.dumps(ki_config, indent=4), encoding="utf-8"
    )

    return tmp_path


def get_know_info(tmp_project):
    """Returns (know_name, know_path, ki_config_path)."""
    # For tests, we use the default '.know' unless we want to test others
    know_name = ".know"
    know_path = tmp_project / know_name
    ki_config_path = know_path / "ki_config.json"
    return know_name, know_path, ki_config_path
