"""
ki_utils.py

Core utilities for ki-manager: registry management, path resolution,
configuration loading. Shared by server.py and all subprocess scripts.

Folder convention: <project>/.ki-base/ (replaces legacy .know/)
  - .ki-base/ki_config.json  → project settings (in git)
  - .ki-base/config.json     → machine-specific (in .gitignore)
  - .ki-base/doc_config.json → file→KI mapping (in git)
"""

import os
import sys
import json
import argparse
from pathlib import Path

# Global state — set by MCP server on initialize
ACTIVE_WORKSPACE_PATH = None
_CACHE = {}

KI_BASE_DIR = ".ki-base"          # canonical project folder name


def normalize_path(path_str: str, make_absolute: bool = True) -> str:
    """Normalizes paths, decoding file:// URIs and standardizing slashes."""
    if not path_str:
        return ""

    is_uri = False
    if path_str.startswith("file:"):
        is_uri = True
        from urllib.parse import urlparse, unquote
        try:
            parsed = urlparse(path_str)
            decoded_path = unquote(parsed.path)
            if os.name == "nt" and decoded_path.startswith("/") and len(decoded_path) > 2 \
                    and decoded_path[1].isalpha() and decoded_path[2] == ":":
                decoded_path = decoded_path[1:]
            path_str = decoded_path
        except Exception:
            path_str = path_str.replace("file:///", "").replace("file://", "").replace("file:", "")
            from urllib.parse import unquote
            path_str = unquote(path_str)

    path_str = os.path.normpath(path_str)

    if make_absolute:
        path_str = os.path.abspath(path_str)
    else:
        if is_uri or os.path.isabs(path_str) or (os.name == "nt" and len(path_str) > 1 and path_str[1] == ":"):
            path_str = os.path.abspath(path_str)

    return path_str


# ─── Registry Management ─────────────────────────────────────────────────────

def get_registry_path() -> Path:
    """Returns path to the global KI registry (~/.ki_base/registry.json)."""
    base_dir = Path.home() / ".ki_base"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "registry.json"


def load_registry() -> dict:
    path = get_registry_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "projects" not in data:
                    data["projects"] = {}
                return data
        except Exception:
            pass
    return {"projects": {}}


