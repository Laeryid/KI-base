"""
test_init_ki_system.py

Tests for init_ki_system.py helper functions:
- detect_venv
- update_gitignore (idempotency, content correctness)
- update_agent_instructions (adds sections, skips if present)
"""

import os
import sys
import json
import pytest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import init_ki_system


# ─── detect_venv ──────────────────────────────────────────────────────────────

@pytest.mark.positive
def test_detect_venv_finds_scripts_python(tmp_path):
    """detect_venv returns the path when .venv/Scripts/python.exe exists."""
    venv_scripts = tmp_path / ".venv" / "Scripts"
    venv_scripts.mkdir(parents=True)
    fake_py = venv_scripts / "python.exe"
    fake_py.write_bytes(b"")  # empty fake executable

    result = init_ki_system.detect_venv(str(tmp_path))
    assert Path(fake_py).as_posix() == result


@pytest.mark.positive
def test_detect_venv_falls_back_to_sys_executable(tmp_path):
    """detect_venv returns sys.executable when no venv is found."""
    result = init_ki_system.detect_venv(str(tmp_path))
    assert result == Path(sys.executable).as_posix()


# ─── update_gitignore ─────────────────────────────────────────────────────────

@pytest.mark.positive
def test_update_gitignore_creates_rules(tmp_path):
    """update_gitignore writes ki_config.json exclusion rule."""
    know_name = os.environ.get("KNOWLEDGE_DIR_NAME", ".know")
    init_ki_system.update_gitignore(str(tmp_path), know_name)
    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    content = gitignore.read_text(encoding="utf-8")
    assert f"{know_name}/ki_config.json" in content


@pytest.mark.positive
def test_update_gitignore_is_idempotent(tmp_path):
    """Calling update_gitignore twice doesn't duplicate rules."""
    know_name = os.environ.get("KNOWLEDGE_DIR_NAME", ".know")
    init_ki_system.update_gitignore(str(tmp_path), know_name)
    init_ki_system.update_gitignore(str(tmp_path), know_name)
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    count = content.count(f"{know_name}/ki_config.json")
    assert count == 1, f"Rule should appear exactly once, found {count}"


@pytest.mark.positive
def test_update_gitignore_appends_to_existing(tmp_path):
    """update_gitignore preserves existing .gitignore content."""
    existing = tmp_path / ".gitignore"
    existing.write_text("*.pyc\n", encoding="utf-8")
    know_name = os.environ.get("KNOWLEDGE_DIR_NAME", ".know")
    init_ki_system.update_gitignore(str(tmp_path), know_name)
    content = existing.read_text(encoding="utf-8")
    assert "*.pyc" in content
    assert f"{know_name}/ki_config.json" in content


# ─── update_agent_instructions ────────────────────────────────────────────────

@pytest.mark.positive
def test_update_agent_instructions_adds_sections(tmp_path):
    """Sections missing from AGENTS.md are appended."""
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# AGENTS\n\nSome existing content.\n", encoding="utf-8")

    sections = {
        "## Knowledge Items (KI)": "\n## Knowledge Items (KI)\n\nTable goes here.\n"
    }
    result = init_ki_system.update_agent_instructions(str(agents), sections)
    assert result is True
    content = agents.read_text(encoding="utf-8")
    assert "## Knowledge Items (KI)" in content
    assert "Some existing content." in content  # existing content preserved


@pytest.mark.positive
def test_update_agent_instructions_skips_if_present(tmp_path):
    """No modification when all sections already exist."""
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        "# AGENTS\n\n## Knowledge Items (KI)\n\nAlready here.\n",
        encoding="utf-8"
    )
    sections = {"## Knowledge Items (KI)": "## Knowledge Items (KI)\n\nNew content.\n"}
    result = init_ki_system.update_agent_instructions(str(agents), sections)
    assert result is False  # no changes made


@pytest.mark.negative
def test_update_agent_instructions_missing_file(tmp_path):
    """Returns False gracefully when AGENTS.md doesn't exist."""
    result = init_ki_system.update_agent_instructions(
        str(tmp_path / "AGENTS.md"), {"## Foo": "## Foo\nContent.\n"}
    )
    assert result is False
