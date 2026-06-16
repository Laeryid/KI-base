import os
import sys
import json
import argparse
from pathlib import Path

# --- Registry Management ---

def get_registry_path():
    """Returns the path to the global KI registry file."""
    base_dir = Path.home() / ".ki_base"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "registry.json"

def load_registry():
    path = get_registry_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "projects" not in data: data["projects"] = {}
                return data
        except Exception:
            pass
    return {"projects": {}}

def save_registry(registry):
    with open(get_registry_path(), "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=4, ensure_ascii=False)

def register_project(config_path):
    """Adds a project to the global registry."""
    config_path = os.path.abspath(config_path)
    if not os.path.exists(config_path):
        return False, f"Config not found: {config_path}"
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        return False, f"Invalid JSON in config: {str(e)}"
    
    # Logic: PROJECT_ROOT / BASE_FOLDER / ki_config.json
    # 1. BASE_FOLDER
    know_root = os.path.dirname(config_path) 
    # 2. PROJECT_ROOT (always 1 level above BASE_FOLDER)
    proj_root = os.path.dirname(know_root)
    
    registry = load_registry()
    proj_root = os.path.normpath(proj_root)
    
    registry["projects"][proj_root] = {
        "config_path": config_path,
        "know_root": know_root,
        "name": os.path.basename(proj_root),
        "last_registered": os.path.getmtime(config_path)
    }
    save_registry(registry)
    return True, f"Project '{os.path.basename(proj_root)}' registered at {proj_root}"

def find_project_by_cwd(cwd=None):
    """Finds the registered project that contains the given CWD."""
    if not cwd:
        cwd = os.getcwd()
    cwd = os.path.abspath(cwd)
    
    registry = load_registry()
    best_match = None
    max_len = -1
    
    for proj_root, data in registry["projects"].items():
        # Case-insensitive check for Windows paths
        if os.path.normcase(cwd).startswith(os.path.normcase(proj_root)):
            if len(proj_root) > max_len:
                max_len = len(proj_root)
                best_match = data
                
    return best_match

# --- Configuration Loading ---

def load_ki_config():
    """
    Loads configuration based on context.
    1. Check --config argument.
    2. Check Registry based on CWD.
    3. Fallback to local search.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=str)
    args, _ = parser.parse_known_args()

    config_path = None

    if args.config and os.path.exists(args.config):
        config_path = args.config
        if os.path.isdir(config_path):
            config_path = os.path.join(config_path, "ki_config.json")
    else:
        # Try Registry based on current CWD
        match = find_project_by_cwd()
        if match:
            config_path = match["config_path"]
        else:
            # Fallback recursive search
            current = Path.cwd()
            for parent in [current] + list(current.parents):
                check_path = parent / ".know" / "ki_config.json"
                if check_path.exists():
                    config_path = str(check_path)
                    break
                check_path = parent / "ki_config.json"
                if check_path.exists():
                    config_path = str(check_path)
                    break

    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                cfg["_loaded_from"] = config_path 
                return cfg
        except Exception:
            pass
    return {}

# --- Path Resolution (Context-Aware) ---

def get_ki_cfg():
    return load_ki_config()

def get_knowledge_root():
    cfg = get_ki_cfg()
    loaded_from = cfg.get("_loaded_from")
    if loaded_from:
        return os.path.dirname(loaded_from)
    return ""

def get_project_root():
    cfg = get_ki_cfg()
    know_root = get_knowledge_root()
    if not know_root:
        return os.getcwd()
    # In the new logic, PROJECT_ROOT is always parent of BASE_FOLDER (know_root)
    return os.path.dirname(know_root)

def get_doc_config():
    root = get_knowledge_root()
    if not root: return {}
    path = os.path.join(root, "doc_config.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def get_python_exe():
    return get_ki_cfg().get("paths", {}).get("venv_python") or sys.executable

def get_instructions():
    root = get_knowledge_root()
    if not root: return "No context."
    path = os.path.join(root, "scripts", "instructions.md")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "Instructions file not found."
