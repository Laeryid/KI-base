import os
import pytest
from pathlib import Path
from ki_manager.tools.facade import render_instruction
from ki_manager import server
from ki_manager.cli import install_skills


def test_render_instruction_basic():
    template = (
        "Start.\n"
        "<!-- if-compact -->\n"
        "`ki_call(tool=\"test\")`\n"
        "<!-- else-compact -->\n"
        "`test()`\n"
        "<!-- /if-compact -->\n"
        "End in {{KI_DIR}}."
    )
    compact_res = render_instruction(template, tool_mode="compact", ki_dir="my_know")
    assert '`ki_call(tool="test")`' in compact_res
    assert '`test()`' not in compact_res
    assert "End in my_know." in compact_res
    assert "<!-- if-compact -->" not in compact_res

    full_res = render_instruction(template, tool_mode="full", ki_dir="my_know")
    assert '`test()`' in full_res
    assert 'ki_call' not in full_res
    assert "End in my_know." in full_res
    assert "<!-- if-compact -->" not in full_res


def test_render_all_bundled_workflows():
    workflows_dir = Path(__file__).parent.parent / "src" / "ki_manager" / "workflows"
    wf_files = list(workflows_dir.glob("*.md"))
    assert len(wf_files) >= 4

    for wf in wf_files:
        raw = wf.read_text(encoding="utf-8")

        # Compact mode
        rendered_compact = render_instruction(raw, tool_mode="compact", ki_dir=".ki-base")
        assert "<!-- if-compact -->" not in rendered_compact
        assert "<!-- else-compact -->" not in rendered_compact
        assert "<!-- /if-compact -->" not in rendered_compact
        assert "allowed-tools: ki_instructions ki_read ki_search ki_tools ki_call ki_mutate" in rendered_compact

        # Full mode
        rendered_full = render_instruction(raw, tool_mode="full", ki_dir=".ki-base")
        assert "<!-- if-compact -->" not in rendered_full
        assert "<!-- else-compact -->" not in rendered_full
        assert "<!-- /if-compact -->" not in rendered_full
        assert "ki_call ki_mutate" not in rendered_full


def test_server_ki_instructions_mode_switching(monkeypatch):
    # Test compact mode rendering
    monkeypatch.setattr(server, "CURRENT_TOOL_MODE", "compact")
    doc_compact = server.handle_tool_call("ki_instructions", {"document": "create-adr"})
    assert 'ki_mutate(tool="create_adr"' in doc_compact
    assert "create_adr(" not in doc_compact.replace('tool="create_adr"', '')

    overview_compact = server.handle_tool_call("ki_instructions", {"document": "overview"})
    assert "ki_call(tool=" in overview_compact

    # Test full mode rendering
    monkeypatch.setattr(server, "CURRENT_TOOL_MODE", "full")
    doc_full = server.handle_tool_call("ki_instructions", {"document": "create-adr"})
    assert 'create_adr(title=' in doc_full
    assert "ki_mutate" not in doc_full

    overview_full = server.handle_tool_call("ki_instructions", {"document": "overview"})
    assert "ki_call" not in overview_full


def test_cli_install_skills_with_mode(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    # Install in compact mode
    install_skills(["--path", str(skills_dir), "--tool-mode", "compact"])
    scaffold_skill = skills_dir / "ki-manager-scaffold-knowledge" / "SKILL.md"
    assert scaffold_skill.exists()
    content = scaffold_skill.read_text(encoding="utf-8")
    assert "ki_call(tool=" in content
    assert "<!-- if-compact -->" not in content


def test_instructions_parity_across_all_access_methods(monkeypatch):
    for mode in ("compact", "full"):
        monkeypatch.setattr(server, "CURRENT_TOOL_MODE", mode)
        overview_text = server.handle_tool_call("ki_instructions", {"document": "overview"})

        know_name = os.path.basename(server.ki_utils.get_knowledge_root()) or ".ki-base"
        rendered = render_instruction(server.GLOBAL_INSTRUCTIONS, tool_mode=mode, ki_dir=know_name)
        assert overview_text == rendered

        if mode == "compact":
            assert 'ki_call' in overview_text
            assert 'ki_mutate' in overview_text
            assert 'ki_search' in overview_text
            assert 'ki_read' in overview_text
            assert 'ki_tools' in overview_text
        else:
            assert 'run `audit_coverage` via MCP' in overview_text
            assert 'Use `git_checkpoint` to save' in overview_text
            assert 'ki_call' not in overview_text

