import json
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
PKG_DIR = ROOT_DIR / "src"
SCRIPTS_DIR = PKG_DIR / "ki_manager" / "scripts"
for p in (str(PKG_DIR), str(SCRIPTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ki_context
import ki_hooks
import ki_lint
from ki_manager import cli
from test_ki_context import _setup_workspace


def test_harness_alias_resolution_and_custom_manifest(tmp_path):
    proj = _setup_workspace(tmp_path)

    # Bundled aliases: agy, antigravity, vaib -> antigravity; claude-code -> claude
    for alias in ("agy", "antigravity", "vaib"):
        cfg = ki_hooks.resolve_harness_config(alias, project_root=str(proj))
        assert cfg is not None
        assert cfg["name"] == "antigravity"

    cfg_claude = ki_hooks.resolve_harness_config("claude-code", project_root=str(proj))
    assert cfg_claude is not None
    assert cfg_claude["name"] == "claude"

    # Project-local custom harness manifest with custom aliases (zero code changes)
    custom_dir = proj / ".ki-base" / "harnesses"
    custom_dir.mkdir(parents=True, exist_ok=True)
    custom_manifest = {
        "name": "my-custom-ide",
        "aliases": ["custom", "mcide"],
        "description": "Custom IDE hooks",
        "install": {
            "target_file": ".myide/hooks.json",
            "merge": {
                "hooks": [
                    {"event": "before_edit", "cmd": "{ki_cmd} hook pre-edit --harness {harness}"}
                ]
            },
        },
        "runtime": {
            "workspace_paths": ["ws"],
            "file_arg_paths": ["payload.target"],
            "pre_edit": {
                "allow": {"stdout": {"ok": True}, "exit_code": 0},
                "deny": {"stdout": {"ok": False, "msg": "{context}"}, "exit_code": 1},
            },
        },
    }
    (custom_dir / "custom.json").write_text(json.dumps(custom_manifest), encoding="utf-8")

    resolved = ki_hooks.resolve_harness_config("mcide", project_root=str(proj))
    assert resolved is not None
    assert resolved["name"] == "my-custom-ide"

    with pytest.raises(FileNotFoundError):
        ki_hooks.resolve_harness_config("nonexistent-harness-xyz", project_root=str(proj))


def test_install_harness_hooks_non_destructive_and_idempotent(tmp_path):
    proj = _setup_workspace(tmp_path)

    # Pre-existing user hook config in .agents/hooks.json must be preserved
    agents_dir = proj / ".agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    existing = {
        "user-safety": {
            "enabled": True,
            "PreToolUse": [{"matcher": "run_command", "hooks": [{"command": "echo safe"}]}],
        }
    }
    hooks_file = agents_dir / "hooks.json"
    hooks_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    # Install via alias "agy"
    res1 = ki_hooks.install_harness_hooks("agy", project_root=str(proj), ki_cmd="ki-manager")
    assert Path(res1["target_file"]) == hooks_file

    data1 = json.loads(hooks_file.read_text(encoding="utf-8"))
    assert "user-safety" in data1
    assert "ki-manager" in data1
    assert data1["ki-manager"]["PreToolUse"][0]["hooks"][0]["command"] == "ki-manager hook pre-edit --harness antigravity"

    # Re-install with different command is idempotent (no duplicate list entries)
    ki_hooks.install_harness_hooks("vaib", project_root=str(proj), ki_cmd="custom-ki")
    data2 = json.loads(hooks_file.read_text(encoding="utf-8"))
    assert "user-safety" in data2
    assert len(data2["ki-manager"]["PreToolUse"]) == 1
    assert len(data2["ki-manager"]["Stop"]) == 1
    assert data2["ki-manager"]["PreToolUse"][0]["hooks"][0]["command"] == "custom-ki hook pre-edit --harness antigravity"

    # Also test Claude Code array merge preserves existing user hook entries
    claude_settings = proj / ".claude" / "settings.json"
    claude_settings.parent.mkdir(parents=True, exist_ok=True)
    claude_settings.write_text(
        json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"command": "echo bash"}]}]}}),
        encoding="utf-8",
    )
    ki_hooks.install_harness_hooks("claude-code", project_root=str(proj), ki_cmd="ki-manager")
    ki_hooks.install_harness_hooks("claude", project_root=str(proj), ki_cmd="ki-manager")
    claude_data = json.loads(claude_settings.read_text(encoding="utf-8"))
    assert len(claude_data["hooks"]["PreToolUse"]) == 2
    assert any(item.get("matcher") == "Bash" for item in claude_data["hooks"]["PreToolUse"])


