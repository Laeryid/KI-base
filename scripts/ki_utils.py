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
    Tries to find the path in the --ki-config argument or uses the default.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=str, default=config_default)
    args, _ = parser.parse_known_args()

    config_path = args.config
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass
    return {}


def resolve_knowledge_root(config_paths=None) -> str:
    config_paths = config_paths or {}

    # 1. From CLI --config (if it looks like a ki_config.json)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=str)
    args, _ = parser.parse_known_args()
    if args.config:
        cfg_path = os.path.abspath(args.config)
        # If it's a file, we look for doc_config.json in its directory
        if os.path.isfile(cfg_path):
            parent = os.path.dirname(cfg_path)
            if os.path.exists(os.path.join(parent, "doc_config.json")):
                return parent
        # If it's a directory, check it
        if os.path.isdir(cfg_path) and os.path.exists(os.path.join(cfg_path, "doc_config.json")):
            return cfg_path

    # 2. From config_paths
    root = config_paths.get("knowledge_root")
    if root:
        abs_root = os.path.abspath(root)
        if os.path.exists(os.path.join(abs_root, "doc_config.json")):
            return abs_root

    # 3. Parent folder of scripts/ (usual location)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    if os.path.exists(os.path.join(parent_dir, "doc_config.json")):
        return parent_dir

    # 3. Same folder as this script
    if os.path.exists(os.path.join(script_dir, "doc_config.json")):
        return script_dir

    # 4. Search in CWD
    for d in [".", ".."]: # Check current and parent (if script run from elsewhere)
        target = os.path.join(os.path.abspath(d), ".know")
        if os.path.isdir(target) and os.path.exists(os.path.join(target, "doc_config.json")):
            return target
        
        # Or look for doc_config.json in current folder itself
        if os.path.exists(os.path.join(os.path.abspath(d), "doc_config.json")):
            return os.path.abspath(d)

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
