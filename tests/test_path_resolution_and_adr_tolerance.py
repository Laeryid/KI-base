import os
import json
import pytest
from ki_manager.server import handle_tool_call, resolve_know_path
import ki_manager.scripts.ki_utils as ki_utils


@pytest.fixture
def mock_ki_env(tmp_path, monkeypatch):
    """Sets up a complete isolated workspace with .ki-base, knowledge/ and decisions/."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    jail = ws / ".ki-base"
    jail.mkdir()
    know_dir = jail / "knowledge"
    know_dir.mkdir()
    dec_dir = ws / "decisions"
    dec_dir.mkdir()

    # Create KI file inside knowledge/
    ki_file = know_dir / "KI_data_persistence.md"
    ki_file.write_text("# Data Persistence\nInitial content\n", encoding="utf-8")

    # Create ADR file inside decisions/
    adr_file = dec_dir / "002_node_status_queue_and_ui_feedback.md"
    adr_file.write_text("# ADR 002: Node Status Queue\n\n## Context\nQueue details\n", encoding="utf-8")

    # Mock ki_utils paths and server helpers
    import ki_manager.server as server
    monkeypatch.setattr(server, "get_jail_dir", lambda: str(jail))
    monkeypatch.setattr(server, "get_project_root", lambda: str(ws))
    monkeypatch.setattr(server.ki_utils, "ACTIVE_WORKSPACE_PATH", str(ws))
    monkeypatch.setattr(server.ki_utils, "get_project_root", lambda: str(ws))
    monkeypatch.setattr(server.ki_utils, "get_knowledge_root", lambda: str(jail))
    monkeypatch.setattr(ki_utils, "ACTIVE_WORKSPACE_PATH", str(ws))
    monkeypatch.setattr(ki_utils, "get_project_root", lambda: str(ws))
    monkeypatch.setattr(ki_utils, "get_knowledge_root", lambda: str(jail))

    # Setup doc_config.json
    doc_config = {
        "knowledge_items": {
            "KI_data_persistence.md": {
                "summary": "Data persistence layer documentation."
            },
            "ADR_002_node_status_queue_and_ui_feedback.md": {
                "summary": "ADR 002 for Node Status Queue"
            }
        }
    }
    doc_cfg_path = jail / "doc_config.json"
    with open(doc_cfg_path, "w", encoding="utf-8") as f:
        json.dump(doc_config, f, indent=2)

    monkeypatch.setattr(server.ki_utils, "get_doc_config_path", lambda: str(doc_cfg_path))
    monkeypatch.setattr(server.ki_utils, "get_doc_config", lambda: json.loads(doc_cfg_path.read_text(encoding="utf-8")))
    monkeypatch.setattr(ki_utils, "get_doc_config_path", lambda: str(doc_cfg_path))
    monkeypatch.setattr(ki_utils, "get_doc_config", lambda: json.loads(doc_cfg_path.read_text(encoding="utf-8")))

    return {
        "ws": str(ws),
        "jail": str(jail),
        "know_dir": str(know_dir),
        "dec_dir": str(dec_dir),
        "ki_file": str(ki_file),
        "adr_file": str(adr_file),
    }


def test_resolve_know_path_flat_and_nested(mock_ki_env):
    """Test resolving KI file with flat name and with knowledge/ prefix."""
    res_flat = resolve_know_path("KI_data_persistence.md", must_exist=True)
    assert res_flat == mock_ki_env["ki_file"]

    res_nested = resolve_know_path("knowledge/KI_data_persistence.md", must_exist=True)
    assert res_nested == mock_ki_env["ki_file"]


def test_resolve_know_path_adr_prefix_tolerance(mock_ki_env):
    """Test resolving ADR with and without ADR_ prefix, and by ADR numeric ID."""
    res_with_prefix = resolve_know_path("ADR_002_node_status_queue_and_ui_feedback.md", must_exist=True)
    assert res_with_prefix == mock_ki_env["adr_file"]

    res_without_prefix = resolve_know_path("002_node_status_queue_and_ui_feedback.md", must_exist=True)
    assert res_without_prefix == mock_ki_env["adr_file"]

    # Resolution by ADR ID
    res_by_id = resolve_know_path("002", must_exist=True)
    assert res_by_id == mock_ki_env["adr_file"]


def test_resolve_know_path_write_existing_and_new(mock_ki_env):
    """Test resolving write paths for existing and new KI files."""
    # Existing file resolves to existing location in knowledge/
    res_existing = resolve_know_path("KI_data_persistence.md", is_write=True, must_exist=False)
    assert res_existing == mock_ki_env["ki_file"]

    # New KI file defaults to knowledge/ subfolder
    res_new = resolve_know_path("KI_new_service.md", is_write=True, must_exist=False)
    assert res_new == os.path.join(mock_ki_env["know_dir"], "KI_new_service.md")


def test_read_and_edit_know_file_cascade(mock_ki_env):
    """Test read_know_file and edit_know_file without specifying knowledge/ folder."""
    # 1. read_know_file with flat name
    content = handle_tool_call("read_know_file", {"rel_path": "KI_data_persistence.md"})
    assert "# Data Persistence" in content

    # 2. edit_know_file with flat name
    edit_res = handle_tool_call("edit_know_file", {
        "rel_path": "KI_data_persistence.md",
        "old_text": "Initial content",
        "new_text": "Updated content via flat name"
    })
    assert edit_res == "File edited."

    # Verify content on disk
    with open(mock_ki_env["ki_file"], "r", encoding="utf-8") as f:
        updated = f.read()
    assert "Updated content via flat name" in updated


def test_write_know_file_flat_name(mock_ki_env):
    """Test write_know_file creates new file inside knowledge/ folder."""
    res = handle_tool_call("write_know_file", {
        "rel_path": "KI_created_via_tool.md",
        "content": "# New KI content\n"
    })
    assert res == "File written."

    expected_path = os.path.join(mock_ki_env["know_dir"], "KI_created_via_tool.md")
    assert os.path.exists(expected_path)
    with open(expected_path, "r", encoding="utf-8") as f:
        assert f.read() == "# New KI content\n"


def test_ki_read_and_edit_adr_with_prefix(mock_ki_env):
    """Test ki_read and edit_know_file on ADR with ADR_ prefix."""
    # 1. ki_read
    read_res = handle_tool_call("ki_read", {
        "rel_path": "ADR_002_node_status_queue_and_ui_feedback.md"
    })
    assert "# ADR 002: Node Status Queue" in read_res

    # 2. edit_know_file
    edit_res = handle_tool_call("edit_know_file", {
        "rel_path": "ADR_002_node_status_queue_and_ui_feedback.md",
        "old_text": "Queue details",
        "new_text": "Updated queue details"
    })
    assert edit_res == "File edited."

    with open(mock_ki_env["adr_file"], "r", encoding="utf-8") as f:
        assert "Updated queue details" in f.read()


def test_get_ki_list_table_resolves_exact_names(mock_ki_env):
    """Test get_ki_list_table converts mismatched ADR_ key to actual filename on disk."""
    table = ki_utils.get_ki_list_table()
    assert "`002_node_status_queue_and_ui_feedback.md`" in table
    assert "`ADR_002_node_status_queue_and_ui_feedback.md`" not in table


def test_ki_instructions_knowledge_items_includes_adr(mock_ki_env):
    """Test ki_instructions(document='knowledge-items') returns both KI and ADR tables."""
    res = handle_tool_call("ki_instructions", {"document": "knowledge-items"})
    assert "Knowledge Items for this project:" in res
    assert "Architecture Decision Records (ADRs):" in res
    assert "002_node_status_queue_and_ui_feedback.md" in res
