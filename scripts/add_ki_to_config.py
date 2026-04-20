"""
add_ki_to_config.py

CLI helper: registers a new Knowledge Item in doc_config.json.

Usage:
    python add_ki_to_config.py <ki_name> <description> <covers_json> <depends_on_json>

Example:
    python add_ki_to_config.py KI_utils.md "Utility helpers" '["Utilities"]' '["src/utils/"]'
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils


def add_ki(ki_name: str, description: str, covers: list, depends_on: list):
    config = ki_utils.get_doc_config()
    if not config:
        print("[!] doc_config.json not found or empty")
        return

    if "knowledge_items" not in config:
        config["knowledge_items"] = {}

    config["knowledge_items"][ki_name] = {
        "description": description,
        "covers": covers,
        "depends_on": depends_on,
    }

    with open(ki_utils.DOC_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

    print(f"[+] KI registered in doc_config.json: {ki_name}")


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python add_ki_to_config.py <ki_name> <description> "
              "<covers_list_json> <depends_on_list_json>")
        sys.exit(1)

    ki_name = sys.argv[1]
    description = sys.argv[2]
    try:
        covers = json.loads(sys.argv[3])
        depends_on = json.loads(sys.argv[4])
    except json.JSONDecodeError:
        print("[!] Error: covers and depends_on must be valid JSON arrays")
        sys.exit(1)

    add_ki(ki_name, description, covers, depends_on)
