import os
import pytest
from unittest.mock import patch, MagicMock
from io import StringIO
from analyze_module import analyze_path, format_size

@pytest.mark.positive
def test_format_size():
    assert format_size(500) == "500 B"
    assert format_size(1024) == "1.00 KB"
    assert format_size(1024 * 1024) == "1.00 MB"

@pytest.mark.positive
def test_analyze_path_basic(tmp_path):
    # Создаем временную структуру файлов
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_file = app_dir / "main.py"
    test_file.write_text("print('hello')")
    
    mock_config = {
        "knowledge_items": {
            "KI_main.md": {
                "depends_on": ["app/main.py"]
            }
        }
    }
    
    know_name = os.environ.get("KNOWLEDGE_DIR_NAME", ".know")
    
    # Мокаем ki_utils и корень проекта
    with patch("ki_utils.get_project_root", return_value=str(tmp_path)), \
         patch("ki_utils.get_doc_config", return_value=mock_config), \
         patch("ki_utils.get_knowledge_root", return_value=str(tmp_path / know_name)), \
         patch("sys.stdout", new=StringIO()) as fake_out:
        
        # Создаем файл KI, чтобы плотность могла считаться
        ki_dir = tmp_path / know_name / "knowledge"
        ki_dir.mkdir(parents=True)
        ki_file = ki_dir / "KI_main.md"
        ki_file.write_text("Documentation content") # ~21 bytes
        
        analyze_path("app", recursive=False)
        output = fake_out.getvalue()
        
        assert "### Analysis for: `app`" in output
        assert "| ✅ | `main.py` |" in output
        assert "KI_main.md" in output
        assert "B_code/B_doc" in output

@pytest.mark.positive
def test_analyze_path_recursive(tmp_path):
    # Структура:
    # app/
    #   core/
    #     logic.py
    core_dir = tmp_path / "app" / "core"
    core_dir.mkdir(parents=True)
    logic_file = core_dir / "logic.py"
    logic_file.write_text("pass")
    
    with patch("ki_utils.get_project_root", return_value=str(tmp_path)), \
         patch("ki_utils.get_doc_config", return_value={}), \
         patch("sys.stdout", new=StringIO()) as fake_out:
        
        analyze_path("app", recursive=True)
        output = fake_out.getvalue()
        
        assert "| ❌ | `logic.py` |" in output

@pytest.mark.negative
def test_analyze_path_not_found(tmp_path):
    with patch("ki_utils.get_project_root", return_value=str(tmp_path)), \
         patch("sys.stdout", new=StringIO()) as fake_out:
        
        analyze_path("non_existent_dir")
        output = fake_out.getvalue()
        assert "Error: Path non_existent_dir not found" in output
