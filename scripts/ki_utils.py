"""
ki_utils.py

Shared utility module for KI_base scripts.
Handles loading ki_config.json and resolving key paths.
"""

import os
import sys
import json
import argparse
from pathlib import Path


def load_ki_config(config_default="ki_config.json"):
    """
    Loads configuration from ki_config.json.
    Tries to find the path in the --config argument, then in .know/, then in current dir.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=str)
    args, _ = parser.parse_known_args()

    # Priority 1: --config argument
    if args.config and os.path.exists(args.config):
        config_path = args.config
        if os.path.isdir(config_path):
            config_path = os.path.join(config_path, config_default)
    else:
        # Priority 2: In .know/ directory relative to project root
        # We try to find project root first
        script_dir = os.path.dirname(os.path.abspath(__file__))
        possible_locations = [
            os.path.join(os.path.dirname(script_dir), config_default), # .know/ki_config.json
            os.path.join(os.getcwd(), ".know", config_default),
            os.path.join(os.getcwd(), config_default),
            config_default
        ]
        
        config_path = None
        for loc in possible_locations:
            if os.path.exists(loc):
                config_path = loc
                break

    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass
    return {}


def resolve_knowledge_root(config_paths=None, strict=False) -> str:
    """
    Determines the knowledge root folder (knowledge_root).
    Priority:
    1. CLI Argument --config (Mandatory if strict=True)
    2. CWD (for MCP Isolation, ignored if strict=True)
    3. Auto-detection based on the location of the ki_utils module itself
    """
    config_paths = config_paths or {}
    
    # 1. From CLI --config (explicit path is always priority)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=str)
    args, _ = parser.parse_known_args()
    if args.config:
        cfg_path = os.path.abspath(args.config)
        if os.path.isfile(cfg_path):
            parent = os.path.dirname(cfg_path)
            if os.path.exists(os.path.join(parent, "doc_config.json")):
                return parent
        if os.path.isdir(cfg_path) and os.path.exists(os.path.join(cfg_path, "doc_config.json")):
            return cfg_path

    # If strict mode is on, we ONLY allow --config
    if strict:
        return ""

    # 2. From CWD (MCP Isolation)
    cwd = os.getcwd()
    target_know = os.path.join(cwd, ".know")
    if os.path.isdir(target_know) and os.path.exists(os.path.join(target_know, "doc_config.json")):
        return target_know
    if os.path.exists(os.path.join(cwd, "doc_config.json")):
        return cwd

    # 3. From config_paths (passed from ki_config.json)
    root = config_paths.get("knowledge_root")
    if root:
        abs_root = os.path.abspath(root)
        if os.path.exists(os.path.join(abs_root, "doc_config.json")):
            return abs_root

    # 4. Fallback: Parent folder of scripts/ (relative to script location)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    if os.path.exists(os.path.join(parent_dir, "doc_config.json")):
        return parent_dir

    # 5. Fallback: Same folder as this script
    if os.path.exists(os.path.join(script_dir, "doc_config.json")):
        return script_dir

    return ""


def resolve_project_root(config_paths, knowledge_root) -> str:
    """
    Determines the project root.
    Priority:
    1. From config (relative to knowledge_root or absolute).
    2. Default: parent of knowledge_root.
    """
    root = config_paths.get("project_root")
    if root:
        if os.path.isabs(root):
            return root
        return os.path.abspath(os.path.join(knowledge_root, root))
    
    if knowledge_root:
        return os.path.dirname(knowledge_root)
    
    return os.getcwd()


# Internal cache
_CACHE = {}


def get_ki_cfg():
    if "ki_cfg" not in _CACHE:
        _CACHE["ki_cfg"] = load_ki_config()
    return _CACHE["ki_cfg"]


def get_paths():
    return get_ki_cfg().get("paths", {})


def get_knowledge_root():
    if "knowledge_root" not in _CACHE:
        _CACHE["knowledge_root"] = resolve_knowledge_root(get_paths())
    return _CACHE["knowledge_root"]


def get_knowledge_root_strict():
    """Returns knowledge root only if explicitly provided via --config."""
    if "knowledge_root_strict" not in _CACHE:
        _CACHE["knowledge_root_strict"] = resolve_knowledge_root(get_paths(), strict=True)
    return _CACHE["knowledge_root_strict"]


def get_project_root():
    if "project_root" not in _CACHE:
        _CACHE["project_root"] = resolve_project_root(get_paths(), get_knowledge_root())
    return _CACHE["project_root"]


def get_doc_config_path():
    # doc_config.json is always located in the knowledge root
    root = get_knowledge_root()
    return os.path.join(root, "doc_config.json") if root else ""


def get_python_exe():
    return get_paths().get("venv_python") or sys.executable


def get_doc_config():
    """Loads doc_config.json (knowledge system manifest)."""
    path = get_doc_config_path()
    if path:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


# Legacy compatibility layer (keep for short-term compatibility)
KNOWLEDGE_ROOT = get_knowledge_root()
PROJECT_ROOT = get_project_root()
DOC_CONFIG_PATH = get_doc_config_path()
PYTHON_EXE = get_python_exe()
