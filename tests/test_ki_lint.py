import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ki_manager import cli, server
from ki_manager.scripts import ki_lint, ki_utils


def _init_project(tmp_path: Path, with_src: bool = True):
    proj = tmp_path / "proj"
    proj.mkdir()
    ki_root = proj / ".ki-base"
    know_dir = ki_root / "knowledge"
    dec_dir = ki_root / "decisions"
    know_dir.mkdir(parents=True)
    dec_dir.mkdir(parents=True)

    (ki_root / "ki_config.json").write_text(
        json.dumps({"knowledge_root": ".ki-base"}, indent=2),
        encoding="utf-8",
    )
    if with_src:
        src_dir = proj / "src"
        src_dir.mkdir()
        (src_dir / "app.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")

    (know_dir / "_OVERVIEW.ki.md").write_text(
        "<!-- last_verified: 2026-01-01 -->\n"
        "# _OVERVIEW\n\n"
        "## Overview\nProject overview.\n\n"
        "## Related KIs\n",
        encoding="utf-8",
    )
    (know_dir / "app.ki.md").write_text(
        "<!-- last_verified: 2026-01-01 -->\n"
        "# App Module\n\n"
        "## Overview\nCore application logic.\n\n"
        "## Key Components\n- `hello()` in `src/app.py`\n\n"
        "## Related KIs\n",
        encoding="utf-8",
    )
    doc_cfg = {
        "knowledge_items": {
            "_OVERVIEW.ki.md": {"description": "Overview", "covers": [], "depends_on": []},
            "app.ki.md": {
                "description": "App module",
                "covers": ["src"],
                "depends_on": ["src/app.py"] if with_src else [],
            },
        }
    }
    (ki_root / "doc_config.json").write_text(json.dumps(doc_cfg, indent=2), encoding="utf-8")
    return proj, ki_root, know_dir, dec_dir


def test_lint_valid_project(tmp_path):
    proj, ki_root, _, _ = _init_project(tmp_path)
    res = ki_lint.lint_knowledge_base(str(proj), str(ki_root))
    assert res["ok"] is True
    assert res["errors"] == []
    assert res["checked_kis"] == 2
    assert res["checked_adrs"] == 0


def test_lint_structure_misplaced_ki_and_missing_overview(tmp_path):
    proj, ki_root, know_dir, _ = _init_project(tmp_path)
    (know_dir / "_OVERVIEW.ki.md").unlink()
    (ki_root / "stray.ki.md").write_text("# Stray\n\n## Overview\nOops.\n", encoding="utf-8")

    res = ki_lint.lint_knowledge_base(str(proj), str(ki_root))
    codes = {e["code"] for e in res["errors"]}
    assert res["ok"] is False
    assert "MISSING_OVERVIEW" in codes
    assert "MISPLACED_KI" in codes


def test_lint_ki_metadata_and_empty_sections(tmp_path):
    proj, ki_root, know_dir, _ = _init_project(tmp_path)
    # Active KI missing last_verified, invalid status, empty Key Components, scaffold marker
    (know_dir / "bad.ki.md").write_text(
        "<!-- status: bogus -->\n"
        "# Bad KI\n\n"
        "## Overview\nHas text.\n",
        encoding="utf-8",
    )
    (know_dir / "empty_active.ki.md").write_text(
        "<!-- status: active -->\n"
        "# Empty Active\n\n"
        "<!-- scaffold: true -->\n"
        "## Overview\n\n"
        "## Related KIs\n",
        encoding="utf-8",
    )
    # PoC KI without last_verified should be allowed
    (know_dir / "exp.ki.md").write_text(
        "<!-- status: poc -->\n"
        "# Experiment\n\n"
        "## Overview\nDraft experiment notes.\n",
        encoding="utf-8",
    )
    cfg_path = ki_root / "doc_config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["knowledge_items"]["bad.ki.md"] = {"description": "bad", "depends_on": []}
    cfg["knowledge_items"]["empty_active.ki.md"] = {"description": "empty", "depends_on": []}
    cfg["knowledge_items"]["exp.ki.md"] = {"description": "exp", "depends_on": ["src/nonexistent.py"], "status": "poc"}
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    res = ki_lint.lint_knowledge_base(str(proj), str(ki_root))
    assert res["ok"] is False
    err_codes_by_file = {}
    for e in res["errors"]:
        err_codes_by_file.setdefault(Path(e["file"]).name, set()).add(e["code"])

    assert "INVALID_STATUS" in err_codes_by_file["bad.ki.md"]
    assert "MISSING_LAST_VERIFIED" in err_codes_by_file["empty_active.ki.md"]
    assert "UNFINALIZED_SCAFFOLD" in err_codes_by_file["empty_active.ki.md"]
    assert "EMPTY_SECTION" in err_codes_by_file["empty_active.ki.md"]
    assert "exp.ki.md" not in err_codes_by_file
    # Broken depends_on on poc should be a warning, not an error
    assert any(w["code"] == "BROKEN_DEPENDS_ON_SOFT" and "exp.ki.md" in w["file"] for w in res["warnings"])


