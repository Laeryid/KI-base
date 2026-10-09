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
import re
import tempfile
import argparse
import fnmatch
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


def register_project(config_path: str = None, workspace: str = None, inline_config: dict = None):
    """Adds a project to the global registry."""
    if not config_path and not workspace:
        return False, "Must provide config_path or workspace"

    if config_path:
        config_path = normalize_path(config_path)
        if not os.path.exists(config_path):
            return False, f"Config not found: {config_path}"
        try:
            import json
            with open(config_path, "r", encoding="utf-8") as f:
                json.load(f)
        except Exception as e:
            return False, f"Invalid JSON in config: {str(e)}"
        
        if not workspace:
            parent = os.path.dirname(config_path)
            if os.path.basename(parent) in (".ki-base", ".know", ".config", "config"):
                workspace = os.path.dirname(parent)
            else:
                workspace = parent
    
    workspace = normalize_path(workspace)
    registry = load_registry()
    
    entry = {
        "name": os.path.basename(workspace),
        "last_registered": __import__("time").time()
    }
    if config_path:
        entry["config_path"] = config_path
    if inline_config is not None:
        entry["config"] = inline_config
        
    registry["projects"][workspace] = entry
    save_registry(registry)
    return True, f"Project '{entry['name']}' registered at {workspace}"


def find_project_by_cwd(cwd=None) -> dict:
    """Finds the registered project that contains the given CWD."""
    if not cwd:
        cwd = ACTIVE_WORKSPACE_PATH or os.getcwd()
    cwd = normalize_path(cwd)

    registry = load_registry()
    best_match = None
    max_len = -1
    best_proj = None

    for proj_root, data in registry["projects"].items():
        norm_proj = normalize_path(proj_root)
        if os.path.normcase(cwd).startswith(os.path.normcase(norm_proj)):
            if len(norm_proj) > max_len:
                max_len = len(norm_proj)
                best_match = data
                best_proj = proj_root

    if best_match:
        best_match["workspace"] = best_proj
    return best_match


# ─── Configuration Loading ────────────────────────────────────────────────────

def load_ki_config() -> dict:
    """
    Loads ki_config.json and/or registry inline config for the active project.
    """
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=str)
    parser.add_argument("--workspace", type=str)
    args, _ = parser.parse_known_args()

    config_path = None
    inline_config = {}
    registry_workspace = None

    global ACTIVE_WORKSPACE_PATH
    if args.workspace:
        ACTIVE_WORKSPACE_PATH = normalize_path(args.workspace)

    if args.config:
        norm_arg = normalize_path(args.config)
        if os.path.exists(norm_arg):
            config_path = norm_arg
            if os.path.isdir(config_path):
                config_path = os.path.join(config_path, "ki_config.json")

    if not config_path:
        match = find_project_by_cwd()
        if match:
            config_path = match.get("config_path")
            inline_config = match.get("config", {})
            registry_workspace = match.get("workspace")

    if not config_path and not inline_config:
        current = Path(ACTIVE_WORKSPACE_PATH) if ACTIVE_WORKSPACE_PATH else Path.cwd()
        for parent in [current] + list(current.parents):
            for candidate in [
                parent / KI_BASE_DIR / "ki_config.json",
                parent / "ki_config.json",
                parent / ".config" / "ki_config.json",
                parent / "config" / "ki_config.json",
                parent / ".know" / "ki_config.json"
            ]:
                if candidate.exists():
                    config_path = str(candidate)
                    break
            if config_path:
                break

    cfg = {}
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                cfg["_loaded_from"] = config_path
        except Exception:
            pass
    
    if inline_config:
        for k, v in inline_config.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
        if registry_workspace and "_project_root" not in cfg:
            cfg["_project_root"] = registry_workspace

    return cfg


# ─── Path Resolution ──────────────────────────────────────────────────────────

def get_ki_cfg() -> dict:
    return load_ki_config()


def get_knowledge_root() -> str:
    """Returns the knowledge directory path for the active project."""
    if "knowledge_root" in _CACHE:
        return _CACHE["knowledge_root"]

    cfg = get_ki_cfg()
    if not cfg:
        return ""

    know_root = cfg.get("paths", {}).get("knowledge_root")
    if know_root:
        if os.path.isabs(know_root):
            return know_root
        return os.path.join(get_project_root(), know_root)

    # Fallback to config path
    loaded_from = cfg.get("_loaded_from")
    if loaded_from:
        parent = os.path.dirname(loaded_from)
        basename = os.path.basename(parent)
        if basename in (".ki-base", ".know"):
            return parent
        return os.path.join(get_project_root(), KI_BASE_DIR)

    if "_project_root" in cfg:
        return os.path.join(cfg["_project_root"], KI_BASE_DIR)

    return ""

