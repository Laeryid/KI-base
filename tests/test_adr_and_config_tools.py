"""
test_adr_and_config_tools.py

Tests for:
- add_ki_to_config tool and CLI
- edit_doc_config tool (set, append, delete for tracked_modules, artifacts, coverage_settings)
- create_adr tool with automatic prefix incrementing and registration
- get_adr_table and ADR parsing
- sync_agents_md with ki_config.json enable/disable setting
- scaffold.migrate_project preserving AGENTS.md
- Negative tests for invalid inputs, missing keys, and unauthorized jail.
"""

import os
import sys
import json
import pytest
from pathlib import Path

# Add src and scripts to sys.path
SRC_DIR = Path(__file__).parent.parent / "src"
SCRIPTS_DIR = SRC_DIR / "ki_manager" / "scripts"
TOOLS_DIR = SRC_DIR / "ki_manager" / "tools"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TOOLS_DIR))

import ki_utils
import server
import sync_agents_md
import add_ki_to_config
import scaffold


@pytest.fixture
def mock_ki_project(tmp_path, monkeypatch):
    """Sets up a complete isolated ki project structure."""
    proj_dir = tmp_path / "my_project"
    proj_dir.mkdir()
    ki_base = proj_dir / ".ki-base"
    ki_base.mkdir()
    knowledge_dir = ki_base / "knowledge"
    knowledge_dir.mkdir()
    decisions_dir = ki_base / "decisions"
    decisions_dir.mkdir()

    ki_config = {
        "project_name": "my_project",
        "sync_agents_md": True,
        "paths": {
            "knowledge_root": ".ki-base",
            "project_root": ".."
        }
    }
    (ki_base / "ki_config.json").write_text(json.dumps(ki_config, indent=2), encoding="utf-8")

    doc_config = {
        "project_name": "my_project",
        "coverage_settings": {
            "tracked_modules": [
                ["core", "Core Module", 5]
            ]
        },
        "artifacts": {
            "README.md": {
                "description": "Project readme",
                "depends_on": [".ki-base/"]
            }
        },
        "knowledge_items": {
            "_OVERVIEW.ki.md": {
                "summary": "Project overview",
                "covers": ["Core"],
                "depends_on": []
            }
        }
    }
    (ki_base / "doc_config.json").write_text(json.dumps(doc_config, indent=2), encoding="utf-8")

    agents_content = (
        "# AGENTS.md\n\n"
        "## Knowledge Items\n\n"
        "| File | Topic / Summary |\n"
        "|------|-----------------|\n"
        "| `_OVERVIEW.ki.md` | Initial overview |\n\n"
        "## Key Files\n"
        "- file1\n"
    )
    (proj_dir / "AGENTS.md").write_text(agents_content, encoding="utf-8")

    # Set active workspace
    monkeypatch.setattr(ki_utils, "ACTIVE_WORKSPACE_PATH", str(proj_dir))
    return proj_dir, ki_base


# ─── 1. add_ki_to_config Tests ───

def test_add_ki_to_config_success(mock_ki_project):
    proj_dir, ki_base = mock_ki_project
    res = server.handle_tool_call("add_ki_to_config", {
        "ki_name": "KI_auth.md",
        "description": "Authentication module documentation",
        "covers": ["auth"],
        "depends_on": ["src/auth.py"],
        "summary": "Auth docs"
    })

    assert "content" in res
    assert "successfully registered" in res["content"][0]["text"]

    doc_cfg = ki_utils.get_doc_config()
    assert "KI_auth.md" in doc_cfg["knowledge_items"]
    entry = doc_cfg["knowledge_items"]["KI_auth.md"]
    assert entry["description"] == "Authentication module documentation"
    assert entry["summary"] == "Auth docs"
    assert entry["covers"] == ["auth"]
    assert entry["depends_on"] == ["src/auth.py"]


