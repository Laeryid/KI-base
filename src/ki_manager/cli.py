"""
ki_manager/cli.py

CLI commands for ki-manager (besides the MCP server).
Provides:
  install-skills  — install bundled workflows as Agent Skills
  install-hooks   — install Git pre-commit hook or declarative agent harness hooks
  hook            — execute a lifecycle hook event (pre-edit, stop-lint) reading JSON stdin
  lint            — run deterministic linter on the knowledge base

Usage:
    ki-manager install-skills [--path /path/to/skills/dir]
    ki-manager install-hooks [--path /path/to/repo] [--harness <name_or_file>] [--list-harnesses] [--force]
    ki-manager hook <pre-edit|stop-lint> [--harness <name_or_file>] [--workspace <path>]
    ki-manager lint [--staged] [--fix] [--json]
"""

import sys
import os
import argparse
import subprocess
from pathlib import Path
from typing import Optional

_PACKAGE_DIR = Path(__file__).parent
_WORKFLOWS_DIR = _PACKAGE_DIR / "workflows"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parses YAML frontmatter from a markdown file.
    
    Returns (meta_dict, body_text).
    If there is no frontmatter, returns ({}, text).
    """
    if not text.startswith("---"):
        return {}, text
    
    lines = text.split("\n")
    end_idx = None
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end_idx = i
            break
    
    if end_idx is None:
        return {}, text
    
    fm_lines = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1:])
    
    meta = {}
    for line in fm_lines:
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip().strip('"')
    
    return meta, body


def install_skills(argv=None):
    """Entry point for `ki-manager install-skills`."""
    parser = argparse.ArgumentParser(
        prog="ki-manager install-skills",
        description="Install ki-manager workflows as Agent Skills (agentskills.io standard).",
    )
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="Target skills directory (default: current working directory)",
    )
    parser.add_argument(
        "--tool-mode",
        type=str,
        choices=["full", "compact"],
        default=None,
        help="Format for skill instructions (default: full, or KI_TOOL_MODE env var)",
    )
    args = parser.parse_args(argv)

    target = Path(args.path).resolve() if args.path else Path.cwd()

    if not _WORKFLOWS_DIR.exists():
        print(f"Error: workflows directory not found: {_WORKFLOWS_DIR}", file=sys.stderr)
        sys.exit(1)

    workflow_files = sorted(_WORKFLOWS_DIR.glob("*.md"))
    if not workflow_files:
        print("No workflow files found.", file=sys.stderr)
        sys.exit(1)

    installed = []
    skipped = []

    # Import facade renderer
    sys.path.insert(0, str(_PACKAGE_DIR / "tools"))
    from facade import render_instruction
    target_mode = (args.tool_mode or os.environ.get("KI_TOOL_MODE", "full")).lower()
    if target_mode not in ("full", "compact"):
        target_mode = "full"

    for wf_file in workflow_files:
        raw_content = wf_file.read_text(encoding="utf-8")
        rendered_content = render_instruction(raw_content, tool_mode=target_mode)
        meta, _ = _parse_frontmatter(rendered_content)
        
        skill_name = meta.get("name") or f"ki-manager-{wf_file.stem}"
        skill_dir = target / skill_name
        skill_md = skill_dir / "SKILL.md"
        
        if skill_md.exists():
            skipped.append(skill_name)
            continue
        
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md.write_text(rendered_content, encoding="utf-8")
        installed.append(skill_name)

    print(f"Installed: {len(installed)} skill(s)")
    for name in installed:
        print(f"  ✓ {name}")

    if skipped:
        print(f"Skipped (already exist): {len(skipped)}")
        for name in skipped:
            print(f"  - {name}")
        print(
            "\n  To update a skill to the latest version, delete its folder and re-run:\n"
            f"    rm -rf <skills-dir>/<skill-name>\n"
            f"    ki-manager install-skills --path <skills-dir>"
        )

    print(f"\nTarget: {target}")


_PRE_COMMIT_MARKER = "# ki-manager pre-commit hook"

_PRE_COMMIT_SCRIPT = """#!/usr/bin/env sh
# ki-manager pre-commit hook (installed by ki-manager install-hooks)
if command -v ki-manager >/dev/null 2>&1; then
    ki-manager lint --staged
elif [ -x ".venv/Scripts/python.exe" ]; then
    .venv/Scripts/python.exe -m ki_manager.server lint --staged
elif [ -x ".venv/bin/python" ]; then
    .venv/bin/python -m ki_manager.server lint --staged
else
    python -m ki_manager.server lint --staged