def test_lint_fix_registers_unmapped_ki_and_depends_on_rules(tmp_path):
    proj, ki_root, know_dir, _ = _init_project(tmp_path)
    (know_dir / "new_mod.ki.md").write_text(
        "<!-- last_verified: 2026-02-01 -->\n"
        "# New Module\n\n"
        "## Overview\nDetails here.\n",
        encoding="utf-8",
    )
    # Missing depends_on on active -> error; on archived -> skipped
    (know_dir / "old.ki.md").write_text(
        "<!-- status: archived -->\n"
        "# Old Module\n\n"
        "## Overview\nLegacy.\n",
        encoding="utf-8",
    )
    cfg_path = ki_root / "doc_config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["knowledge_items"]["app.ki.md"]["depends_on"].append("src/deleted.py")
    cfg["knowledge_items"]["old.ki.md"] = {"description": "old", "depends_on": ["src/also_deleted.py"], "status": "archived"}
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    res_no_fix = ki_lint.lint_knowledge_base(str(proj), str(ki_root), fix=False)
    codes = {e["code"] for e in res_no_fix["errors"]}
    assert "UNREGISTERED_KI" in codes
    assert "BROKEN_DEPENDS_ON" in codes
    assert not any("old.ki.md" in e["file"] for e in res_no_fix["errors"])

    res_fix = ki_lint.lint_knowledge_base(str(proj), str(ki_root), fix=True)
    assert any("new_mod.ki.md" in item for item in res_fix["fixed"])
    updated_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert "new_mod.ki.md" in updated_cfg["knowledge_items"]


def test_lint_adr_superseded_validation_and_cycle_detection(tmp_path):
    proj, ki_root, _, dec_dir = _init_project(tmp_path)
    (dec_dir / "001_first.md").write_text(
        "<!-- status: superseded -->\n# ADR 001: First\n\n## Context\nOld.\n",
        encoding="utf-8",
    )
    (dec_dir / "002_second.md").write_text(
        "<!-- status: superseded -->\n<!-- superseded_by: 999 -->\n# ADR 002: Second\n",
        encoding="utf-8",
    )
    (dec_dir / "003_cycle_a.md").write_text(
        "<!-- status: superseded -->\n<!-- superseded_by: 004 -->\n# ADR 003: Cycle A\n",
        encoding="utf-8",
    )
    (dec_dir / "004_cycle_b.md").write_text(
        "<!-- status: superseded -->\n<!-- superseded_by: 003 -->\n# ADR 004: Cycle B\n",
        encoding="utf-8",
    )

    res = ki_lint.lint_knowledge_base(str(proj), str(ki_root))
    assert res["ok"] is False
    codes_by_file = {Path(e["file"]).name: e["code"] for e in res["errors"]}
    assert codes_by_file["001_first.md"] == "MISSING_SUPERSEDED_BY"
    assert codes_by_file["002_second.md"] == "BROKEN_SUPERSEDED_BY"
    assert codes_by_file["003_cycle_a.md"] == "SUPERSEDED_CYCLE"
    assert codes_by_file["004_cycle_b.md"] == "SUPERSEDED_CYCLE"


