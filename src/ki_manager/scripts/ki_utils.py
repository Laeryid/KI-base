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
from typing import Optional, Dict, Any, List, Union, Tuple

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


def is_subpath(target: str, root: str) -> bool:
    """Checks whether target path is strictly within or equal to root directory."""
    if not target or not root:
        return False
    try:
        norm_t = os.path.normcase(os.path.abspath(target))
        norm_r = os.path.normcase(os.path.abspath(root))
        return os.path.commonpath([norm_t, norm_r]) == norm_r
    except (ValueError, OSError):
        return False


def is_ki_filename(name: str, include_overview: bool = False) -> bool:
    """Checks if a file name matches Knowledge Item convention (KI_*.md or *.ki.md)."""
    if not name or not name.endswith(".md"):
        return False
    base = os.path.basename(name)
    if not include_overview and base in ("_OVERVIEW.ki.md", "_OVERVIEW.md"):
        return False
    return base.startswith("KI_") or base.endswith(".ki.md")


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
        if is_subpath(cwd, norm_proj):
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
    if args.workspace and not ACTIVE_WORKSPACE_PATH:
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
            inline_config = match.get("config") or {}
            registry_workspace = match.get("workspace")

    if config_path:
        if os.path.basename(config_path).lower() == "doc_config.json":
            sibling_ki_cfg = os.path.join(os.path.dirname(config_path), "ki_config.json")
            if os.path.exists(sibling_ki_cfg):
                config_path = sibling_ki_cfg
        if not os.path.exists(config_path):
            config_path = None

    if not config_path:
        current = Path(ACTIVE_WORKSPACE_PATH) if ACTIVE_WORKSPACE_PATH else (
            Path(registry_workspace) if registry_workspace else Path.cwd()
        )
        search_dirs = [current] + list(current.parents)
        if registry_workspace:
            norm_reg_ws = normalize_path(registry_workspace)
            search_dirs = [d for d in search_dirs if is_subpath(str(d), norm_reg_ws)]
            if not search_dirs:
                search_dirs = [Path(norm_reg_ws)]

        for parent in search_dirs:
            for candidate in [
                parent / KI_BASE_DIR / "ki_config.json",
                parent / "ki_config.json",
                parent / ".know" / "ki_config.json",
                parent / ".config" / "ki_config.json",
                parent / "config" / "ki_config.json",
            ]:
                if candidate.exists():
                    config_path = str(candidate)
                    break
            if config_path:
                break

    cfg = {}
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8-sig") as f:
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
    cand = os.path.join(root, "doc_config.json") if root else ""
    if cand and os.path.exists(cand):
        return cand
    proj = get_project_root()
    if proj:
        for p in [os.path.join(proj, ".ki-base", "doc_config.json"), os.path.join(proj, "doc_config.json")]:
            if os.path.exists(p):
                return p
    return cand


def get_doc_config() -> dict:
    path = get_doc_config_path()
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def normalize_tracked_module(entry: Any) -> Tuple[str, str, int]:
    """
    Normalizes a tracked module entry to canonical (module_path, label, importance).
    Supports:
      - [path, label, importance] (canonical 3-tuple/list)
      - [path, label] (defaults importance to 5)
      - [path] (defaults label=path, importance=5)
      - "path" (defaults label=path, importance=5)
      - {"path": "...", "label": "...", "importance": 5}
    """
    if isinstance(entry, (list, tuple)):
        path = str(entry[0]).strip() if len(entry) > 0 and entry[0] is not None else ""
        label = str(entry[1]).strip() if len(entry) > 1 and entry[1] is not None else path
        importance = 5
        if len(entry) > 2 and entry[2] is not None:
            try:
                importance = int(entry[2])
            except (ValueError, TypeError):
                importance = 5
        return (path, label, importance)
    elif isinstance(entry, str):
        p = entry.strip()
        return (p, p, 5)
    elif isinstance(entry, dict):
        p = str(entry.get("path", "")).strip()
        l = str(entry.get("label", p)).strip() or p
        try:
            imp = int(entry.get("importance", 5))
        except (ValueError, TypeError):
            imp = 5
        return (p, l, imp)
    return ("", "", 5)


