"""
test_ki_graph_visualize.py

Unit and integration tests for ki_graph_visualize.py and its MCP tool integration.
"""

import os
import sys
import json
import pytest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "src" / "ki_manager" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import ki_graph_visualize as kgv


@pytest.fixture(autouse=True)
def setup_ki_utils(monkeypatch, tmp_project):
    from conftest import get_know_info
    know_name, know_path, config_path = get_know_info(tmp_project)

    import ki_utils
    monkeypatch.setattr(ki_utils, "_CACHE", {})
    monkeypatch.setattr(sys, "argv", ["prog", "--config", str(config_path)])
    monkeypatch.chdir(tmp_project)

    # Populate doc_config.json with sample KIs
    cfg_file = know_path / "doc_config.json"
    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))

    # Create dummy source files
    src_dir = tmp_project / "src"
    mod_a = src_dir / "module_a" / "alpha.py"
    mod_a.parent.mkdir(parents=True, exist_ok=True)
    mod_a.write_text("import sys\nfrom module_b import beta\n", encoding="utf-8")

    mod_b = src_dir / "module_b" / "beta.py"
    mod_b.parent.mkdir(parents=True, exist_ok=True)
    mod_b.write_text("class Beta: pass\n", encoding="utf-8")

    cfg["coverage_settings"] = {
        "tracked_modules": [["src/module_a", "Module A", 1], ["src/module_b", "Module B", 1]]
    }
    cfg["knowledge_items"] = {
        "KI_alpha.md": {
            "summary": "Alpha Service",
            "depends_on": ["src/module_a/alpha.py"]
        },
        "KI_beta.md": {
            "summary": "Beta Service",
            "depends_on": ["src/module_b/beta.py"]
        }
    }
    cfg_file.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return tmp_project


@pytest.mark.positive
def test_sanitize_id():
    assert kgv.sanitize_id("KI_system.md") == "KI_system_md"
    assert kgv.sanitize_id("123_test") == "id_123_test"
    assert kgv.sanitize_id("path/to/file.py", prefix="f") == "f_path_to_file_py"
    assert kgv.sanitize_id("???", prefix="node") == "node"


@pytest.mark.positive
def test_semantic_mode_output():
    graph = kgv.build_mermaid_graph(mode="semantic", direction="TD")
    assert graph.startswith("```mermaid")
    assert "flowchart TD" in graph
    assert 'subgraph sg_KI_alpha_md ["Alpha Service"]' in graph
    assert 'subgraph sg_KI_beta_md ["Beta Service"]' in graph
    assert "alpha.py" in graph
    assert "beta.py" in graph
    assert graph.endswith("```")


@pytest.mark.positive
def test_ki_only_mode_output():
    graph = kgv.build_mermaid_graph(mode="ki-only", direction="LR")
    assert "flowchart LR" in graph
    assert 'ki_KI_alpha_md["Alpha Service<br/>(1 files)"]' in graph
    assert 'ki_KI_beta_md["Beta Service<br/>(1 files)"]' in graph
    assert "subgraph" not in graph


@pytest.mark.positive
def test_coverage_mode_output(tmp_project):
    # Create an unmapped file
    unmapped_file = tmp_project / "src" / "extra_unmapped.py"
    unmapped_file.write_text("# unmapped\n", encoding="utf-8")

    graph = kgv.build_mermaid_graph(mode="coverage")
    assert "sg_unmapped" in graph
    assert "⚠️ Unmapped Files" in graph
    assert "extra_unmapped.py" in graph


@pytest.mark.positive
def test_ki_filter():
    graph = kgv.build_mermaid_graph(mode="ki-only", ki_filter="KI_alpha")
    assert "Alpha Service" in graph

    graph_missing = kgv.build_mermaid_graph(mode="ki-only", ki_filter="NonExistent")
    assert "KI 'NonExistent' not found" in graph_missing


@pytest.mark.positive
def test_empty_config(monkeypatch, tmp_project):
    from conftest import get_know_info
    _, know_path, _ = get_know_info(tmp_project)
    cfg_file = know_path / "doc_config.json"
    cfg = {"knowledge_items": {}}
    cfg_file.write_text(json.dumps(cfg), encoding="utf-8")

    graph = kgv.build_mermaid_graph()
    assert "No Knowledge Items registered" in graph


@pytest.mark.positive
def test_server_dispatch_tool_call(tmp_project):
    import server
    res = server.handle_tool_call("ki_graph_visualize", {"mode": "ki-only"})
    assert isinstance(res, dict)
    assert "content" in res
    assert "```mermaid" in res["content"][0]["text"]
