"""
ki_manager/cli.py

CLI commands for ki-manager (besides the MCP server).
Currently provides:
  install-skills  — install bundled workflows as Agent Skills

Usage:
    ki-manager install-skills
    ki-manager install-skills --path /path/to/skills/dir
"""

import sys
import argparse
from pathlib import Path

_PACKAGE_DIR = Path(__file__).parent
_WORKFLOWS_DIR = _PACKAGE_DIR / "workflows"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Парсит YAML frontmatter из маркдаун-файла.
    
    Возвращает (meta_dict, body_text).
    Если frontmatter нет — возвращает ({}, text).
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

    for wf_file in workflow_files:
        content = wf_file.read_text(encoding="utf-8")
        meta, _ = _parse_frontmatter(content)
        
        skill_name = meta.get("name") or f"ki-manager-{wf_file.stem}"
        skill_dir = target / skill_name
        skill_md = skill_dir / "SKILL.md"
        
        if skill_md.exists():
            skipped.append(skill_name)
            continue
        
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md.write_text(content, encoding="utf-8")
        installed.append(skill_name)

    print(f"Installed: {len(installed)} skill(s)")
    for name in installed:
        print(f"  ✓ {name}")

    if skipped:
        print(f"Skipped (already exist): {len(skipped)}")
        for name in skipped:
            print(f"  - {name}")

    print(f"\nTarget: {target}")


def main():
    """Dispatcher for ki-manager subcommands."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if len(sys.argv) < 2:
        print("Usage: ki-manager <command> [options]")
        print("Commands:")
        print("  install-skills  Install bundled workflows as Agent Skills")
        sys.exit(1)
    
    command = sys.argv[1]
    if command == "install-skills":
        install_skills(sys.argv[2:])
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

