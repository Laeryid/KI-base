"""
git_diff_secured.py

Safely runs git status and git diff for project files within the project sandbox.
Prevents argument/flag injection and path traversal.
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils


def git_diff_secured(paths: List[str] = None) -> str:
    project_root = ki_utils.get_project_root()
    if not project_root or not os.path.exists(project_root):
        return "Error: No active project context."

    safe_paths = []
    if paths:
        for p in paths:
            clean_p = p.strip()
            if not clean_p:
                continue
            if clean_p.startswith("-") or any(char in clean_p for char in [";", "|", "&", ">", "<", "`"]):
                return f"Error: Suspicious argument or path '{clean_p}'."
            abs_p = os.path.abspath(os.path.join(project_root, clean_p))
            if not ki_utils.is_subpath(abs_p, project_root):
                return f"Access Denied: Path '{clean_p}' escapes project root."
            safe_paths.append(os.path.relpath(abs_p, project_root).replace("\\", "/"))

    try:
        if safe_paths:
            stat_cmd = ["git", "status", "--short", "--"] + safe_paths
            diff_cmd = ["git", "diff", "HEAD", "--"] + safe_paths
        else:
            stat_cmd = ["git", "status", "--short"]
            diff_cmd = ["git", "diff", "HEAD"]

        stat_res = subprocess.run(
            stat_cmd, cwd=project_root, capture_output=True, text=True, encoding="utf-8"
        )
        diff_res = subprocess.run(
            diff_cmd, cwd=project_root, capture_output=True, text=True, encoding="utf-8"
        )

        output = []
        if stat_res.stdout.strip():
            output.append("### Git Status:\n" + stat_res.stdout.strip())
        if diff_res.stdout.strip():
            output.append("### Git Diff:\n" + diff_res.stdout.strip())
        if not output:
            output.append("No changes detected in git.")

        return "\n\n".join(output)
    except Exception as e:
        return f"Git execution error: {str(e)}"


def main():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Secured git diff for project files.")
    parser.add_argument("paths", nargs=argparse.REMAINDER, help="File or directory paths relative to project root")
    args = parser.parse_args()

    result = git_diff_secured(args.paths)
    print(result)


if __name__ == "__main__":
    main()