def get_project_root() -> str:
    """Returns the absolute path to the project root."""
    cfg = get_ki_cfg()
    if "_project_root" in cfg:
        return cfg["_project_root"]
        
    loaded_from = cfg.get("_loaded_from")
    if loaded_from:
        parent = os.path.dirname(loaded_from)
        if os.path.basename(parent) in (".ki-base", ".know", ".config", "config"):
            return os.path.dirname(parent)
        return parent
        
    if ACTIVE_WORKSPACE_PATH:
        return ACTIVE_WORKSPACE_PATH
        
    match = find_project_by_cwd()
    if match and match.get("workspace"):
        return match["workspace"]
    
    return os.getcwd()


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


def get_local_config() -> dict:
    """Loads machine-specific config.json if present in knowledge_root."""
    root = get_knowledge_root()
    if root:
        config_json = os.path.join(root, "config.json")
        if os.path.exists(config_json):
            try:
                with open(config_json, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


DEFAULT_EXCLUDED_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}


def get_exclude_patterns() -> set:
    """
    Returns the set of directory/file exclude patterns.
    Combines default excluded dirs with exclude_patterns from:
    1. config.json (machine-specific)
    2. doc_config.json (coverage_settings.exclude_patterns or top-level exclude_patterns)
    3. ki_config.json
    """
    patterns = set(DEFAULT_EXCLUDED_DIRS)

    # 1. config.json
    local_cfg = get_local_config()
    for p in local_cfg.get("exclude_patterns", []):
        if p:
            patterns.add(str(p))

    # 2. doc_config.json
    doc_cfg = get_doc_config()
    for p in doc_cfg.get("exclude_patterns", []):
        if p:
            patterns.add(str(p))
    for p in doc_cfg.get("coverage_settings", {}).get("exclude_patterns", []):
        if p:
            patterns.add(str(p))

    # 3. ki_config.json
    ki_cfg = get_ki_cfg()
    for p in ki_cfg.get("exclude_patterns", []):
        if p:
            patterns.add(str(p))

    return patterns


def should_exclude(name: str, rel_path: str = "", patterns: set = None) -> bool:
    """
    Checks if a file or directory name/path matches any exclude pattern.
    Supports exact name match, component match, and glob pattern (fnmatch).
    """
    if patterns is None:
        patterns = get_exclude_patterns()

    if name in patterns:
        return True

    norm_rel = rel_path.replace("\\", "/").strip("/") if rel_path else ""

    for pat in patterns:
        if fnmatch.fnmatch(name, pat):
            return True
        if norm_rel:
            norm_pat = pat.replace("\\", "/").strip("/")
            if norm_rel == norm_pat or norm_rel.startswith(norm_pat + "/"):
                return True
            if fnmatch.fnmatch(norm_rel, norm_pat):
                return True
            if any(fnmatch.fnmatch(comp, pat) for comp in norm_rel.split("/")):
                return True

    return False


def get_python_exe() -> str:
    """Returns venv python from config.json (machine-specific) or ki_config.json."""
    local_cfg = get_local_config()
    venv_py = local_cfg.get("venv_python")
    if venv_py and os.path.exists(venv_py):
        return venv_py
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
    rows = ["| File | Topic / Summary |", "|------|-----------------|"]
    for name, info in sorted(items.items()):
        summary = info.get("summary", info.get("description", "—"))
        rows.append(f"| `{name}` | {summary} |")
    return "\n".join(rows)


def save_doc_config(config: dict) -> str:
    """Atomically saves doc_config.json for the active project."""
    path = get_doc_config_path()
    if not path:
        raise ValueError("doc_config.json path could not be resolved.")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    return path


def is_sync_agents_md_enabled() -> bool:
    """Checks whether sync_agents_md is enabled in ki_config.json (default: True)."""
    cfg = get_ki_cfg()
    return bool(cfg.get("sync_agents_md", True))


def get_decisions_dirs(project_root: str = None, jail: str = None) -> list:
    """Returns candidate directories where ADRs can be stored."""
    if not project_root:
        project_root = get_project_root()
    if not jail:
        jail = get_knowledge_root()
    dirs = []
    if project_root:
        dirs.append(os.path.join(project_root, "decisions"))
    if jail and (not project_root or os.path.normcase(jail) != os.path.normcase(project_root)):
        dirs.append(os.path.join(jail, "decisions"))
    return dirs


