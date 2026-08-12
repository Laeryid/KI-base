"""
finalize_ki_scaffolds.py

Finalizes enriched scaffold KI files by:
  1. Updating doc_config.json summaries from "[scaffold] label" to the real
     Overview text extracted from the KI file.
  2. Removing the <!-- scaffold: enriched --> marker from each enriched KI.

Only processes KIs with <!-- scaffold: enriched --> on line 1.
KIs with <!-- scaffold: true --> (pending) are left untouched.

Usage:
    python finalize_ki_scaffolds.py
    python finalize_ki_scaffolds.py --dry-run
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils

ENRICHED_MARKER = "<!-- scaffold: enriched -->"
PENDING_MARKER = "<!-- scaffold: true -->"


def extract_overview(content: str) -> str:
    """Extract the first non-empty paragraph from the Overview section."""
    match = re.search(r"## Overview\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
    if not match:
        return ""
    text = match.group(1).strip()
    # Strip HTML comments (<!-- TODO --> etc.)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip()
    # Return only the first non-empty line
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def finalize_scaffolds(dry_run: bool = False) -> None:
    knowledge_root = ki_utils.get_knowledge_root()
    if not knowledge_root:
        print("[ERROR] No active project. Run ki_init_project first.")
        sys.exit(1)

    ki_dir = os.path.join(knowledge_root, "knowledge")
    if not os.path.exists(ki_dir):
        print("[ERROR] knowledge/ directory not found.")
        sys.exit(1)

    doc_config_path = ki_utils.get_doc_config_path()
    if not doc_config_path or not os.path.exists(doc_config_path):
        print("[ERROR] doc_config.json not found.")
        sys.exit(1)

    with open(doc_config_path, "r", encoding="utf-8") as f:
        doc_config = json.load(f)

    ki_items = doc_config.get("knowledge_items", {})

    processed = 0
    skipped_pending = 0
    skipped_clean = 0

    for fname in sorted(os.listdir(ki_dir)):
        if not (fname.startswith("KI_") and fname.endswith(".md")):
            continue

        ki_path = os.path.join(ki_dir, fname)

        try:
            with open(ki_path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            print(f"  [ERROR] Cannot read {fname}: {e}")
            continue

        first_line = content.split("\n", 1)[0].strip()

        if PENDING_MARKER in first_line:
            print(f"  [SKIP]  {fname} — still pending, not enriched yet")
            skipped_pending += 1
            continue

        if ENRICHED_MARKER not in first_line:
            skipped_clean += 1
            continue  # Already clean — no marker, nothing to do

        # ── This KI is enriched: process it ──

        # 1. Extract overview for doc_config summary
        overview = extract_overview(content)

        # 2. Remove the enriched marker line
        lines = content.split("\n")
        new_lines = [l for l in lines if ENRICHED_MARKER not in l]
        new_content = "\n".join(new_lines)

        print(f"  [OK]    {fname}")
        if overview:
            print(f"           summary: {overview[:80]}{'...' if len(overview) > 80 else ''}")
        else:
            print(f"           summary: (no overview text found — keeping old summary)")

        if not dry_run:
            # Write cleaned KI
            with open(ki_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            # Update doc_config summary
            if fname in ki_items and overview:
                ki_items[fname]["summary"] = overview
            elif fname not in ki_items:
                print(f"           [WARN] {fname} not found in doc_config.json — skipping summary update")

        processed += 1

    if not dry_run and processed > 0:
        doc_config["knowledge_items"] = ki_items
        with open(doc_config_path, "w", encoding="utf-8") as f:
            json.dump(doc_config, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"\n[+] doc_config.json updated.")

    print(f"\n── Summary ──────────────────────────────────────")
    print(f"  Finalized:       {processed}")
    print(f"  Skipped pending: {skipped_pending}")
    print(f"  Already clean:   {skipped_clean}")
    if dry_run:
        print(f"  (dry run — no files written)")
    if skipped_pending > 0:
        print(f"\n[!] {skipped_pending} KI(s) still pending. Enrich them first, then run ki_finalize_scaffolds again.")
    elif processed > 0:
        print(f"\n[NEXT] Run analyze_all_dependencies to populate 'Related KIs' sections.")


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Finalize enriched scaffold KI files: clean markers, update doc_config summaries."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be changed without writing any files."
    )
    parser.add_argument("--workspace", type=str, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.workspace:
        ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(args.workspace)
    else:
        cwd = os.getcwd()
        match = ki_utils.find_project_by_cwd(cwd)
        if match:
            ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(match["config_path"])

    finalize_scaffolds(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
