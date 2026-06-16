import os
import json
import sys
import argparse
import secrets
import string
from pathlib import Path

# Add scripts dir to path to import ki_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils

def detect_venv(root_dir):
    """Tries to find venv and returns the path to python.exe / python."""
    common_names = [".venv", "venv", "env"]
    for name in common_names:
        # Windows
        py_exe = Path(root_dir) / name / "Scripts" / "python.exe"
        if py_exe.exists():
            return str(py_exe.as_posix())
        # Linux / macOS
        py_unix = Path(root_dir) / name / "bin" / "python"
        if py_unix.exists():
            return str(py_unix.as_posix())
    return str(Path(sys.executable).as_posix())


def setup_workflow_links(knowledge_root, project_root, workflows_rel_path):
    """Creates hard links for individual workflow files with collision handling."""
    know_workflows = Path(knowledge_root) / "workflows"
    target_dir = Path(project_root) / workflows_rel_path

    if not know_workflows.exists():
        print(f"[~] Source workflows directory not found: {know_workflows}. Skipping.")
        return

    if not target_dir.exists():
        print(f"[+] Creating target workflows directory: {target_dir}")
        target_dir.mkdir(parents=True, exist_ok=True)

    files_to_link = [f.name for f in know_workflows.glob("*.md")]
    
    if not files_to_link:
        print(f"[~] No .md files found in {know_workflows}. Skipping link creation.")
        return

    print(f"[*] Setting up workflow links in {target_dir}...")

    for filename in files_to_link:
        src_file = know_workflows / filename
        dst_file = target_dir / filename
        
        if dst_file.exists():
            try:
                if dst_file.stat().st_ino == src_file.stat().st_ino and dst_file.stat().st_dev == src_file.stat().st_dev:
                    print(f"[~] Hard link for {filename} already exists and is correct.")
                    continue
            except OSError:
                pass 
            
            suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
            name_parts = filename.rsplit(".", 1)
            new_filename = f"{name_parts[0]}_{suffix}.{name_parts[1]}" if len(name_parts) > 1 else f"{filename}_{suffix}"
            dst_file = target_dir / new_filename
            print(f"[!] Destination {filename} occupied. Using unique name: {new_filename}")

        try:
            os.link(src_file.resolve(), dst_file)
            print(f"[+] Created hard link: {dst_file.name} -> {filename}")
        except OSError as e:
            print(f"[!] Failed to create link for {filename}: {e}")


def find_knowledge_root():
    """Determines the knowledge root (where doc_config.json lives)."""
    # 1. Check current directory
    if (Path.cwd() / "doc_config.json").exists():
        return Path.cwd()
    if (Path.cwd() / ".know" / "doc_config.json").exists():
        return Path.cwd() / ".know"
        
    # 2. Existing logic
    current = Path(__file__).resolve().parent.parent
    if (current / "doc_config.json").exists():
        return current
    
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "doc_config.json").exists():
            return parent
    return current


def setup_gitignore(knowledge_root):
    """Generates .gitignore file inside .know directory."""
    gitignore_path = Path(knowledge_root) / ".gitignore"
    
    content = (
        "# KI_base: Project mode (ignore engine scripts/tests)\n"
        "/*\n"
        "!knowledge/\n"
        "!decisions/\n"
        "!doc_config.json\n"
        "!.gitignore\n"
        "\n"
        "# Ignore technical engine parts\n"
        "scripts/\n"
        "tests/\n"
        "workflows/\n"
        "ki_config.json\n"
        "\n"
        "# Ignore caches and temporary files\n"
        "__pycache__/\n"
        "*.py[cod]\n"
        "*$py.class\n"
        "doc_state.json\n"
    )
    
    with open(gitignore_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[+] {gitignore_path} updated.")


def init_ki_system():
    print("[*] Initializing Knowledge Infrastructure...")

    knowledge_root = find_knowledge_root()
    print(f"[+] Knowledge root detected: {knowledge_root}")

    parser = argparse.ArgumentParser(description="Knowledge system initialization.")
    parser.add_argument("--project-root", default=None, help="Path to the project root")
    parser.add_argument("--workflows", default=None, help="Path to workflows directory")
    args = parser.parse_known_args()[0]

    # Rule: PROJECT_ROOT is always 1 level above BASE_FOLDER (knowledge_root)
    project_root = Path(args.project_root).resolve() if args.project_root else knowledge_root.parent
    print(f"[+] Project root: {project_root}")

    venv_py = detect_venv(project_root)
    workflows_dir = args.workflows or ".agent/workflows"
    
    config_path = knowledge_root / "ki_config.json"
    existing_config = {}
    if config_path.exists():
        print(f"[~] Existing configuration found at {config_path}. Preserving settings.")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                existing_config = json.load(f)
        except Exception as e:
            print(f"[!] Error reading existing config: {e}")

    # Build updated config
    config = existing_config.copy()
    if "paths" not in config: config["paths"] = {}
    
    config["paths"].update({
        "knowledge_root": knowledge_root.name,
        "project_root": "..", # Always ".." because BASE_FOLDER is inside PROJECT_ROOT
        "agent_instructions": config["paths"].get("agent_instructions", "AGENTS.md"),
        "workflows_dir": workflows_dir,
        "venv_python": venv_py
    })
    
    config["auto_resolve"] = config.get("auto_resolve", True)
    
    if "knowledge_system" not in config:
        config["knowledge_system"] = {}
    
    config["knowledge_system"]["mcp_server"] = {
        "name": "KnowledgeManager",
        "version": "1.2.0"
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    print(f"[+] {config_path} updated.")

    # 1. Setup gitignore
    setup_gitignore(knowledge_root)

    # 2. Setup individual workflow links
    setup_workflow_links(knowledge_root, project_root, workflows_dir)

    # 3. Register in Global Registry
    print("[*] Registering project in global KI registry...")
    success, msg = ki_utils.register_project(str(config_path))
    if success:
        print(f"[+] {msg}")
    else:
        print(f"[!] Registration failed: {msg}")

    print("\n[*] Initialization complete. You can now use a single global MCP server for all your projects.")


if __name__ == "__main__":
    init_ki_system()
