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
    2. By checking for doc_config.json in the same folder as this script.
    3. Checking the parent folder of this script (scripts/ → knowledge_root/).
    4. Searching for any folder with doc_config.json in the current working directory.
    """
    config_paths = config_paths or {}

    # 1. From config
    root = config_paths.get("knowledge_root")
    if root and os.path.exists(os.path.join(root, "doc_config.json")):
        return os.path.abspath(root)

    # 2. Same folder as this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists(os.path.join(script_dir, "doc_config.json")):
        return script_dir

    # 3. Parent folder of scripts/ (the knowledge root itself)
    parent_dir = os.path.dirname(script_dir)
    if os.path.exists(os.path.join(parent_dir, "doc_config.json")):
        return parent_dir

    # 4. Search in CWD
    for d in os.listdir("."):
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "doc_config.json")):
            return os.path.abspath(d)

    return ""


# Global configuration objects (resolved at import time)
KI_CFG = load_ki_config()
PATHS = KI_CFG.get("paths", {})
KNOWLEDGE_ROOT = resolve_knowledge_root(PATHS)
DOC_CONFIG_PATH = os.path.join(KNOWLEDGE_ROOT, "doc_config.json") if KNOWLEDGE_ROOT else ""
PYTHON_EXE = PATHS.get("venv_python") or sys.executable


def get_doc_config():
    """Loads doc_config.json (knowledge system manifest)."""
    if DOC_CONFIG_PATH and os.path.exists(DOC_CONFIG_PATH):
        with open(DOC_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}
