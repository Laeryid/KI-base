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


def find_knowledge_root():
    """Determines the knowledge root (where doc_config.json lives)."""
    # If this script lives inside the scripts/ folder
    current = Path(__file__).resolve().parent.parent
    if (current / "doc_config.json").exists():
        return current
    
    # Fallback to current directory or parents
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "doc_config.json").exists():
            return parent
    return current


def init_ki_system():
    print("[*] Initializing Knowledge Infrastructure...")

    knowledge_root = find_knowledge_root()
    knowledge_root_name = knowledge_root.name
    print(f"[+] Knowledge root detected: {knowledge_root}")

    parser = argparse.ArgumentParser(description="Knowledge system initialization.")
    parser.add_argument("--project-root", default=None,
                        help="Path to the project root (default: one level above knowledge root)")
    parser.add_argument("--agents", default="AGENTS.md",
                        help="Path to the agent instructions file (default: AGENTS.md)")
    parser.add_argument("--workflows", default=None,
                        help="Path to the IDE workflows directory (default: auto-detect)")
    parser.add_argument("--root-name", default=None,
                        help="Override knowledge root name in config (default: detected folder name)")
    args = parser.parse_known_args()[0]

    project_root = Path(args.project_root).resolve() if args.project_root else knowledge_root.parent
    print(f"[+] Project root: {project_root}")

    os.chdir(project_root)

    knowledge_root_rel = os.path.relpath(knowledge_root, project_root)
    knowledge_root_name = args.root_name or knowledge_root_rel

    agent_file = args.agents
    print(f"[+] Agent instructions file: {agent_file}")

    workflows_dir = args.workflows
    if not workflows_dir:
        for d in [".agent/workflows", ".github/workflows", "workflows"]:
            if (project_root / d).is_dir():
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
            "project_root": "..", # Default relative to KNOWLEDGE_ROOT
            "agent_instructions": agent_file,
            "workflows_dir": workflows_dir,
            "venv_python": venv_py
        },
        "auto_resolve": True
    }

    # If project root is NOT parent of knowledge root, save it as absolute or custom relative
    if project_root != knowledge_root.parent:
        config["paths"]["project_root"] = os.path.relpath(project_root, knowledge_root)

    config_path = knowledge_root / "ki_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    print(f"[+] {config_path} created.")

    # Update AGENTS.md
    sections_to_check = {
        "## Forced Efficiency (Anti-Hallucinations)": FORCED_EFFICIENCY_EN,
        "## Project Navigation": PROJECT_NAVIGATION_EN,
        "## Knowledge Items (KI)": KNOWLEDGE_ITEMS_EN,
    }
    
    # Try finding AGENTS.md in project root or relative
    agent_path = project_root / agent_file
    if update_agent_instructions(str(agent_path), sections_to_check):
        print(f"[+] {agent_path} updated with required sections.")
    else:
        # Check if it was skipped or already has sections
        if os.path.exists(agent_path):
             print(f"[~] {agent_path} already contains all required sections.")

    # Update .gitignore in project root
    update_gitignore(project_root, knowledge_root_name)

    if not (knowledge_root / "doc_config.json").exists():
        print(f"[!] Warning: doc_config.json not found in {knowledge_root}.")
        print(f"    Make sure you copied the full KI_base contents into '{knowledge_root}'.")

    # Print MCP connection instructions
    mcp_script = os.path.abspath(os.path.join(str(knowledge_root), 'scripts', 'knowledge_mcp.py'))
    project_name = project_root.name
    
    print("\n" + "="*60)
    print("MCP CONFIGURATION INSTRUCTIONS")
    print("="*60)
    print("Add the following entry to your 'mcpServers' config file:")
    print(f"\n\"knowledge-manager-{project_name}\": {{")
    print(f"  \"command\": {json.dumps(str(venv_py))},")
    print(f"  \"args\": [")
    print(f"    {json.dumps(str(mcp_script))},")
    print(f"    \"--config\",")
    print(f"    {json.dumps(str(config_path))}")
    print(f"  ],")
    print(f"  \"cwd\": {json.dumps(str(project_root))}")
    print("}")
    print("-" * 60)
    print("[*] Initialization complete.")


if __name__ == "__main__":
    init_ki_system()
