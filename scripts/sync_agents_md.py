"""
sync_agents_md.py

Synchronizes the KI table in AGENTS.md with the current state of doc_config.json.
Finds the | File | Topic | table and replaces its rows with fresh data from knowledge_items.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils


def sync_agents_md():
    doc_config = ki_utils.get_doc_config()
    if not doc_config:
        print("[!] doc_config.json not found or empty")
        return

    # Resolve AGENTS.md: try next to knowledge root, then project root, then CWD
    candidates = []
    if ki_utils.KNOWLEDGE_ROOT:
        candidates.append(os.path.join(ki_utils.KNOWLEDGE_ROOT, "..", "AGENTS.md"))
    candidates.append("AGENTS.md")

    agents_file_path = None
    for c in candidates:
        if os.path.exists(c):
            agents_file_path = c
            break

    if not agents_file_path:
        print("[!] AGENTS.md not found. Checked:", candidates)
        return

    with open(agents_file_path, "r", encoding="utf-8") as f:
        content = f.read()

    header = "| File | Topic |"
    divider = "|------|-------|"

    if header not in content:
        print("[!] Table '| File | Topic |' not found in AGENTS.md. Nothing to sync.")
        return

    ki_items = doc_config.get("knowledge_items", {})
    new_rows = sorted(
        f"| `{ki_name}` | {ki_info.get('description', 'No description')} |"
        for ki_name, ki_info in ki_items.items()
    )

    lines = content.splitlines()
    start_idx = next((i for i, l in enumerate(lines) if header in l), -1)
    if start_idx == -1:
        return

    # Find the end of the table (skip header + divider line, then consume | rows)
    end_idx = start_idx + 2
    while end_idx < len(lines) and lines[end_idx].strip().startswith("|"):
        end_idx += 1

    new_content_lines = lines[:start_idx + 2] + new_rows + lines[end_idx:]

    with open(agents_file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(new_content_lines) + "\n")

    print(f"[+] AGENTS.md synchronized. Total KIs: {len(new_rows)}")


if __name__ == "__main__":
    sync_agents_md()