def test_pre_edit_allows_after_mcp_context_call(tmp_path):
    proj = _setup_workspace(tmp_path)
    target = str(proj / "src" / "auth" / "tokens.py")

    # Agent proactively calls ki_context_for BEFORE editing
    ki_context.get_context_for(files=["src/auth/tokens.py"], project_root=str(proj))

    # First edit attempt must pass immediately without blocking
    payload = {
        "workspacePaths": [str(proj)],
        "cwd": str(proj),
        "toolCall": {"name": "edit_file", "args": {"Path": target}},
    }
    code, out, err = ki_hooks.handle_pre_edit(payload, harness="agy")
    assert code == 0
    assert err is None
    assert json.loads(out) == {"decision": "allow"}


def test_pre_edit_blocks_first_edit_then_allows_retry_and_custom_harness(tmp_path):
    proj = _setup_workspace(tmp_path)
    target = str(proj / "src" / "auth" / "tokens.py")

    payload = {
        "workspacePaths": [str(proj)],
        "cwd": str(proj),
        "toolCall": {"name": "edit_file", "args": {"Path": target}},
    }

    # First attempt without prior ki_context_for -> denied with active invariants in reason
    code1, out1, _ = ki_hooks.handle_pre_edit(payload, harness="antigravity")
    assert code1 == 0
    resp1 = json.loads(out1)
    assert resp1["decision"] == "deny"
    assert "Always rotate signing keys via KeyStore." in resp1["reason"]
    assert "Reject alg=none and HS256 tokens immediately." in resp1["reason"]

    # Retry attempt passes with allow because cache was populated on first delivery
    code2, out2, _ = ki_hooks.handle_pre_edit(payload, harness="antigravity")
    assert code2 == 0
    assert json.loads(out2) == {"decision": "allow"}

    # Claude Code harness against a fresh file outputs stderr + exit code 2 on first hit
    api_target = str(proj / "src" / "api" / "routes.py")
    claude_payload = {"cwd": str(proj), "tool_input": {"file_path": api_target}}
    c_code1, c_out1, c_err1 = ki_hooks.handle_pre_edit(claude_payload, harness="claude")
    assert c_code1 == 2
    assert c_out1 is None
    assert "RFC 7807" in c_err1

    c_code2, c_out2, c_err2 = ki_hooks.handle_pre_edit(claude_payload, harness="claude")
    assert c_code2 == 0
    assert c_err2 is None


def test_pre_edit_ignores_kb_artifacts_and_unmatched_files(tmp_path):
    proj = _setup_workspace(tmp_path)
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()

    for ignored in [
        str(proj / ".ki-base" / "knowledge" / "KI_auth.md"),
        str(proj / ".ki-base" / "doc_config.json"),
        str(proj / "AGENTS.md"),
        str(artifacts_dir / "plan.md"),
        str(proj / "src" / "untracked_helper.py"),
    ]:
        payload = {
            "workspacePaths": [str(proj)],
            "artifactDirectoryPath": str(artifacts_dir),
            "toolCall": {"name": "edit_file", "args": {"Path": ignored}},
        }
        code, out, _ = ki_hooks.handle_pre_edit(payload, harness="antigravity")
        assert code == 0
        assert json.loads(out) == {"decision": "allow"}