def get_tracked_modules(doc_config: Optional[dict] = None) -> List[Tuple[str, str, int]]:
    """
    Returns normalized tracked modules list [(module_path, label, importance), ...]
    from coverage_settings.tracked_modules or root tracked_modules.
    Filters out empty paths.
    """
    if doc_config is None:
        doc_config = get_doc_config()
    raw = doc_config.get("coverage_settings", {}).get("tracked_modules")
    if raw is None:
        raw = doc_config.get("tracked_modules", [])
    if not isinstance(raw, list):
        return []

    res = []
    for item in raw:
        norm = normalize_tracked_module(item)
        if norm[0]:
            res.append(norm)
    return res


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


def load_gitignore_patterns(project_root: str = None) -> set:
    """Parses .gitignore file in project_root if present, returning a set of pattern strings."""
    if not project_root:
        project_root = get_project_root()
    if not project_root or not os.path.isdir(project_root):
        return set()

    gitignore_path = os.path.join(project_root, ".gitignore")
    if not os.path.isfile(gitignore_path):
        return set()

    patterns = set()
    try:
        with open(gitignore_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("!"):
                    continue
                norm = line.replace("\\", "/").rstrip("/")
                if norm.startswith("/"):
                    norm = norm.lstrip("/")
                if norm:
                    patterns.add(norm)
    except Exception:
        pass
    return patterns


DEFAULT_EXCLUDED_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}

CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift", ".kt",
}


def get_exclude_patterns() -> set:
    """
    Returns the set of directory/file exclude patterns.
    Combines default excluded dirs with exclude_patterns, exclude, ignore_dirs, and exclude_dirs from:
    1. config.json (machine-specific)
    2. doc_config.json (coverage_settings and top-level)
    3. ki_config.json
    4. .gitignore in project root
    """
    patterns = set(DEFAULT_EXCLUDED_DIRS)

    def _add_from_cfg(cfg_dict, key):
        val = cfg_dict.get(key, [])
        if isinstance(val, list):
            for p in val:
                if p:
                    patterns.add(str(p))
        elif isinstance(val, str) and val:
            patterns.add(val)

    exclude_keys = ("exclude_patterns", "exclude", "ignore_dirs", "exclude_dirs")

    # 1. config.json
    local_cfg = get_local_config()
    for k in exclude_keys:
        _add_from_cfg(local_cfg, k)

    # 2. doc_config.json
    doc_cfg = get_doc_config()
    for k in exclude_keys:
        _add_from_cfg(doc_cfg, k)
    cov_cfg = doc_cfg.get("coverage_settings", {})
    if isinstance(cov_cfg, dict):
        for k in exclude_keys:
            _add_from_cfg(cov_cfg, k)

    # 3. ki_config.json
    ki_cfg = get_ki_cfg()
    for k in exclude_keys:
        _add_from_cfg(ki_cfg, k)

    # 4. .gitignore
    patterns.update(load_gitignore_patterns())

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
        norm_pat = pat.replace("\\", "/").strip("/")
        if not norm_pat:
            continue
        if fnmatch.fnmatch(name, norm_pat):
            return True
        if norm_rel:
            if norm_rel == norm_pat or norm_rel.startswith(norm_pat + "/"):
                return True
            if fnmatch.fnmatch(norm_rel, norm_pat):
                return True
            if any(fnmatch.fnmatch(comp, norm_pat) for comp in norm_rel.split("/")):
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


ADR_STATUSES = ("draft", "poc", "accepted", "superseded", "deprecated", "archived")
KI_STATUSES = ("stub", "draft", "poc", "active", "stale", "archived")
INACTIVE_STATUSES = frozenset({"superseded", "deprecated", "archived"})
ACTIVE_ADR_TABLE_STATUSES = frozenset({"accepted", "poc"})


