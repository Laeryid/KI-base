import os
import sys
import argparse
import subprocess
import json
import re
from datetime import date
from pathlib import Path

def run_cmd(cmd, cwd=None, check=True):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if check and result.returncode != 0:
        print(f"Error executing command: {' '.join(cmd)}")
        print(result.stdout)
        print(result.stderr)
        sys.exit(result.returncode)
    return result.stdout.strip()

def update_file_regex(filepath, pattern, replacement):
    if not os.path.exists(filepath):
        print(f"Warning: File {filepath} not found, skipping.")
        return
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content, count = re.subn(pattern, replacement, content)
    if count > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {filepath}")
    else:
        print(f"Warning: Could not find match in {filepath}")

def update_json_file(filepath, new_version):
    if not os.path.exists(filepath):
        print(f"Warning: File {filepath} not found, skipping.")
        return
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    data["version"] = new_version
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"Updated {filepath}")

def update_changelog(filepath, version):
    if not os.path.exists(filepath):
        print(f"Warning: File {filepath} not found, skipping changelog update.")
        return
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if f"## [{version}]" in content or f"## [v{version}]" in content:
        print(f"Changelog already contains entry for {version}.")
        return
    
    today = date.today().isoformat()
    if "## [Unreleased]" in content:
        replacement = f"## [Unreleased]\n\n## [{version}] — {today}"
        new_content = content.replace("## [Unreleased]", replacement, 1)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {filepath} with version {version} section.")
    else:
        print(f"Notice: '## [Unreleased]' not found in {filepath}. Please update changelog manually if needed.")

def main():
    parser = argparse.ArgumentParser(description="Publish a new version of ki-manager")
    parser.add_argument("version", help="New version (e.g. 2.0.38)")
    parser.add_argument("-m", "--message", help="Commit message", default=None)
    parser.add_argument("--repo-root", help="Path to repository root", default=".")
    parser.add_argument("--skip-tests", action="store_true", help="Skip pre-flight verification gate")
    
    args = parser.parse_args()
    
    version = args.version
    if version.startswith("v"):
        version = version[1:]
        
    msg = args.message if args.message else f"Bump version to {version}"
    repo_root = Path(args.repo_root).resolve()
    
    # Pre-flight gate: verify all tests and build pass BEFORE modifying any files
    if not args.skip_tests:
        print("Running pre-flight verification gate (pytest + build + CLI checks)...")
        verify_script = repo_root / "scripts" / "verify_release.py"
        if verify_script.exists():
            run_cmd([sys.executable, str(verify_script)], cwd=repo_root)
        else:
            run_cmd([sys.executable, "-m", "pytest", "tests/"], cwd=repo_root)

    print(f"Bumping version to {version}...")
    
    # 1. pyproject.toml
    pyproject_path = repo_root / "pyproject.toml"
    update_file_regex(
        pyproject_path,
        r'version\s*=\s*"[^"]+"',
        f'version = "{version}"'
    )
    
    # 2. src/ki_manager/__init__.py
    init_path = repo_root / "src" / "ki_manager" / "__init__.py"
    update_file_regex(
        init_path,
        r'__version__\s*=\s*"[^"]+"',
        f'__version__ = "{version}"'
    )
    
    # 3. CHANGELOG.md
    changelog_path = repo_root / "CHANGELOG.md"
    update_changelog(changelog_path, version)
    
    # Check if there are changes
    status = run_cmd(["git", "status", "--porcelain"], cwd=repo_root)
    if not status:
        print("No files modified. Exiting.")
        sys.exit(0)
        
    # Git add, commit, tag, push
    print("Committing and pushing changes...")
    
    # Add ALL files (both version bumps and any code changes/fixes)
    run_cmd(["git", "add", "-A"], cwd=repo_root)
    
    # Commit
    run_cmd(["git", "commit", "-m", msg], cwd=repo_root)
    
    # Push main
    run_cmd(["git", "push", "origin", "main"], cwd=repo_root)
    
    # Tag
    tag_name = f"v{version}"
    run_cmd(["git", "tag", tag_name], cwd=repo_root)
    
    # Push tag
    run_cmd(["git", "push", "origin", tag_name], cwd=repo_root)
    
    print(f"Successfully published {tag_name}!")
    print("GitHub Actions will now build and publish the release to PyPI.")

if __name__ == "__main__":
    main()