def test_lint_staged_mode_git(tmp_path):
    proj, ki_root, know_dir, _ = _init_project(tmp_path)
    subprocess.run(["git", "init"], cwd=str(proj), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(proj), check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(proj), check=True)
    subprocess.run(["git", "add", "."], cwd=str(proj), check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(proj), check=True, capture_output=True)

    # Modify only source code and stage it -> lint --staged should skip KB and succeed
    (proj / "src" / "app.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    subprocess.run(["git", "add", "src/app.py"], cwd=str(proj), check=True)
    res_skip = ki_lint.lint_knowledge_base(str(proj), str(ki_root), staged=True)
    assert res_skip["ok"] is True
    assert res_skip["skipped"] is True

    # Break app.ki.md and stage it -> lint --staged must fail
    (know_dir / "app.ki.md").write_text("# App Module\n\n## Overview\n\n", encoding="utf-8")
    subprocess.run(["git", "add", ".ki-base/knowledge/app.ki.md"], cwd=str(proj), check=True)
    res_fail = ki_lint.lint_knowledge_base(str(proj), str(ki_root), staged=True)
    assert res_fail["ok"] is False
    assert res_fail["skipped"] is False
    assert any(e["code"] == "MISSING_LAST_VERIFIED" for e in res_fail["errors"])


def test_ki_sync_aborts_on_lint_error_and_succeeds_after_fix(tmp_path, monkeypatch):
    proj, ki_root, know_dir, _ = _init_project(tmp_path)
    agents_md = proj / "AGENTS.md"
    agents_md.write_text(
        "# Agents\n\n## Knowledge Items\n| File | Description |\n|---|---|\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(server, "get_project_root", lambda: str(proj))
    monkeypatch.setattr(server, "get_jail_dir", lambda: str(ki_root))
    monkeypatch.setattr(ki_utils, "ACTIVE_WORKSPACE_PATH", str(proj))

    # Native edit that introduces a lint error (unregistered + missing last_verified)
    broken_ki = know_dir / "broken.ki.md"
    broken_ki.write_text("# Broken\n\n## Overview\nText\n", encoding="utf-8")

    aborted = server.handle_tool_call("ki_sync", {})
    assert isinstance(aborted, dict) and aborted.get("isError") is True
    assert "aborted" in aborted["content"][0]["text"].lower()
    # Must NOT have written doc_state.json or DIR_INDEX.md
    assert not (ki_root / "doc_state.json").exists()
    assert not (ki_root / "DIR_INDEX.md").exists()

    # Fix broken.ki.md via native edit (fix_lint=True registers it in doc_config.json)
    broken_ki.write_text(
        "<!-- last_verified: 2026-01-01 -->\n# Broken Fixed\n\n## Overview\nValid details.\n",
        encoding="utf-8",
    )

    ok_res = server.handle_tool_call("ki_sync", {"fix_lint": True})
    assert isinstance(ok_res, dict) and not ok_res.get("isError")
    text = ok_res["content"][0]["text"]
    assert "ki_sync completed" in text
    assert (ki_root / "DIR_INDEX.md").exists()
    assert (ki_root / "doc_state.json").exists()
    assert "broken.ki.md" in agents_md.read_text(encoding="utf-8")


def test_install_hooks_and_cli_lint(tmp_path, capsys):
    proj, ki_root, _, _ = _init_project(tmp_path)
    subprocess.run(["git", "init"], cwd=str(proj), check=True, capture_output=True)

    rc = cli.install_hooks(["--path", str(proj)])
    assert rc == 0
    hook_file = proj / ".git" / "hooks" / "pre-commit"
    assert hook_file.exists()
    content = hook_file.read_text(encoding="utf-8")
    assert cli._PRE_COMMIT_MARKER in content
    assert "lint --staged" in content

    # Custom hook without marker should NOT be overwritten without --force
    hook_file.write_text("#!/bin/sh\necho custom\n", encoding="utf-8")
    rc_conflict = cli.install_hooks(["--path", str(proj)])
    assert rc_conflict == 1
    assert "echo custom" in hook_file.read_text(encoding="utf-8")

    rc_force = cli.install_hooks(["--path", str(proj), "--force"])
    assert rc_force == 0
    assert cli._PRE_COMMIT_MARKER in hook_file.read_text(encoding="utf-8")

    # Test `python -m ki_manager.server lint --workspace <proj> --json`
    proc = subprocess.run(
        [sys.executable, "-m", "ki_manager.server", "lint", "--workspace", str(proj), "--json"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert data["checked_kis"] == 2