def normalize_status(raw_status: Optional[str], doc_type: str = "adr") -> str:
    """Normalizes ADR or KI lifecycle status to canonical lowercase form."""
    raw = (raw_status or "").strip()
    if raw:
        raw = re.sub(r"^\[|\]$", "", raw.strip("`").strip()).strip()
    low = raw.lower()

    if doc_type == "adr":
        if not low:
            return "accepted"
        if low.startswith("superseded"):
            return "superseded"
        if low.startswith("deprecated"):
            return "deprecated"
        if low.startswith("archived"):
            return "archived"
        if low.startswith("proposed") or low.startswith("draft") or low == "wip":
            return "draft"
        if low.startswith("poc") or low in ("proof of concept", "experiment"):
            return "poc"
        if low.startswith("accepted") or low == "active":
            return "accepted"
        return low

    # doc_type == "ki"
    if not low:
        return "active"
    if low in ("active", "accepted", "verified"):
        return "active"
    if low.startswith("poc") or low in ("proof of concept", "experiment"):
        return "poc"
    if low.startswith("draft") or low.startswith("proposed") or low == "wip":
        return "draft"
    if low in ("stub", "scaffold"):
        return "stub"
    if low in ("stale", "outdated"):
        return "stale"
    if low in ("archived", "deprecated", "superseded") or low.startswith("superseded"):
        return "archived"
    return low


def _extract_frontmatter_field(content: str, field_name: str) -> Optional[str]:
    """Extracts a scalar field from YAML frontmatter at the top of markdown content."""
    if not content.startswith("---"):
        return None
    m_fm = re.match(r"^---\s*\n([\s\S]*?)\n---(?:\s*\n|\Z)", content)
    if not m_fm:
        return None
    pattern = rf"^{re.escape(field_name)}\s*:\s*([^\n\r]+)"
    m_val = re.search(pattern, m_fm.group(1), re.MULTILINE | re.IGNORECASE)
    if not m_val:
        return None
    return m_val.group(1).strip().strip('"').strip("'")


def extract_raw_status_from_content(content: str, doc_type: str = "adr") -> Optional[str]:
    """Extracts raw status string from HTML comments, YAML frontmatter, or Markdown headers."""
    if not content:
        return None
    m_status = re.search(r"<!--\s*status:\s*([^\n\r>]+?)\s*-->", content, re.IGNORECASE)
    if m_status:
        return m_status.group(1).strip()
    fm_status = _extract_frontmatter_field(content, "status")
    if fm_status:
        return fm_status
    m_status = re.search(r"\*\*Status\*\*:\s*([^\n\r]+)", content, re.IGNORECASE)
    if m_status:
        return m_status.group(1).strip()
    m_status = re.search(r"^Status:\s*([^\n\r]+)", content, re.MULTILINE | re.IGNORECASE)
    if m_status:
        return m_status.group(1).strip()
    if doc_type == "ki" and re.search(r"<!--\s*scaffold:\s*true\s*-->", content, re.IGNORECASE):
        return "stub"
    return None


def extract_status_from_content(content: str, doc_type: str = "adr") -> str:
    """Extracts and normalizes lifecycle status from markdown content."""
    raw = extract_raw_status_from_content(content, doc_type=doc_type)
    return normalize_status(raw, doc_type=doc_type)


def extract_superseded_by_from_content(content: str) -> Optional[str]:
    """Extracts the target ADR ID that superseded this document, if any."""
    if not content:
        return None
    m_meta = re.search(r"<!--\s*superseded_by:\s*([^\n\r>]+?)\s*-->", content, re.IGNORECASE)
    if m_meta:
        nums = re.findall(r"\d+", m_meta.group(1))
        if nums:
            return nums[0].zfill(3)
        val = m_meta.group(1).strip()
        return val or None

    fm_val = _extract_frontmatter_field(content, "superseded_by")
    if fm_val:
        nums = re.findall(r"\d+", fm_val)
        return nums[0].zfill(3) if nums else fm_val

    m_inline = re.search(r"superseded\s+by\s+\[?ADR[\s_\-]*(\d+)\]?", content, re.IGNORECASE)
    if m_inline:
        return m_inline.group(1).zfill(3)
    return None


