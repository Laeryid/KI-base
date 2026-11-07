import os
import json
import pytest
from unittest.mock import patch, mock_open
from pathlib import Path

# Импортируем тестируемый скрипт
from ki_manager.scripts import generate_ki_scaffolds
from ki_manager.scripts.generate_ki_scaffolds import (
    extract_symbols,
    build_scaffold_content,
    ki_filename_from_module,
    scan_module,
    print_scaffold_status
)


def test_ki_filename_from_module():
    assert ki_filename_from_module("src/auth") == "KI_src_auth.md"
    assert ki_filename_from_module("/src/auth/tests/") == "KI_src_auth_tests.md"


def test_extract_symbols_python(tmp_path):
    py_file = tmp_path / "test.py"
    py_file.write_text(
        "class MyClass:\n    pass\n\n"
        "def my_function():\n    pass\n\n"
        "def __private():\n    pass\n",
        encoding="utf-8"
    )
    symbols = extract_symbols(str(py_file))
    assert "MyClass" in symbols
    assert "my_function" in symbols
    assert "__private" not in symbols


def test_extract_symbols_typescript(tmp_path):
    ts_file = tmp_path / "test.ts"
    ts_file.write_text(
        "export class AuthController {}\n"
        "export const myConst = 1;\n"
        "export async function login() {}\n"
        "function internal() {}\n",
        encoding="utf-8"
    )
    symbols = extract_symbols(str(ts_file))
    assert "AuthController" in symbols
    assert "myConst" in symbols
    assert "login" in symbols
    assert "internal" not in symbols


def test_extract_symbols_golang(tmp_path):
    go_file = tmp_path / "test.go"
    go_file.write_text(
        "package main\n\n"
        "type Server struct {}\n"
        "func (s *Server) Handle() {}\n"
        "func GlobalFunc() {}\n",
        encoding="utf-8"
    )
    symbols = extract_symbols(str(go_file))
    assert "Server" in symbols
    assert "Handle" in symbols
    assert "GlobalFunc" in symbols


def test_build_scaffold_content():
    file_infos = [
        {
            "rel_path": "src/api/main.py",
            "size": 1024,
            "symbols": ["ApiServer", "start"]
        },
        {
            "rel_path": "src/api/config.json",
            "size": 512,
            "symbols": []
        }
    ]
    content = build_scaffold_content("src/api", "API Module", file_infos)
    
    assert "<!-- scaffold: true -->" in content
    assert "# KI: API Module" in content
    assert "`ApiServer`" in content
    assert "`start`" in content
    assert "`src/api/main.py`" in content
    assert "0.5 KB" in content # Для файла без символов


@patch("sys.stdout")
def test_print_scaffold_status(mock_stdout, tmp_path):
    # Подготавливаем фейковую файловую систему
    ki_dir = tmp_path / "knowledge"
    ki_dir.mkdir()
    
    pending_ki = ki_dir / "KI_pending.md"
    pending_ki.write_text(
        "<!-- scaffold: true -->\n"
        "<!-- last_verified: 2026-07-20 -->\n"
        "# KI: Pending Module\n",
        encoding="utf-8"
    )
    
    enriched_ki = ki_dir / "KI_enriched.md"
    enriched_ki.write_text(
        "<!-- scaffold: enriched -->\n"
        "<!-- last_verified: 2026-07-21 -->\n"
        "# KI: Enriched Module\n",
        encoding="utf-8"
    )
    
    regular_ki = ki_dir / "KI_regular.md"
    regular_ki.write_text(
        "<!-- last_verified: 2026-07-22 -->\n"
        "# KI: Regular Module\n",
        encoding="utf-8"
    )

    with patch("ki_manager.scripts.generate_ki_scaffolds.ki_utils.get_knowledge_root", return_value=str(tmp_path)):
        import sys
        import io
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        print_scaffold_status()
        
        sys.stdout = sys.__stdout__
        
        output = captured_output.getvalue()
        assert "KI_pending.md" in output
        assert "🚧 Pending (True)" in output
        assert "2026-07-20" in output
        assert "Pending Module" in output
        
        assert "KI_enriched.md" in output
        assert "✅ Enriched" in output
        
        assert "KI_regular.md" in output
        assert "Complete" in output
        
        assert "1 pending enrichment" in output
        assert "1 enriched scaffolds" in output