fi
"""


def _find_git_hooks_dir(target_dir: Path) -> Optional[Path]:
    """Locate the .git/hooks directory using git rev-parse."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks"],
            cwd=str(target_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if res.returncode != 0:
            return None
        hooks_raw = res.stdout.strip()
        if not hooks_raw:
            return None
        p = Path(hooks_raw)
        if not p.is_absolute():
            p = (target_dir / p).resolve()
        return p
    except Exception:
        return None


def _import_ki_hooks():
    scripts_dir = str(_PACKAGE_DIR / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import ki_hooks
    return ki_hooks


def install_hooks(argv=None) -> int:
    """Entry point for `ki-manager install-hooks`."""
    parser = argparse.ArgumentParser(
        prog="ki-manager install-hooks",
        description="Install Git pre-commit hook or declarative agent harness hooks.",
    )
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="Path inside target repository/project (default: current working directory)",
    )
    parser.add_argument(
        "--harness",
        type=str,
        default=None,
        help="Harness name, alias (e.g. agy, antigravity, vaib, claude), or path to custom JSON manifest",
    )
    parser.add_argument(
        "--list-harnesses",
        action="store_true",
        help="List discovered harness manifests and aliases",
    )
    parser.add_argument(
        "--cmd",
        type=str,
        default=None,
        help="Override {ki_cmd} prefix when installing harness hooks",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing non-ki-manager hook or malformed JSON config",
    )
    args = parser.parse_args(argv)

    target = Path(args.path).resolve() if args.path else Path.cwd()

    if args.list_harnesses:
        ki_hooks = _import_ki_hooks()
        harnesses = ki_hooks.list_harnesses(project_root=str(target))
        if not harnesses:
            print("No harness manifests found.")
            return 0
        print("Available harnesses:")
        for h in harnesses:
            aliases = ", ".join(h.get("aliases") or [])
            tgt = (h.get("install") or {}).get("target_file", "—")
            desc = h.get("description", "")
            print(f"  - {h['name']} (aliases: {aliases}) -> {tgt}")
            if desc:
                print(f"      {desc}")
        return 0

    if args.harness:
        ki_hooks = _import_ki_hooks()
        try:
            res = ki_hooks.install_harness_hooks(
                harness_ref=args.harness,
                project_root=str(target),
                force=args.force,
                ki_cmd=args.cmd,
            )
            print(f"Installed '{res['harness']}' hooks into: {res['target_file']}")
            return 0
        except Exception as e:
            print(f"Error installing harness hooks: {e}", file=sys.stderr)
            return 1

    hooks_dir = _find_git_hooks_dir(target)
    if hooks_dir is None:
        print(f"Error: '{target}' is not inside a Git repository.", file=sys.stderr)
        return 1

    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "pre-commit"

    if hook_path.exists():
        existing = hook_path.read_text(encoding="utf-8", errors="replace")
        if _PRE_COMMIT_MARKER not in existing and not args.force:
            print(
                f"Error: existing pre-commit hook at '{hook_path}' was not created by ki-manager. "
                "Re-run with --force to overwrite.",
                file=sys.stderr,
            )
            return 1

    with open(hook_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(_PRE_COMMIT_SCRIPT)

    try:
        os.chmod(hook_path, 0o755)
    except Exception:
        pass

    print(f"Installed Git pre-commit hook: {hook_path}")
    return 0


def run_hook(argv=None) -> int:
    """Entry point for `ki-manager hook <event>`."""
    parser = argparse.ArgumentParser(
        prog="ki-manager hook",
        description="Execute a declarative ki-manager hook handler reading JSON from stdin.",
    )
    parser.add_argument(
        "event",
        choices=["pre-edit", "stop-lint"],
        help="Hook lifecycle event to handle",
    )
    parser.add_argument(
        "--harness",
        type=str,
        default=None,
        help="Harness name, alias, or path to JSON manifest",
    )
    parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help="Explicit project root override",
    )
    args = parser.parse_args(argv)
    ki_hooks = _import_ki_hooks()
    return ki_hooks.run_hook_cli(
        hook_event=args.event,
        harness=args.harness,
        project_root=args.workspace,
    )


def run_lint(argv=None):
    """Entry point for `ki-manager lint`."""
    scripts_dir = str(_PACKAGE_DIR / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import ki_lint

    old_argv = sys.argv
    try:
        sys.argv = ["ki-manager lint"] + list(argv or [])
        ki_lint.main()
    finally:
        sys.argv = old_argv


def main():
    """Dispatcher for ki-manager CLI subcommands."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        print("Usage: ki-manager <command> [options]")
        print("Commands:")
        print("  install-skills  Install bundled workflows as Agent Skills")
        print("  install-hooks   Install Git pre-commit hook or agent harness hooks (--harness)")
        print("  hook            Run a lifecycle hook handler (pre-edit, stop-lint)")
        print("  lint            Lint the project knowledge base")
        sys.exit(0 if len(sys.argv) >= 2 and sys.argv[1] in ("--help", "-h") else 1)

    command = sys.argv[1]
    if command == "install-skills":
        install_skills(sys.argv[2:])
    elif command == "install-hooks":
        rc = install_hooks(sys.argv[2:])
        sys.exit(rc)
    elif command == "hook":
        rc = run_hook(sys.argv[2:])
        sys.exit(rc)
    elif command == "lint":
        run_lint(sys.argv[2:])
    elif command in ("--version", "-v"):
        try:
            from . import __version__ as v
        except Exception:
            import importlib.metadata
            try:
                v = importlib.metadata.version("ki-manager")
            except Exception:
                v = "unknown"
        print(f"ki-manager {v}")
        sys.exit(0)
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