def resolve_superseding_chain(adr_id: str, adr_records_or_map: Any) -> List[str]:
    """
    Follows superseded_by links transitively (with cycle protection) and returns
    the ordered chain of replacement ADR IDs (e.g. ['128', '129']).
    """
    if isinstance(adr_records_or_map, dict):
        adr_map = adr_records_or_map
    else:
        adr_map = {}
        for rec in adr_records_or_map or []:
            rid = str(rec.get("id", "")).strip()
            if rid:
                adr_map[rid] = rec
                if rid.isdigit():
                    adr_map[rid.lstrip("0") or "0"] = rec
                    adr_map[rid.zfill(3)] = rec

    start = str(adr_id).strip()
    if start.isdigit():
        start_norm = start.zfill(3)
    else:
        start_norm = start

    chain: List[str] = []
    visited = {start_norm}
    current = start_norm

    while True:
        rec = adr_map.get(current) or (adr_map.get(current.lstrip("0") or "0") if current.isdigit() else None)
        if not rec:
            break
        nxt = rec.get("superseded_by")
        if not nxt:
            break
        nxt_norm = nxt.zfill(3) if str(nxt).isdigit() else str(nxt).strip()
        if not nxt_norm or nxt_norm in visited:
            break
        chain.append(nxt_norm)
        visited.add(nxt_norm)
        current = nxt_norm

    return chain


def _resolve_ki_display_and_path(name: str, info: dict, jail: str, proj: str, dec_dirs: List[str]) -> Tuple[str, Optional[str]]:
    """Resolves display name and optional on-disk file path for a doc_config entry."""
    display_name = name
    found_path: Optional[str] = None

    if "path" in info and info["path"]:
        display_name = info["path"]

    search_roots = []
    if jail:
        search_roots.extend([jail, os.path.join(jail, "knowledge")])
    if proj:
        search_roots.append(proj)
    search_roots.extend(dec_dirs)

    candidates = [display_name, name]
    if re.match(r"^(?:ADR|adr)[_\-]", name):
        candidates.append(re.sub(r"^(?:ADR|adr)[_\-]", "", name))

    for cand in candidates:
        for root_cand in search_roots:
            if not root_cand:
                continue
            p = os.path.join(root_cand, cand)
            if os.path.isfile(p):
                found_path = p
                if cand != name and "path" not in info and any(os.path.normcase(os.path.dirname(p)) == os.path.normcase(d) for d in dec_dirs):
                    display_name = cand
                return display_name, found_path

    return display_name, found_path


def get_ki_status(ki_name: str, info: Optional[dict] = None, file_path: Optional[str] = None) -> str:
    """Determines canonical lifecycle status for a Knowledge Item (or config-tracked doc)."""
    info = info or {}
    is_adr = (
        "decisions/" in ki_name.replace("\\", "/").lower()
        or "decisions/" in str(info.get("path", "")).replace("\\", "/").lower()
        or bool(re.match(r"^(?:ADR[_\-])?\d+_", os.path.basename(ki_name)))
    )
    doc_type = "adr" if is_adr else "ki"

    if file_path and os.path.isfile(file_path):
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                head_content = f.read(4096)
            raw_in_file = extract_raw_status_from_content(head_content, doc_type=doc_type)
            if raw_in_file:
                return normalize_status(raw_in_file, doc_type=doc_type)
        except Exception:
            pass

    if info.get("status"):
        return normalize_status(str(info["status"]), doc_type=doc_type)

    return "accepted" if is_adr else "active"


def get_ki_list_table(include_archived: bool = False) -> str:
    """Returns a markdown table of active Knowledge Items (filtering archived by default)."""
    doc_config = get_doc_config()
    items = doc_config.get("knowledge_items", {})
    if not items:
        return "No Knowledge Items registered yet."
    jail = get_knowledge_root()
    proj = get_project_root()
    dec_dirs = get_decisions_dirs(proj, jail)

    rows = ["| File | Topic / Summary |", "|------|-----------------|"]
    archived_count = 0
    shown_count = 0

    for name, info in sorted(items.items()):
        summary = info.get("summary", info.get("description", "—"))
        display_name, file_path = _resolve_ki_display_and_path(name, info, jail, proj, dec_dirs)
        status = get_ki_status(name, info, file_path)

        if not include_archived and status in INACTIVE_STATUSES:
            archived_count += 1
            continue

        shown_count += 1
        status_tag = ""
        if status in ("poc", "stale", "draft", "stub"):
            status_tag = f"[{status.upper()}] "
        rows.append(f"| `{display_name}` | {status_tag}{summary} |")

    if shown_count == 0 and archived_count > 0:
        table = "No active Knowledge Items (all registered items are archived/superseded)."
    else:
        table = "\n".join(rows)

    if archived_count > 0:
        table += f"\n\n> *+ {archived_count} archived/inactive item(s) omitted. Call `ki_list(status=\"all\")` to view all.*"
    return table