def test_ast_pre_enrichment(tmp_path):
    # Test rich metadata extraction with docstrings and env vars
    mod_dir = tmp_path / "src" / "worker"
    mod_dir.mkdir(parents=True)
    py_file = mod_dir / "tasks.py"
    py_file.write_text(
        '"""Task processing worker module."""\n'
        'import os\n\n'
        'class TaskRunner:\n'
        '    """Manages execution queue."""\n'
        '    pass\n\n'
        'def execute_job(job_id: str, retries: int = 3) -> bool:\n'
        '    """Run a single background job."""\n'
        '    token = os.getenv("API_TOKEN")\n'
        '    return True\n',
        encoding="utf-8"
    )

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_tasks.py"
    test_file.write_text("def test_dummy(): pass\n", encoding="utf-8")

    file_infos = scan_module(str(tmp_path), "src/worker")
    assert len(file_infos) == 1
    info = file_infos[0]
    assert info["module_doc"] == "Task processing worker module."
    assert "TaskRunner" in info["symbols"]
    assert "execute_job" in info["symbols"]
    assert "API_TOKEN" in info["env_vars"]

    content = build_scaffold_content("src/worker", "Worker Module", file_infos, project_root=str(tmp_path))
    assert "Task processing worker module." in content
    assert "Manages execution queue." in content
    assert "Run a single background job." in content
    assert "API_TOKEN" in content
    assert "test_tasks.py" in content
    assert "## Entry Points & Public API" in content
    assert "## Testing & Verification" in content


def test_flexible_tracked_modules_in_scaffolds():
    """String and dict entries in tracked_modules do not crash get_uncovered_modules."""
    from ki_manager.scripts.generate_ki_scaffolds import get_uncovered_modules
    doc_cfg = {
        "coverage_settings": {
            "tracked_modules": ["src/alpha", ["src/beta"], {"path": "src/gamma", "label": "Gamma", "importance": 7}]
        },
        "knowledge_items": {
            "KI_src_alpha.md": {
                "depends_on": ["src/alpha/main.py"]
            }
        }
    }
    uncovered = get_uncovered_modules(doc_cfg)
    assert len(uncovered) == 2
    paths = [u[0] for u in uncovered]
    assert "src/beta" in paths
    assert "src/gamma" in paths


def test_scaffold_modules_filter_on_empty_tracked(tmp_path, monkeypatch):
    """Passing modules_filter scaffolds module even if tracked_modules is empty, and registers it."""
    from ki_manager.scripts.generate_ki_scaffolds import generate_scaffolds
    from ki_manager.scripts import ki_utils

    # Setup mini project
    src_dir = tmp_path / "rich"
    src_dir.mkdir()
    (src_dir / "core.py").write_text("class RichCore:\n    pass\n", encoding="utf-8")

    ki_base = tmp_path / ".ki-base"
    ki_base.mkdir()
    ki_config = {
        "project_name": "test_proj",
        "paths": {"knowledge_root": ".ki-base", "project_root": "."}
    }
    (ki_base / "ki_config.json").write_text(json.dumps(ki_config), encoding="utf-8")

    doc_cfg = {
        "coverage_settings": {"tracked_modules": []},
        "knowledge_items": {}
    }
    (ki_base / "doc_config.json").write_text(json.dumps(doc_cfg), encoding="utf-8")

    monkeypatch.setattr(ki_utils, "ACTIVE_WORKSPACE_PATH", str(tmp_path))
    monkeypatch.setattr(ki_utils, "_CACHE", {})
    monkeypatch.chdir(tmp_path)

    generate_scaffolds(modules_filter=["rich"])

    # Check KI file was created
    ki_file = ki_base / "knowledge" / "KI_rich.md"
    assert ki_file.exists()
    content = ki_file.read_text(encoding="utf-8")
    assert "RichCore" in content

    # Check doc_config was updated with tracked_module
    updated_cfg = json.loads((ki_base / "doc_config.json").read_text(encoding="utf-8"))
    assert "KI_rich.md" in updated_cfg["knowledge_items"]
    assert any(m[0] == "rich" for m in updated_cfg["coverage_settings"]["tracked_modules"])


def test_empty_tracked_modules_message(tmp_path, monkeypatch, capsys):
    """When tracked_modules is empty and no modules_filter, clear warning is printed."""
    from ki_manager.scripts.generate_ki_scaffolds import generate_scaffolds
    from ki_manager.scripts import ki_utils

    ki_base = tmp_path / ".ki-base"
    ki_base.mkdir()
    ki_config = {
        "project_name": "test_proj",
        "paths": {"knowledge_root": ".ki-base", "project_root": "."}
    }
    (ki_base / "ki_config.json").write_text(json.dumps(ki_config), encoding="utf-8")

    doc_cfg = {"coverage_settings": {"tracked_modules": []}, "knowledge_items": {}}
    (ki_base / "doc_config.json").write_text(json.dumps(doc_cfg), encoding="utf-8")

    monkeypatch.setattr(ki_utils, "ACTIVE_WORKSPACE_PATH", str(tmp_path))
    monkeypatch.setattr(ki_utils, "_CACHE", {})
    monkeypatch.chdir(tmp_path)

    generate_scaffolds()

    captured = capsys.readouterr().out
    assert "[!] No tracked modules configured in doc_config.json." in captured