def test_add_ki_to_config_update_existing(mock_ki_project):
    mock_ki_project
    server.handle_tool_call("add_ki_to_config", {
        "ki_name": "_OVERVIEW.ki.md",
        "description": "Updated overview description",
        "covers": ["Core", "Extra"],
        "depends_on": ["main.py"]
    })

    doc_cfg = ki_utils.get_doc_config()
    entry = doc_cfg["knowledge_items"]["_OVERVIEW.ki.md"]
    assert entry["description"] == "Updated overview description"
    assert entry["summary"] == "Project overview"  # preserved existing summary
    assert entry["covers"] == ["Core", "Extra"]


def test_add_ki_to_config_negative_missing_args(mock_ki_project):
    mock_ki_project
    res = server.handle_tool_call("add_ki_to_config", {
        "ki_name": "",
        "description": "test"
    })
    assert res.get("isError") is True
    assert "required" in res["content"][0]["text"]


def test_add_ki_to_config_negative_invalid_types(mock_ki_project):
    mock_ki_project
    res = server.handle_tool_call("add_ki_to_config", {
        "ki_name": "KI_test.md",
        "description": "test",
        "covers": "not-a-list"
    })
    assert res.get("isError") is True
    assert "must be arrays" in res["content"][0]["text"]


# ─── 2. edit_doc_config Tests ───

def test_edit_doc_config_tracked_modules_append_and_delete(mock_ki_project):
    mock_ki_project
    # Append
    res = server.handle_tool_call("edit_doc_config", {
        "section": "tracked_modules",
        "action": "append",
        "value": ["api", "API Subsystem", 10]
    })
    assert "Appended module" in res["content"][0]["text"]

    doc_cfg = ki_utils.get_doc_config()
    tracked = doc_cfg["coverage_settings"]["tracked_modules"]
    assert len(tracked) == 2
    assert tracked[1] == ["api", "API Subsystem", 10]

    # Delete by module key
    res_del = server.handle_tool_call("edit_doc_config", {
        "section": "tracked_modules",
        "action": "delete",
        "key": "api"
    })
    assert "Deleted tracked_module 'api'" in res_del["content"][0]["text"]
    doc_cfg2 = ki_utils.get_doc_config()
    assert len(doc_cfg2["coverage_settings"]["tracked_modules"]) == 1


def test_edit_doc_config_artifacts_operations(mock_ki_project):
    mock_ki_project
    # Set artifact
    res_set = server.handle_tool_call("edit_doc_config", {
        "section": "artifacts",
        "action": "set",
        "key": "CHANGELOG.md",
        "value": {"description": "Changelog", "depends_on": []}
    })
    assert "Set artifact 'CHANGELOG.md'" in res_set["content"][0]["text"]

    # Append dependency
    res_app = server.handle_tool_call("edit_doc_config", {
        "section": "artifacts",
        "action": "append",
        "key": "CHANGELOG.md",
        "value": ".ki-base/decisions/"
    })
    assert "Appended dependencies" in res_app["content"][0]["text"]
    doc_cfg = ki_utils.get_doc_config()
    assert ".ki-base/decisions/" in doc_cfg["artifacts"]["CHANGELOG.md"]["depends_on"]

    # Delete artifact
    res_del = server.handle_tool_call("edit_doc_config", {
        "section": "artifacts",
        "action": "delete",
        "key": "CHANGELOG.md"
    })
    assert "Deleted artifact 'CHANGELOG.md'" in res_del["content"][0]["text"]
    assert "CHANGELOG.md" not in ki_utils.get_doc_config()["artifacts"]


