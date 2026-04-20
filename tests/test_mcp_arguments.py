import pytest
from unittest.mock import patch, MagicMock
from knowledge_mcp import run_script, tool_analyze_module

@pytest.mark.positive
def test_run_script_with_args():
    # Мокаем геттеры, чтобы пройти проверку безопасности
    with patch("knowledge_mcp.get_jail_dir", return_value="/fake/jail"), \
         patch("os.path.exists", return_value=True), \
         patch("ki_utils.get_python_exe", return_value="python"), \
         patch("ki_utils.get_project_root", return_value="/fake/root"), \
         patch("subprocess.run") as mock_run:
        
        mock_run.return_value = MagicMock(stdout="success", stderr="")
        
        result = run_script("test_script.py", ["--arg1", "val1"])
        
        # Проверяем, что в subprocess.run ушли правильные аргументы
        mock_run.assert_called_once()
        args_passed = mock_run.call_args[0][0]
        assert "test_script.py" in args_passed[1]
        assert "--arg1" in args_passed
        assert "val1" in args_passed
        assert result["content"][0]["text"] == "success"

@pytest.mark.positive
def test_tool_analyze_module_mapping():
    # Проверяем, как параметры MCP превращаются в аргументы командной строки
    with patch("knowledge_mcp.run_script") as mock_run_script:
        args = {"path": "app/core", "recursive": True}
        tool_analyze_module(args)
        
        mock_run_script.assert_called_once_with("analyze_module.py", ["app/core", "--recursive"])

@pytest.mark.positive
def test_tool_analyze_module_no_recursive():
    with patch("knowledge_mcp.run_script") as mock_run_script:
        args = {"path": "ui"}
        tool_analyze_module(args)
        
        mock_run_script.assert_called_once_with("analyze_module.py", ["ui"])
