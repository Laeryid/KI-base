"""
ki_utils.py

Shared utility module for KI_base scripts.
Handles loading ki_config.json and resolving key paths.
"""

import os
import json
import sys
import argparse
from pathlib import Path


def load_ki_config(config_default="ki_config.json"):
    """
    Loads configuration from ki_config.json.
    Tries to find the path in the --config argument or uses the default.
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
    """
    Determines the knowledge root folder.
    Priority:
    1. From the configuration path dictionary (if present).
    2. Checking the parent folder of this script (scripts/ → knowledge_root/).
    3. Checking for doc_config.json in the same folder as this script.
    4. Searching for any folder with doc_config.json in the current working directory.
    """
    config_paths = config_paths or {}

    # 1. From config
    root = config_paths.get("knowledge_root")
    if root:
        abs_root = os.path.abspath(root)
        if os.path.exists(os.path.join(abs_root, "doc_config.json")):
            return abs_root

    # 2. Parent folder of scripts/ (usual location)
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


# Global configuration objects (resolved at import time)
KI_CFG = load_ki_config()
PATHS = KI_CFG.get("paths", {})
KNOWLEDGE_ROOT = resolve_knowledge_root(PATHS)
PROJECT_ROOT = resolve_project_root(PATHS, KNOWLEDGE_ROOT)
DOC_CONFIG_PATH = os.path.join(KNOWLEDGE_ROOT, "doc_config.json") if KNOWLEDGE_ROOT else ""
PYTHON_EXE = PATHS.get("venv_python") or sys.executable


def get_doc_config():
    """Loads doc_config.json (knowledge system manifest)."""
    if DOC_CONFIG_PATH and os.path.exists(DOC_CONFIG_PATH):
        try:
            with open(DOC_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}
