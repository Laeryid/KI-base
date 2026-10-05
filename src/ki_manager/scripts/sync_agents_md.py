"""
sync_agents_md.py

Synchronizes Knowledge Items and ADR tables in AGENTS.md
using the single source of truth from ki_utils (doc_config.json and decisions/).
"""

import os
import sys
import argparse
import re
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils


def resolve_agents_path(agents_path: str = None) -> str:
    """Finds the AGENTS.md file in the project."""
    if agents_path:
        p = ki_utils.normalize_path(agents_path)
        if os.path.exists(p):
            return p
        return p  # let caller handle not found

    pr = ki_utils.get_project_root()
    kr = ki_utils.get_knowledge_root()
    candidates = []
    if pr:
        candidates.append(os.path.join(pr, "AGENTS.md"))
    if kr and (not pr or os.path.normcase(kr) != os.path.normcase(pr)):
        candidates.append(os.path.join(kr, "AGENTS.md"))
    candidates.append(os.path.abspath("AGENTS.md"))

    for c in candidates:
        if os.path.exists(c):
            return c

    return candidates[0] if candidates else ""


def update_ki_table_in_text(content: str, ki_table_text: str) -> str:
    """Replaces or inserts the Knowledge Items table in AGENTS.md content."""
    lines = content.splitlines()
    
    # Try finding an existing KI table header
    header_idx = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and "File" in line and ("Summary" in line or "Topic" in line):
            header_idx = i
            break
            
    table_lines = ki_table_text.strip().splitlines()

    if header_idx != -1:
        # Find divider line
        divider_idx = header_idx + 1
        if divider_idx < len(lines) and lines[divider_idx].strip().startswith("|"):
            # Consume all table rows
            end_idx = divider_idx + 1
            while end_idx < len(lines) and lines[end_idx].strip().startswith("|"):
                end_idx += 1
            # Replace existing table
            new_lines = lines[:header_idx] + table_lines + lines[end_idx:]
            return "\n".join(new_lines)

    # If no existing table found, look for Knowledge Items section or insert
    sec_match = re.search(r"^(##+\s*(?:Knowledge Items|База знаний)[^\n\r]*)", content, re.MULTILINE | re.IGNORECASE)
    if sec_match:
        pos = sec_match.end()
        return content[:pos] + "\n\n" + ki_table_text + "\n" + content[pos:]

    # Otherwise append before ADR section or at end
    return content + "\n\n## Knowledge Items\n\n" + ki_table_text + "\n"


def update_adr_section_in_text(content: str, adr_table_text: str) -> str:
    """Replaces or inserts the ADR section/table in AGENTS.md content."""
    sec_pattern = re.compile(
        r"^(##+\s*(?:Architecture Decision Records|Architectural Decision Records|ADR|Архитектурные решения)[^\n\r]*)",
        re.MULTILINE | re.IGNORECASE
    )
    m = sec_pattern.search(content)

    if m:
        sec_start = m.start()
        # Find where this section ends (next ## section or end of file)
        rest = content[m.end():]
        next_sec = re.search(r"\n(?=##\s+)", rest)
        if next_sec:
            sec_end = m.end() + next_sec.start()
        else:
            sec_end = len(content)

        new_section = f"{m.group(1)}\n\n{adr_table_text}\n"
        return content[:sec_start] + new_section + content[sec_end:]

    # ADR section not found: insert before "Ключевые файлы для изучения" or "Key Files" or at the end
    key_files_m = re.search(r"\n(?=##\s+(?:Ключевые файлы|Key Files|References))", content, re.IGNORECASE)
    adr_block = f"\n---\n\n## Architecture Decision Records (ADRs)\n\n{adr_table_text}\n\n"
    if key_files_m:
        idx = key_files_m.start()
        return content[:idx] + adr_block + content[idx:]
    else:
        return content.rstrip() + "\n" + adr_block


def sync_agents_md(agents_path: str = None) -> str:
    """
    Synchronizes AGENTS.md with current KIs and ADRs.
    Respects 'sync_agents_md' setting in ki_config.json.
    """
    if not ki_utils.is_sync_agents_md_enabled():
        return "Sync skipped: sync_agents_md is disabled in ki_config.json"

    target_path = resolve_agents_path(agents_path)
    if not target_path or not os.path.exists(target_path):
        return f"Error: AGENTS.md not found at '{target_path}'"

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return f"Error reading AGENTS.md: {e}"

    # Use single source of truth for both tables
    ki_table = ki_utils.get_ki_list_table()
    adr_table = ki_utils.get_adr_table()

    updated = update_ki_table_in_text(content, ki_table)
    updated = update_adr_section_in_text(updated, adr_table)

    if updated != content:
        target_dir = os.path.dirname(target_path) or "."
        os.makedirs(target_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=target_dir, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(updated)
            os.replace(tmp_path, target_path)
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return f"Error saving AGENTS.md: {e}"
        return f"AGENTS.md successfully synchronized at '{target_path}'"
    else:
        return f"AGENTS.md is already up to date at '{target_path}'"


def main():
    parser = argparse.ArgumentParser(description="Synchronize AGENTS.md with doc_config.json and ADRs.")
    parser.add_argument("--agents-path", type=str, default=None, help="Explicit path to AGENTS.md")
    args = parser.parse_args()

    result = sync_agents_md(args.agents_path)
    print(result)


if __name__ == "__main__":
    main()