def get_ki_list_data(
    scope: str = "all",
    filter_query: Optional[str] = None,
    status: str = "active",
) -> Dict[str, Any]:
    """Collects structured list of Knowledge Items and ADRs with optional filtering by text and lifecycle status."""
    jail = get_knowledge_root()
    proj = get_project_root()
    dec_dirs = get_decisions_dirs(proj, jail)
    doc_config = get_doc_config() or {}
    items = doc_config.get("knowledge_items", {})

    flt = filter_query.lower().strip() if filter_query else None
    req_status = (status or "active").strip().lower()

    def _matches_status(item_status: str) -> bool:
        if req_status in ("all", "*"):
            return True
        if req_status == "active":
            return item_status not in INACTIVE_STATUSES
        return item_status == normalize_status(req_status, "adr") or item_status == normalize_status(req_status, "ki")

    omitted_count = 0

    ki_list = []
    if scope in ("all", "ki"):
        for name, info in sorted(items.items()):
            summary = info.get("summary", info.get("description", "—"))
            covers = info.get("covers", [])
            display_name, file_path = _resolve_ki_display_and_path(name, info, jail, proj, dec_dirs)
            item_status = get_ki_status(name, info, file_path)

            if flt:
                covers_str = " ".join(covers).lower() if isinstance(covers, list) else str(covers).lower()
                if (
                    flt not in name.lower()
                    and flt not in summary.lower()
                    and flt not in covers_str
                    and flt not in display_name.lower()
                    and flt not in item_status.lower()
                ):
                    continue

            if not _matches_status(item_status):
                omitted_count += 1
                continue

            ki_list.append({
                "name": name,
                "path": display_name,
                "status": item_status,
                "summary": summary,
                "covers": covers,
                "type": "ki",
            })

    adr_list = []
    if scope in ("all", "adr"):
        adr_records = []
        seen_files = set()
        for c in dec_dirs:
            if os.path.exists(c) and os.path.isdir(c):
                for f in sorted(os.listdir(c)):
                    if f.endswith(".md") and f not in seen_files:
                        seen_files.add(f)
                        full_p = os.path.join(c, f)
                        adr_records.append(parse_adr_file(full_p, proj))

        def _sort_key(r):
            num = int(r["id"]) if r["id"].isdigit() else 999999
            return (num, r["file"])
        adr_records.sort(key=_sort_key)

        for r in adr_records:
            if flt:
                target_text = f"{r['id']} {r['title']} {r['summary']} {r['file']} {r['status']} {r.get('raw_status', '')}".lower()
                if flt not in target_text:
                    continue
            if not _matches_status(r["status"]):
                omitted_count += 1
                continue
            entry = {
                "id": r["id"],
                "title": r["title"],
                "status": r["status"],
                "date": r["date"],
                "summary": r["summary"],
                "file": r["file"],
                "rel_path": r["rel_path"],
                "type": "adr",
            }
            if r.get("superseded_by"):
                entry["superseded_by"] = r["superseded_by"]
            adr_list.append(entry)

    return {
        "scope": scope,
        "filter": filter_query,
        "status": req_status,
        "total_ki": len(ki_list),
        "total_adr": len(adr_list),
        "omitted_inactive": omitted_count,
        "knowledge_items": ki_list,
        "adrs": adr_list,
    }