def save_registry(registry: dict):
    with open(get_registry_path(), "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=4, ensure_ascii=False)


def register_project(config_path: str):
    """Adds a project to the global registry. config_path must point to ki_config.json."""
    config_path = normalize_path(config_path)
    if not os.path.exists(config_path):
        return False, f"Config not found: {config_path}"

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        return False, f"Invalid JSON in config: {str(e)}"

    # Structure: <project_root>/.ki-base/ki_config.json
    ki_base_root = os.path.dirname(config_path)   # .ki-base/
    proj_root = os.path.dirname(ki_base_root)      # project root

    registry = load_registry()
    proj_root = os.path.normpath(proj_root)

    registry["projects"][proj_root] = {
        "config_path": config_path,
        "know_root": ki_base_root,
        "name": os.path.basename(proj_root),
        "last_registered": os.path.getmtime(config_path),
    }
    save_registry(registry)
    return True, f"Project '{os.path.basename(proj_root)}' registered at {proj_root}"


def find_project_by_cwd(cwd=None) -> dict:
    """Finds the registered project that contains the given CWD."""
    if not cwd:
        cwd = ACTIVE_WORKSPACE_PATH or os.getcwd()
    cwd = normalize_path(cwd)

    registry = load_registry()
    best_match = None
    max_len = -1

    for proj_root, data in registry["projects"].items():
        norm_proj = normalize_path(proj_root)
        if os.path.normcase(cwd).startswith(os.path.normcase(norm_proj)):
            if len(norm_proj) > max_len:
                max_len = len(norm_proj)
                best_match = data

    return best_match


# ─── Configuration Loading ────────────────────────────────────────────────────

def load_ki_config() -> dict:
    """
    Loads ki_config.json for the active project.
    Resolution order:
      1. --config CLI argument
      2. Global registry lookup by CWD / ACTIVE_WORKSPACE_PATH
      3. Recursive filesystem search for .ki-base/ki_config.json
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=str)
    parser.add_argument("--workspace", type=str)
    args, _ = parser.parse_known_args()

    config_path = None

    # Priority 0: --workspace sets ACTIVE_WORKSPACE_PATH
    global ACTIVE_WORKSPACE_PATH
    if args.workspace:
        ACTIVE_WORKSPACE_PATH = normalize_path(args.workspace)

    # Priority 1: explicit --config
    if args.config:
        norm_arg = normalize_path(args.config)
        if os.path.exists(norm_arg):
            config_path = norm_arg
            if os.path.isdir(config_path):
                config_path = os.path.join(config_path, "ki_config.json")

    # Priority 2: registry
    if not config_path:
        match = find_project_by_cwd()
        if match:
            config_path = match["config_path"]

    # Priority 3: filesystem walk
    if not config_path:
        current = Path(ACTIVE_WORKSPACE_PATH) if ACTIVE_WORKSPACE_PATH else Path.cwd()
        for parent in [current] + list(current.parents):
            check_path = parent / KI_BASE_DIR / "ki_config.json"
            if check_path.exists():
                config_path = str(check_path)
                break
            # Legacy fallback
            check_path = parent / ".know" / "ki_config.json"
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


# ─── Path Resolution ──────────────────────────────────────────────────────────

def get_ki_cfg() -> dict:
    return load_ki_config()


def get_knowledge_root() -> str:
    """Returns the .ki-base/ directory path for the active project."""
    cfg = get_ki_cfg()
    loaded_from = cfg.get("_loaded_from")
    if loaded_from:
        return os.path.dirname(loaded_from)
    return ""


def get_project_root() -> str:
    """Returns the project root (parent of .ki-base/)."""
    know_root = get_knowledge_root()
    if not know_root:
        return os.getcwd()
    return os.path.dirname(know_root)


def get_doc_config_path() -> str:
    root = get_knowledge_root()
    return os.path.join(root, "doc_config.json") if root else ""


def get_doc_config() -> dict:
    root = get_knowledge_root()
    if not root:
        return {}
    path = os.path.join(root, "doc_config.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def get_python_exe() -> str:
    """Returns venv python from config.json (machine-specific) or ki_config.json."""
    # First try machine-specific config.json
    root = get_knowledge_root()
    if root:
        config_json = os.path.join(root, "config.json")
        if os.path.exists(config_json):
            try:
                with open(config_json, "r", encoding="utf-8") as f:
                    local_cfg = json.load(f)
                venv_py = local_cfg.get("venv_python")
                if venv_py and os.path.exists(venv_py):
                    return venv_py
            except Exception:
                pass
    # Fallback: ki_config.json paths section (legacy)
    return get_ki_cfg().get("paths", {}).get("venv_python") or sys.executable


def get_instructions() -> str:
    root = get_knowledge_root()
    if not root:
        return "No active project context."
    # AGENTS.md is now in .ki-base/ directly
    agents_path = os.path.join(root, "AGENTS.md")
    if os.path.exists(agents_path):
        with open(agents_path, "r", encoding="utf-8") as f:
            return f.read()
    return "AGENTS.md not found in .ki-base/."


def get_ki_list_table() -> str:
    """Returns a markdown table of all registered Knowledge Items."""
    doc_config = get_doc_config()
    items = doc_config.get("knowledge_items", {})
    if not items:
        return "No Knowledge Items registered yet."
    rows = ["| File | Summary |", "|------|---------|"]
    for name, info in sorted(items.items()):
        summary = info.get("summary", info.get("description", "—"))
        rows.append(f"| `{name}` | {summary} |")
    return "\n".join(rows)