def test_edit_doc_config_coverage_settings_operations(mock_ki_project):
    mock_ki_project
    res_set = server.handle_tool_call("edit_doc_config", {
        "section": "coverage_settings",
        "action": "set",
        "key": "thresholds",
        "value": {"density": 80.0}
    })
    assert "Set coverage_settings['thresholds']" in res_set["content"][0]["text"]
    doc_cfg = ki_utils.get_doc_config()
    assert doc_cfg["coverage_settings"]["thresholds"]["density"] == 80.0

    res_del = server.handle_tool_call("edit_doc_config", {
        "section": "coverage_settings",
        "action": "delete",
        "key": "thresholds"
    })
    assert "Deleted coverage_settings['thresholds']" in res_del["content"][0]["text"]
    assert "thresholds" not in ki_utils.get_doc_config()["coverage_settings"]


def test_edit_doc_config_negative_invalid_section(mock_ki_project):
    mock_ki_project
    res = server.handle_tool_call("edit_doc_config", {
        "section": "unsupported_section",
        "action": "set",
        "key": "x",
        "value": 1
    })
    assert res.get("isError") is True
    assert "not allowed" in res["content"][0]["text"]


def test_edit_doc_config_negative_invalid_action(mock_ki_project):
    mock_ki_project
    res = server.handle_tool_call("edit_doc_config", {
        "section": "artifacts",
        "action": "drop_table",
        "key": "x"
    })
    assert res.get("isError") is True
    assert "action 'drop_table' is not supported" in res["content"][0]["text"]


def test_edit_doc_config_negative_missing_key_for_delete(mock_ki_project):
    mock_ki_project
    res = server.handle_tool_call("edit_doc_config", {
        "section": "artifacts",
        "action": "delete",
        "key": "non_existent_file.md"
    })
    assert res.get("isError") is True
    assert "not found" in res["content"][0]["text"]


# ─── 3. create_adr & ADR Parsing Tests ───

def test_create_adr_and_auto_increment(mock_ki_project):
    proj_dir, ki_base = mock_ki_project

    # First ADR
    res1 = server.handle_tool_call("create_adr", {
        "title": "Use SQLite Storage",
        "status": "Accepted",
        "context": "File-based storage lacks concurrency.",
        "decision": "Adopt SQLite with WAL mode.",
        "consequences": "Faster queries, requires sqlite driver.",
        "topic_name": "sqlite_storage"
    })
    assert "Created ADR 001_sqlite_storage.md" in res1["content"][0]["text"]

    decisions_dir = ki_base / "decisions"
    adr1_path = decisions_dir / "001_sqlite_storage.md"
    assert adr1_path.exists()
    content1 = adr1_path.read_text(encoding="utf-8")
    assert "# ADR 001: Use SQLite Storage" in content1
    assert "Adopt SQLite with WAL mode." in content1

    # Second ADR: prefix should increment to 002
    res2 = server.handle_tool_call("create_adr", {
        "title": "Migrate Transport to WebSockets",
        "status": "Proposed",
        "context": "Polling is too slow.",
        "decision": "Use WebSockets.",
        "consequences": "Persistent connections required.",
        "topic_name": "websocket_transport"
    })
    assert "Created ADR 002_websocket_transport.md" in res2["content"][0]["text"]
    adr2_path = decisions_dir / "002_websocket_transport.md"
    assert adr2_path.exists()

    # Check registered in doc_config.json
    doc_cfg = ki_utils.get_doc_config()
    registered_keys = list(doc_cfg["knowledge_items"].keys())
    assert any("001_sqlite_storage.md" in k for k in registered_keys)
    assert any("002_websocket_transport.md" in k for k in registered_keys)

    # Check ADR table formatting
    adr_table = ki_utils.get_adr_table()
    assert "| 001 | Use SQLite Storage | Accepted |" in adr_table
    assert "| 002 | Migrate Transport to WebSockets | Proposed |" in adr_table


def test_create_adr_negative_missing_title(mock_ki_project):
    mock_ki_project
    res = server.handle_tool_call("create_adr", {
        "title": "",
        "topic_name": "fail"
    })
    assert res.get("isError") is True
    assert "required" in res["content"][0]["text"]


# ─── 4. sync_agents_md Tests ───

