"""
add_ki_to_config.py

CLI helper and module function to register or update a Knowledge Item in doc_config.json.
"""

import sys
import os
import json
import argparse
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils


def add_ki(
    ki_name: str,
    description: str,
    covers: Optional[List[str]] = None,
    depends_on: Optional[List[str]] = None,
    summary: Optional[str] = None
) -> str:
    """
    Registers or updates a Knowledge Item in doc_config.json.
    """
    if not ki_name:
        raise ValueError("ki_name is required.")

    covers = covers if covers is not None else []
    depends_on = depends_on if depends_on is not None else []

    config = ki_utils.get_doc_config()
    if not config and not ki_utils.get_doc_config_path():
        raise PermissionError("No active workspace detected or doc_config.json not found.")

    if "knowledge_items" not in config:
        config["knowledge_items"] = {}

    existing = config["knowledge_items"].get(ki_name, {})
    entry = {
        "description": description if description else existing.get("description", ""),
        "covers": covers,
        "depends_on": depends_on,
    }
    
    if summary:
        entry["summary"] = summary
    elif "summary" in existing:
        entry["summary"] = existing["summary"]
    elif description:
        entry["summary"] = description

    config["knowledge_items"][ki_name] = entry
    ki_utils.save_doc_config(config)
    return f"Knowledge Item '{ki_name}' successfully registered in doc_config.json"


def main():
    parser = argparse.ArgumentParser(description="Add or update a Knowledge Item in doc_config.json")
    parser.add_argument("ki_name", type=str, help="Knowledge Item filename")
    parser.add_argument("description", type=str, help="KI description")
    parser.add_argument("--covers", type=str, default="[]", help="JSON array of covered modules")
    parser.add_argument("--depends-on", type=str, default="[]", help="JSON array of dependencies")
    parser.add_argument("--summary", type=str, default=None, help="Optional summary text")

    args = parser.parse_args()
    try:
        covers = json.loads(args.covers)
        depends_on = json.loads(args.depends_on)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON arguments: {e}")
        sys.exit(1)

    result = add_ki(args.ki_name, args.description, covers, depends_on, args.summary)
    print(result)


if __name__ == "__main__":
    main()