def parse_adr_file(filepath: str, project_root: str = None) -> dict:
    """Parses metadata from an ADR markdown file."""
    if not project_root:
        project_root = get_project_root()
    filename = os.path.basename(filepath)
    rel_path = os.path.relpath(filepath, project_root).replace("\\", "/") if project_root else filename

    title = filename
    status = "Accepted"
    date = "—"
    summary = "—"
    adr_id = "—"

    m_id = re.match(r"^(\d+)", filename)
    if m_id:
        adr_id = m_id.group(1)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        content = ""

    # Parse title
    m_title = re.search(r"^#\s+(?:ADR\s*\d*[:\-]?\s*)?([^\n\r]+)", content, re.MULTILINE)
    if m_title:
        title = m_title.group(1).strip()

    # Parse status
    m_status = re.search(r"<!--\s*status:\s*([^\n\r>]+?)\s*-->", content, re.IGNORECASE)
    if not m_status:
        m_status = re.search(r"\*\*Status\*\*:\s*([^\n\r]+)", content, re.IGNORECASE)
    if not m_status:
        m_status = re.search(r"^Status:\s*([^\n\r]+)", content, re.MULTILINE | re.IGNORECASE)
    if m_status:
        status = m_status.group(1).strip()

    # Parse date
    m_date = re.search(r"<!--\s*created:\s*([^\n\r>]+?)\s*-->", content, re.IGNORECASE)
    if not m_date:
        m_date = re.search(r"\*\*Date\*\*:\s*([^\n\r]+)", content, re.IGNORECASE)
    if not m_date:
        m_date = re.search(r"^Date:\s*([^\n\r]+)", content, re.MULTILINE | re.IGNORECASE)
    if m_date:
        date = m_date.group(1).strip()

    # Parse summary / context
    m_ctx = re.search(r"##\s*(?:Context|Контекст)[^\n\r]*\n+([\s\S]*?)(?=\n##|\Z)", content, re.IGNORECASE)
    if m_ctx:
        ctx_lines = [l.strip() for l in m_ctx.group(1).splitlines() if l.strip() and not l.strip().startswith("<!--")]
        if ctx_lines:
            summary = ctx_lines[0]
            if len(summary) > 120:
                summary = summary[:117] + "..."

    # Parse supersedes
    supersedes = []
    m_sup = re.search(r"<!--\s*supersedes:\s*([^\n\r>]+?)\s*-->", content, re.IGNORECASE)
    if not m_sup:
        m_sup = re.search(r"\*\*Supersedes\*\*:\s*([^\n\r]+)", content, re.IGNORECASE)
    if m_sup:
        # Extract numeric IDs or file references
        raw_sup = m_sup.group(1)
        for s in re.findall(r"\b\d{3}\b|\b\d+\b", raw_sup):
            if s not in supersedes:
                supersedes.append(s.zfill(3) if s.isdigit() else s)

    return {
        "id": adr_id,
        "title": title,
        "status": status,
        "date": date,
        "summary": summary,
        "file": filename,
        "rel_path": rel_path,
        "abs_path": filepath,
        "supersedes": supersedes
    }


def get_adr_table(project_root: str = None, jail: str = None) -> str:
    """Dynamically scans for ADR files and formats a structured Markdown table."""
    if not project_root:
        project_root = get_project_root()
    if not jail:
        jail = get_knowledge_root()

    candidates = get_decisions_dirs(project_root, jail)
    adr_records = []
    seen_files = set()

    for c in candidates:
        if os.path.exists(c) and os.path.isdir(c):
            for f in sorted(os.listdir(c)):
                if f.endswith(".md") and f not in seen_files:
                    seen_files.add(f)
                    full_p = os.path.join(c, f)
                    adr_records.append(parse_adr_file(full_p, project_root))

    if not adr_records:
        return "No ADRs found in this project."

    # Sort by numeric ID or filename
    def _sort_key(r):
        num = int(r["id"]) if r["id"].isdigit() else 999999
        return (num, r["file"])

    adr_records.sort(key=_sort_key)

    rows = [
        "| ID | Title | Status | Date | File |",
        "|----|-------|--------|------|------|"
    ]
    for r in adr_records:
        link = f"[{r['file']}]({r['rel_path']})"
        rows.append(f"| {r['id']} | {r['title']} | {r['status']} | {r['date']} | {link} |")

    return "\n".join(rows)


def get_adr_list(project_root: str = None, jail: str = None) -> str:
    """Dynamic ADR list representation."""
    return get_adr_table(project_root, jail)