def test_sync_agents_md_enabled(mock_ki_project):
    proj_dir, ki_base = mock_ki_project

    # Create an ADR so we have both KI and ADR tables
    server.handle_tool_call("create_adr", {
        "title": "Adopt Event Bus",
        "context": "Decoupling needed.",
        "decision": "Use simple pub-sub.",
        "consequences": "Decoupled logic.",
        "topic_name": "event_bus"
    })

    res = server.handle_tool_call("sync_agents_md", {})
    assert "successfully synchronized" in res["content"][0]["text"] or "up to date" in res["content"][0]["text"]

    agents_content = (proj_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert "| `_OVERVIEW.ki.md` |" in agents_content
    assert "## Architecture Decision Records (ADRs)" in agents_content
    assert "| 001 | Adopt Event Bus | Accepted |" in agents_content


def test_sync_agents_md_disabled_in_ki_config(mock_ki_project):
    proj_dir, ki_base = mock_ki_project

    # Explicitly disable sync_agents_md in ki_config.json
    ki_cfg_path = ki_base / "ki_config.json"
    cfg = json.loads(ki_cfg_path.read_text(encoding="utf-8"))
    cfg["sync_agents_md"] = False
    ki_cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    agents_path = proj_dir / "AGENTS.md"
    original_mtime = agents_path.stat().st_mtime

    res = server.handle_tool_call("sync_agents_md", {})
    assert "sync_agents_md is disabled in ki_config.json" in res["content"][0]["text"]
    assert agents_path.stat().st_mtime == original_mtime


# ─── 5. scaffold.migrate_project Preserving AGENTS.md ───

def test_migrate_project_preserves_agents_md(tmp_path):
    legacy_proj = tmp_path / "legacy_proj"
    legacy_proj.mkdir()
    legacy_know = legacy_proj / ".know"
    legacy_know.mkdir()

    # Create AGENTS.md in legacy dir
    agents_md = legacy_know / "AGENTS.md"
    agents_md.write_text("# Legacy Agents Rules", encoding="utf-8")

    res = scaffold.migrate_project(str(legacy_proj))
    assert "[+] Renamed .know/ to .ki-base/" in res
    assert "[~] Preserved existing AGENTS.md" in res

    new_agents_md = legacy_proj / ".ki-base" / "AGENTS.md"
    assert new_agents_md.exists()
    assert new_agents_md.read_text(encoding="utf-8") == "# Legacy Agents Rules"


# ─── 6. Global Sandbox Negative Tests ───

def test_tools_no_workspace_error(monkeypatch):
    monkeypatch.setattr(ki_utils, "ACTIVE_WORKSPACE_PATH", "")
    monkeypatch.setattr(ki_utils, "find_project_by_cwd", lambda cwd=None: None)
    monkeypatch.setattr(ki_utils, "get_knowledge_root", lambda: "")

    for tool_name in ["add_ki_to_config", "edit_doc_config", "create_adr", "sync_agents_md"]:
        res = server.handle_tool_call(tool_name, {"ki_name": "x", "title": "t", "topic_name": "tn", "section": "artifacts", "action": "set"})
        assert res.get("isError") is True
        assert "No active workspace detected" in res["content"][0]["text"]


# ─── 7. Additional Targeted Negative Tests ───

def test_edit_doc_config_negative_tracked_modules_append_no_value(mock_ki_project):
    mock_ki_project
    res = server.handle_tool_call("edit_doc_config", {
        "section": "tracked_modules",
        "action": "append",
        "value": None
    })
    assert res.get("isError") is True
    assert "'value' is required" in res["content"][0]["text"]


def test_edit_doc_config_negative_tracked_modules_set_invalid_value(mock_ki_project):
    mock_ki_project
    res = server.handle_tool_call("edit_doc_config", {
        "section": "tracked_modules",
        "action": "set",
        "value": "not-a-list"
    })
    assert res.get("isError") is True
    assert "must be a list" in res["content"][0]["text"]


def test_edit_doc_config_negative_artifacts_missing_key_for_set(mock_ki_project):
    mock_ki_project
    res = server.handle_tool_call("edit_doc_config", {
        "section": "artifacts",
        "action": "set",
        "key": "",
        "value": {"desc": "test"}
    })
    assert res.get("isError") is True
    assert "'key' (artifact name) is required" in res["content"][0]["text"]


def test_edit_doc_config_negative_coverage_settings_append_to_non_list(mock_ki_project):
    mock_ki_project
    # Set thresholds as dict
    server.handle_tool_call("edit_doc_config", {
        "section": "coverage_settings",
        "action": "set",
        "key": "thresholds",
        "value": {"density": 50.0}
    })
    # Try to append to dict (which is not a list)
    res = server.handle_tool_call("edit_doc_config", {
        "section": "coverage_settings",
        "action": "append",
        "key": "thresholds",
        "value": "something"
    })
    assert res.get("isError") is True
    assert "is not a list" in res["content"][0]["text"]


def test_create_adr_negative_missing_topic_name(mock_ki_project):
    mock_ki_project
    res = server.handle_tool_call("create_adr", {
        "title": "Valid Title",
        "context": "ctx",
        "decision": "dec",
        "consequences": "csq",
        "topic_name": ""
    })
    assert res.get("isError") is True
    assert "required" in res["content"][0]["text"]


def test_sync_agents_md_negative_file_not_found(mock_ki_project):
    mock_ki_project
    res = server.handle_tool_call("sync_agents_md", {
        "agents_path": "non_existent_folder/AGENTS.md"
    })
    assert "Error: AGENTS.md not found" in res["content"][0]["text"]


def test_add_ki_to_config_cli_negative_invalid_json(monkeypatch):
    import add_ki_to_config
    monkeypatch.setattr(sys, "argv", [
        "add_ki_to_config.py", "KI_test.md", "description", "--covers", "{invalid_json}"
    ])
    with pytest.raises(SystemExit) as excinfo:
        add_ki_to_config.main()
    assert excinfo.value.code == 1


# ─── 5. Enhanced ADR Features Tests (Supersedes list, Invariants, Alternatives, Scope) ───

def test_create_adr_with_supersedes_list(mock_ki_project):
    proj_dir, ki_base = mock_ki_project
    decisions_dir = ki_base / "decisions"

    # 1. Create ADR 001
    server.handle_tool_call("create_adr", {
        "title": "Old Approach 1",
        "status": "Accepted",
        "context": "Context 1",
        "decision": "Decision 1",
        "consequences": "Consequences 1",
        "topic_name": "old_one"
    })
    # 2. Create ADR 002
    server.handle_tool_call("create_adr", {
        "title": "Old Approach 2",
        "status": "Accepted",
        "context": "Context 2",
        "decision": "Decision 2",
        "consequences": "Consequences 2",
        "topic_name": "old_two"
    })

    adr1_path = decisions_dir / "001_old_one.md"
    adr2_path = decisions_dir / "002_old_two.md"
    assert adr1_path.exists()
    assert adr2_path.exists()

    # 3. Create ADR 003 that supersedes both 001 and 002
    res3 = server.handle_tool_call("create_adr", {
        "title": "Consolidated New Architecture",
        "status": "Accepted",
        "context": "Both old approaches failed concurrency requirements.",
        "decision": "Use Unified Engine.",
        "consequences": "Much simpler architecture.",
        "topic_name": "unified_engine",
        "supersedes": ["001", "002"],
        "rejected_alternatives": "- Polling queues: high latency\n- Raw threads: race conditions",
        "invariants": "- [MUST] Use async I/O\n- [MUST NOT] Block event loop",
        "verification": "pytest tests/test_engine.py"
    })
    msg3 = res3["content"][0]["text"]
    assert "Created ADR 003_unified_engine.md" in msg3
    assert "Updated superseded ADRs: 001_old_one.md, 002_old_two.md" in msg3

    # Verify ADR 001 was updated
    content1 = adr1_path.read_text(encoding="utf-8")
    assert "<!-- status: Superseded by ADR 003 -->" in content1
    assert "**Status**: Superseded by [ADR 003](./003_unified_engine.md)" in content1
    assert "> [!WARNING]" in content1
    assert "This ADR is superseded by [ADR 003: Consolidated New Architecture](./003_unified_engine.md)" in content1

    # Verify ADR 002 was updated
    content2 = adr2_path.read_text(encoding="utf-8")
    assert "<!-- status: Superseded by ADR 003 -->" in content2
    assert "**Status**: Superseded by [ADR 003](./003_unified_engine.md)" in content2
    assert "> [!WARNING]" in content2

    # Verify ADR 003 content
    adr3_path = decisions_dir / "003_unified_engine.md"
    assert adr3_path.exists()
    content3 = adr3_path.read_text(encoding="utf-8")
    assert "<!-- supersedes: 001, 002 -->" in content3
    assert "**Supersedes**: [ADR 001](./001_old_one.md), [ADR 002](./002_old_two.md)" in content3
    assert "**Environment**:" in content3
    assert "## Alternatives Considered & Rejected" in content3
    assert "Polling queues: high latency" in content3
    assert "## Invariants & Rules for AI" in content3
    assert "[MUST] Use async I/O" in content3
    assert "## Verification" in content3
    assert "pytest tests/test_engine.py" in content3

    # Verify doc_config.json update
    doc_cfg = ki_utils.get_doc_config()
    for k, v in doc_cfg["knowledge_items"].items():
        if "001_old_one.md" in k or "002_old_two.md" in k:
            assert "(Superseded by ADR 003)" in v["description"]

    # Verify parse_adr_file and get_adr_table
    parsed = ki_utils.parse_adr_file(str(adr3_path), str(proj_dir))
    assert parsed["supersedes"] == ["001", "002"]

    adr_table = ki_utils.get_adr_table()
    assert "Superseded by ADR 003" in adr_table


def test_create_adr_affected_files_and_ki_mapping(mock_ki_project):
    proj_dir, ki_base = mock_ki_project
    doc_cfg_file = ki_base / "doc_config.json"
    doc_data = json.loads(doc_cfg_file.read_text(encoding="utf-8"))
    doc_data["knowledge_items"]["KI_storage.md"] = {
        "summary": "Storage layer",
        "covers": ["Storage"],
        "depends_on": ["src/storage.py", "src/models/"]
    }
    doc_cfg_file.write_text(json.dumps(doc_data, indent=2), encoding="utf-8")

    res = server.handle_tool_call("create_adr", {
        "title": "Use Parquet for Cold Storage",
        "context": "Need columnar format.",
        "decision": "Adopt Parquet.",
        "consequences": "Faster analytics.",
        "topic_name": "parquet_storage",
        "affected_files": ["src/storage.py", "src/extra.py"]
    })
    assert res.get("isError") is not True
    msg = res["content"][0]["text"]
    assert "Linked to Knowledge Items: KI_storage.md" in msg

    # Verify file content
    adr_path = ki_base / "decisions" / "001_parquet_storage.md"
    content = adr_path.read_text(encoding="utf-8")
    assert "## Scope & Affected Files" in content
    assert "`src/storage.py` (Related KI: `KI_storage.md`)" in content
    assert "- `src/extra.py`" in content

    # Verify doc_config registered depends_on
    updated_cfg = ki_utils.get_doc_config()
    registered = None
    for k, v in updated_cfg["knowledge_items"].items():
        if "001_parquet_storage.md" in k:
            registered = v
            break
    assert registered is not None
    assert "KI_storage.md" in registered["depends_on"]

