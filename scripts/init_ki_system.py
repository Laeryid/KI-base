import os
import json
import sys
import argparse
from pathlib import Path

# Fixed English sections injected into AGENTS.md during initialization
FORCED_EFFICIENCY_EN = """
## Forced Efficiency (Anti-Hallucinations)

1. **Mandatory Planning Template**:
   Before making code changes, your initial plan (Implementation Plan) **MUST** include the following block:
   - **Affected layers**: [which subsystems are affected]
   - **Read KIs**: [LIST of files from `.know/knowledge/` which you read via `view_file` for this task]. *If the list is empty — read KIs before writing code!*
   - **KIs Constraints**: [which approaches are prohibited by current architecture]

2. **Mandatory validation (Linter)**:
   After every save or modification of a `.py` file, you **MUST** check it for syntax errors:
   ```powershell
   .venv\\Scripts\\python.exe -m py_compile <full_path_to_file.py>
   ```
   You are not allowed to proceed to the next steps until you fix the found `SyntaxError`.

3. **Guardrails (Critical Triggers)**:
   - **Stop-word: `async/await`**. If you are about to add `async/await` inside a synchronous method to call a database or file, **STOP**. Cascading forced asynchrony of synchronous reducers is PROHIBITED.
"""

PROJECT_NAVIGATION_EN = """
## Project Navigation

- **`DIR_INDEX.md`** (`.know/DIR_INDEX.md`) — project directory tree.
- **`doc_config.json`** (`.know/doc_config.json`) — manifest of tracked artifacts and their dependencies on code.
"""

KNOWLEDGE_ITEMS_EN = """
## Knowledge Items (KI)

Before starting work — **be sure to read** the relevant KIs in `.know/knowledge/`:

| File | Topic |
|------|-------|
"""


def detect_venv(root_dir):
    """Tries to find venv and returns the path to python.exe / python."""
    common_names = [".venv", "venv", "env"]
    for name in common_names:
        # Windows
        py_exe = Path(root_dir) / name / "Scripts" / "python.exe"
        if py_exe.exists():
            return str(py_exe)
        # Linux / macOS
        py_unix = Path(root_dir) / name / "bin" / "python"
        if py_unix.exists():
            return str(py_unix)
    return sys.executable


def find_project_root():
    """Determines the project root by looking for .git or a known knowledge folder."""
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / ".git").exists():
            return parent
        # If this script lives inside the knowledge folder (e.g. .know/scripts/)
        # the project root is two levels up
        if (parent.parent / "doc_config.json").exists():
            return parent.parent
    return current


def update_gitignore(project_root, knowledge_root_name):
    """Adds KI_base ignore rules to .gitignore."""
    gitignore_path = Path(project_root) / ".gitignore"

    rules = [
        f"\n# KI_base: ignore service files, keep only knowledge data",
        f"{knowledge_root_name}/__pycache__/",
        f"{knowledge_root_name}/ki_config.json",
        f"{knowledge_root_name}/doc_state.json",
        f"{knowledge_root_name}/coverage_matrix.md",
        f"{knowledge_root_name}/tests/__pycache__/",
    ]

    content = ""
    if gitignore_path.exists():
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()

    marker = f"{knowledge_root_name}/ki_config.json"
    if marker in content:
        print(f"[~] .gitignore already contains rules for '{knowledge_root_name}'. Skipping.")
        return

    print(f"[+] Updating {gitignore_path}...")
    with open(gitignore_path, "a", encoding="utf-8") as f:
        if content and not content.endswith("\n"):
            f.write("\n")
        f.write("\n".join(rules) + "\n")


def update_agent_instructions(agent_file, sections):
    """Adds missing sections to AGENTS.md."""
    if not os.path.exists(agent_file):
        print(f"[!] {agent_file} not found. Skipping instructions update.")
        return False

    with open(agent_file, "r", encoding="utf-8") as f:
        content = f.read()

    modified = False
    for header, text in sections.items():
        if header not in content:
            print(f"[+] Adding section: {header}")
            content = content.rstrip() + "\n\n" + text.strip() + "\n"
            modified = True

    if modified:
        with open(agent_file, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    return False


def init_ki_system():
    print("[*] Initializing Knowledge Infrastructure...")

    project_root = find_project_root()
    os.chdir(project_root)
    print(f"[+] Project root detected: {project_root}")

    parser = argparse.ArgumentParser(description="Knowledge system initialization.")
    parser.add_argument("--root", default=".know",
                        help="Knowledge folder name relative to project root (default: .know)")
    parser.add_argument("--agents", default="AGENTS.md",
                        help="Path to the agent instructions file (default: AGENTS.md)")
    parser.add_argument("--workflows", default=None,
                        help="Path to the IDE workflows directory (default: auto-detect)")
    args = parser.parse_args()

    knowledge_root_name = args.root
    knowledge_root = os.path.join(str(project_root), knowledge_root_name)
    print(f"[+] Knowledge root: {knowledge_root}")

    agent_file = args.agents
    print(f"[+] Agent instructions file: {agent_file}")

    workflows_dir = args.workflows
    if not workflows_dir:
        for d in [".agent/workflows", ".github/workflows", "workflows"]:
            if os.path.isdir(os.path.join(str(project_root), d)):
                workflows_dir = d
                break
    workflows_dir = workflows_dir or ".agent/workflows"
    print(f"[+] Workflows directory: {workflows_dir}")

    venv_py = detect_venv(project_root)
    print(f"[+] Python interpreter: {venv_py}")

    # Write ki_config.json into the knowledge root
    config = {
        "paths": {
            "knowledge_root": knowledge_root_name,
            "agent_instructions": agent_file,
            "workflows_dir": workflows_dir,
            "venv_python": venv_py
        },
        "auto_resolve": True
    }

    os.makedirs(knowledge_root, exist_ok=True)
    config_path = os.path.join(knowledge_root, "ki_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    print(f"[+] {config_path} created.")

    # Update AGENTS.md
    sections_to_check = {
        "## Forced Efficiency (Anti-Hallucinations)": FORCED_EFFICIENCY_EN,
        "## Project Navigation": PROJECT_NAVIGATION_EN,
        "## Knowledge Items (KI)": KNOWLEDGE_ITEMS_EN,
    }
    if update_agent_instructions(agent_file, sections_to_check):
        print(f"[+] {agent_file} updated with required sections.")
    else:
        print(f"[~] {agent_file} already contains all required sections.")

    # Update .gitignore
    update_gitignore(project_root, knowledge_root_name)

    if not os.path.exists(os.path.join(knowledge_root, "doc_config.json")):
        print(f"[!] Warning: doc_config.json not found in {knowledge_root}.")
        print(f"    Make sure you copied the full KI_base contents into '{knowledge_root_name}/'.")

    # Print MCP connection instructions
    mcp_script = os.path.join(knowledge_root_name, "scripts", "knowledge_mcp.py")
    print("\n[!] To activate KnowledgeManager in your IDE (Cursor/Windsurf/Claude), add this to your MCP config:")
    print(f'    "command": "{venv_py}"')
    print(f'    "args": ["{mcp_script}", "--config", "{config_path}"]')
    print("-" * 60)
    print("[*] Initialization complete.")


if __name__ == "__main__":
    init_ki_system()