def test_stop_lint_respects_loop_guards_and_reports_errors(tmp_path):
    proj = _setup_workspace(tmp_path)
    # Create _OVERVIEW.ki.md so base lint is clean initially, then break a KI
    know = proj / ".ki-base" / "knowledge"
    (know / "_OVERVIEW.ki.md").write_text(
        "<!-- last_verified: 2026-11-01 -->\n# Overview\n\n## Overview\nProject overview.\n",
        encoding="utf-8",
    )

    # Loop guard: continuationActive=True allows immediate stop even if KB is broken
    (know / "KI_broken.ki.md").write_text("# Broken\n", encoding="utf-8")
    code_guard, out_guard, _ = ki_hooks.handle_stop_lint(
        {
            "workspacePaths": [str(proj)],
            "continuationActive": True,
            "terminationReason": "NO_TOOL_CALL",
        },
        harness="antigravity",
    )
    assert code_guard == 0
    assert json.loads(out_guard) == {}

    # Cancellation guard: USER_CANCELED does not block stop
    code_cancel, out_cancel, _ = ki_hooks.handle_stop_lint(
        {
            "workspacePaths": [str(proj)],
            "continuationActive": False,
            "terminationReason": "USER_CANCELED",
        },
        harness="antigravity",
    )
    assert code_cancel == 0
    assert json.loads(out_cancel) == {}

    # Normal NO_TOOL_CALL stop with KB lint errors -> returns decision=continue
    code_err, out_err, _ = ki_hooks.handle_stop_lint(
        {
            "workspacePaths": [str(proj)],
            "continuationActive": False,
            "terminationReason": "NO_TOOL_CALL",
        },
        harness="antigravity",
    )
    assert code_err == 0
    resp_err = json.loads(out_err)
    assert resp_err["decision"] == "continue"
    assert "KI_broken.ki.md" in resp_err["reason"]


def test_cli_install_hooks_with_alias_and_hook_runner(tmp_path, capsys):
    proj = _setup_workspace(tmp_path)

    rc_list = cli.install_hooks(["--path", str(proj), "--list-harnesses"])
    assert rc_list == 0
    listed = capsys.readouterr().out
    assert "antigravity" in listed
    assert "vaib" in listed
    assert "claude" in listed

    rc_inst = cli.install_hooks(["--path", str(proj), "--harness", "vaib", "--cmd", "ki-manager"])
    assert rc_inst == 0
    assert (proj / ".agents" / "hooks.json").is_file()
    capsys.readouterr()

    # Check run_hook_cli directly with custom stdin text
    rc_hook = ki_hooks.run_hook_cli(
        hook_event="pre-edit",
        harness="agy",
        stdin_text=json.dumps({
            "workspacePaths": [str(proj)],
            "toolCall": {"name": "edit_file", "args": {"Path": str(proj / "src" / "auth" / "tokens.py")}},
        }),
    )
    assert rc_hook == 0
    hook_out = json.loads(capsys.readouterr().out)
    assert hook_out["decision"] == "deny"


def test_ki_lint_fix_inserts_last_verified_and_nested_update(tmp_path):
    proj = tmp_path / "nested_proj"
    sub = proj / ".ki-base" / "knowledge" / "sub"
    sub.mkdir(parents=True)
    (proj / ".ki-base" / "ki_config.json").write_text(
        json.dumps({"project_name": "Nested", "knowledge_root": ".ki-base"}),
        encoding="utf-8",
    )
    (proj / ".ki-base" / "doc_config.json").write_text(
        json.dumps({"knowledge_items": {}}), encoding="utf-8"
    )
    (proj / ".ki-base" / "knowledge" / "_OVERVIEW.ki.md").write_text(
        "<!-- last_verified: 2026-11-01 -->\n# Overview\n\n## Overview\nOk.\n",
        encoding="utf-8",
    )
    nested_ki = sub / "KI_nested.ki.md"
    nested_ki.write_text("# KI Nested\n\n## Overview\nNested subsystem.\n", encoding="utf-8")

    res = ki_lint.lint_knowledge_base(project_root=str(proj), fix=True)
    assert res["ok"] is True
    assert "<!-- last_verified:" in nested_ki.read_text(encoding="utf-8")
    assert any("last_verified" in msg for msg in res["fixed"])
