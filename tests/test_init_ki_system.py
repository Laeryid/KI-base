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


# ─── setup_gitignore ─────────────────────────────────────────────────────────

@pytest.mark.positive
def test_setup_gitignore_project_mode(tmp_path):
    """setup_gitignore in project mode ignores scripts/ and tests/."""
    init_ki_system.setup_gitignore(str(tmp_path), is_master=False)
    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    content = gitignore.read_text(encoding="utf-8")
    assert "scripts/" in content
    assert "tests/" in content
    assert "!knowledge/" in content
    assert "KI_base: Project mode" in content


@pytest.mark.positive
def test_setup_gitignore_master_mode(tmp_path):
    """setup_gitignore in master mode allows everything (!scripts/ etc.)."""
    init_ki_system.setup_gitignore(str(tmp_path), is_master=True)
    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    content = gitignore.read_text(encoding="utf-8")
    assert "!scripts/" in content
    assert "!tests/" in content
    assert "!knowledge/" in content
    assert "KI_base: Master repository mode" in content


@pytest.mark.positive
def test_init_ki_system_calls_setup_gitignore(tmp_path, monkeypatch):
    """init_ki_system calls setup_gitignore during execution."""
    know_dir = tmp_path / ".know"
    know_dir.mkdir()
    (know_dir / "doc_config.json").write_text("{}", encoding="utf-8")
    
    # Mock find_knowledge_root to return our tmp .know
    monkeypatch.setattr(init_ki_system, "find_knowledge_root", lambda: know_dir)
    
    # Run with --master
    sys_argv = ["script.py", "--master", f"--project-root={tmp_path}"]
    monkeypatch.setattr("sys.argv", sys_argv)
    
    init_ki_system.init_ki_system()
    
    gitignore = know_dir / ".gitignore"
    assert gitignore.exists()
    assert "Master repository mode" in gitignore.read_text(encoding="utf-8")


# update_agent_instructions was removed in favor of MCP delivery