def format_ki_list_markdown(data: Dict[str, Any]) -> str:
    """Formats KI and ADR list into clean Markdown tables."""
    scope = data.get("scope", "all")
    flt = data.get("filter")
    req_status = data.get("status", "active")
    ki_list = data.get("knowledge_items", [])
    adr_list = data.get("adrs", [])
    omitted = data.get("omitted_inactive", 0)

    sections = []
    flt_msg = f" matching '{flt}'" if flt else ""
    status_msg = f" (status={req_status})" if req_status and req_status != "active" else ""

    if scope in ("all", "ki"):
        if ki_list:
            rows = [
                f"### Knowledge Items ({len(ki_list)}){flt_msg}{status_msg}\n",
                "| File | Status | Summary / Topic | Covered Modules |",
                "|------|--------|-----------------|-----------------|"
            ]
            for item in ki_list:
                covers_str = ", ".join(f"`{c}`" for c in item.get("covers", [])) if item.get("covers") else "—"
                st = item.get("status", "active")
                rows.append(f"| `{item['path']}` | {st} | {item['summary']} | {covers_str} |")
            sections.append("\n".join(rows))
        else:
            sections.append(f"No Knowledge Items{flt_msg}{status_msg} found.")

    if scope in ("all", "adr"):
        if adr_list:
            rows = [
                f"### Architecture Decision Records ({len(adr_list)}){flt_msg}{status_msg}\n",
                "| ID | Title | Status | Date | File |",
                "|----|-------|--------|------|------|"
            ]
            for r in adr_list:
                link = f"[{r['file']}]({r['rel_path']})"
                st = r["status"]
                if r.get("superseded_by"):
                    st = f"{st} -> ADR {r['superseded_by']}"
                rows.append(f"| {r['id']} | {r['title']} | {st} | {r['date']} | {link} |")
            sections.append("\n".join(rows))
        elif scope == "adr":
            sections.append(f"No ADRs{flt_msg}{status_msg} found.")

    if omitted > 0:
        sections.append(f"> *+ {omitted} inactive item(s) omitted (superseded/deprecated/archived). Call `ki_list(status=\"all\")` to view all.*")

    return "\n\n".join(sections)


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
    val = cfg.get("sync_agents_md", True)
    if isinstance(val, str):
        return val.strip().lower() not in ("false", "0", "no", "off")
    return bool(val)


def is_auto_git_checkpoint_enabled() -> bool:
    """Checks whether git_checkpoint creates commits automatically (default: False)."""
    cfg = get_ki_cfg()
    return bool(cfg.get("auto_git_checkpoint", False))


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
    raw_status = "Accepted"
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

    # Parse status (normalized + raw)
    extracted_raw = extract_raw_status_from_content(content, doc_type="adr")
    if extracted_raw:
        raw_status = extracted_raw
    status = normalize_status(extracted_raw, doc_type="adr")
    superseded_by = extract_superseded_by_from_content(content)

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
        "raw_status": raw_status,
        "superseded_by": superseded_by,
        "date": date,
        "summary": summary,
        "file": filename,
        "rel_path": rel_path,
        "abs_path": filepath,
        "supersedes": supersedes
    }


def get_adr_table(project_root: str = None, jail: str = None, include_inactive: bool = False) -> str:
    """Dynamically scans for ADR files and formats a structured Markdown table (active ADRs by default)."""
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

    visible_records = []
    inactive_counts: Dict[str, int] = {}
    for r in adr_records:
        st = r["status"]
        if not include_inactive and st not in ACTIVE_ADR_TABLE_STATUSES:
            inactive_counts[st] = inactive_counts.get(st, 0) + 1
            continue
        visible_records.append(r)

    rows = []
    if visible_records:
        rows.extend([
            "| ID | Title | Status | Date | File |",
            "|----|-------|--------|------|------|"
        ])
        for r in visible_records:
            link = f"[{r['file']}]({r['rel_path']})"
            st = r["status"]
            if st == "poc":
                st_cell = "poc [POC]"
            elif st == "superseded" and r.get("superseded_by"):
                st_cell = f"superseded -> ADR {r['superseded_by']}"
            else:
                st_cell = st
            rows.append(f"| {r['id']} | {r['title']} | {st_cell} | {r['date']} | {link} |")
    else:
        rows.append("No active ADRs (all ADRs are draft/superseded/archived).")

    inactive_total = sum(inactive_counts.values())
    if inactive_total > 0:
        breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(inactive_counts.items()))
        rows.append("")
        rows.append(
            f"> *+ {inactive_total} inactive ADR(s) omitted ({breakdown}). "
            f'Call `ki_list(scope="adr", status="all")` to view all.*'
        )

    return "\n".join(rows)


def get_adr_list(project_root: str = None, jail: str = None) -> str:
    """Dynamic ADR list representation."""
    return get_adr_table(project_root, jail)
