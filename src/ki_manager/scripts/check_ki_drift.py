"""
check_ki_drift.py

Detects discrepancies (drift) between Knowledge Items (KI) and the actual codebase:
1. Symbol Drift:
   - Dead symbols in Key Components table (deleted/renamed in code).
   - Unmapped public symbols in source files (new code not yet in KI).
2. File Drift:
   - Broken or missing file paths in doc_config.json depends_on.
3. Date Drift:
   - Source files modified in git after KI's <!-- last_verified: YYYY-MM-DD -->.
4. Broken Wiki-links:
   - [[Target_KI.md]] links in Related KIs that do not exist.
5. Integrity Drift:
   - Pending scaffolds (<!-- scaffold: true -->) or remaining <!-- TODO --> markers.

Usage:
    python check_ki_drift.py --all
    python check_ki_drift.py --ki KI_server.md
    python check_ki_drift.py --json
"""

import os
import sys
import re
import json
import argparse
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils
from generate_ki_scaffolds import extract_symbol_details


def parse_ki_file(ki_path: Path) -> Dict[str, Any]:
    """Parse a KI markdown file and extract its metadata, tables, and links."""
    try:
        content = ki_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {
            "error": f"Cannot read {ki_path.name}",
            "last_verified": None,
            "is_scaffold": False,
            "is_enriched": False,
            "has_todo": False,
            "table_symbols": [],
            "wiki_links": [],
            "sections": set(),
        }

    lines = content.splitlines()
    last_verified = None
    is_scaffold = False
    is_enriched = False
    has_todo = "<!-- TODO" in content or "TODO:" in content

    # Check top lines for markers
    for line in lines[:5]:
        line_clean = line.strip()
        if "<!-- scaffold: true -->" in line_clean:
            is_scaffold = True
        elif "<!-- scaffold: enriched -->" in line_clean:
            is_enriched = True
        elif line_clean.startswith("<!-- last_verified:"):
            parts = line_clean.split(":", 1)
            if len(parts) > 1:
                last_verified = parts[1].replace("-->", "").strip()

    # Extract sections
    sections = set()
    for line in lines:
        if line.startswith("## "):
            sections.add(line[3:].strip())

    # Extract Key Components table symbols
    # Expected table format: | `SymbolName` | `rel/path/file.ext` | Purpose |
    table_symbols: List[Dict[str, str]] = []
    in_key_components = False
    table_row_pattern = re.compile(r"\|\s*`?([A-Za-z0-9_]+)`?\s*\|\s*`?([^`|\s]+)`?\s*\|")

    for line in lines:
        if line.startswith("## Key Components"):
            in_key_components = True
            continue
        elif in_key_components and line.startswith("## "):
            in_key_components = False
            continue

        if in_key_components and line.strip().startswith("|"):
            lower = line.lower()
            if any(k in lower for k in ["class / function", "component", "|---", "|:---", "| — |", "| - |"]):
                continue
            m = table_row_pattern.search(line)
            if m:
                sym_name = m.group(1).strip()
                file_rel = m.group(2).strip()
                header_keywords = {"component", "file", "purpose", "class", "function", "description"}
                if sym_name.lower() in header_keywords or file_rel.lower() in header_keywords:
                    continue
                if sym_name and file_rel and not file_rel.startswith("—"):
                    table_symbols.append({"symbol": sym_name, "file": file_rel})

    # Extract wiki-links [[KI_*.md]]
    wiki_links = []
    for link_match in re.finditer(r"\[\[([^\]]+)\]\]", content):
        wiki_links.append(link_match.group(1).strip())

    return {
        "last_verified": last_verified,
        "is_scaffold": is_scaffold,
        "is_enriched": is_enriched,
        "has_todo": has_todo,
        "table_symbols": table_symbols,
        "wiki_links": wiki_links,
        "sections": sections,
    }


def get_git_commit_date(project_root: str, rel_path: str) -> Optional[str]:
    """Returns the ISO date (YYYY-MM-DD) of the last git commit touching rel_path."""
    try:
        res = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", rel_path],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
        if res.returncode == 0:
            date_str = res.stdout.strip()
            return date_str if date_str else None
    except Exception:
        pass
    return None


def check_single_ki(
    ki_name: str,
    ki_path: Path,
    doc_config: dict,
    project_root: str,
    knowledge_dir: Path
) -> Dict[str, Any]:
    """Inspects a single KI file against code and configuration for drift."""
    ki_data = parse_ki_file(ki_path)
    if "error" in ki_data:
        return {"ki": ki_name, "error": ki_data["error"], "drift_count": 1}

    config_entry = doc_config.get("knowledge_items", {}).get(ki_name, {})
    depends_on = config_entry.get("depends_on", [])

    dead_symbols: List[Dict[str, str]] = []
    unmapped_symbols: List[Dict[str, Any]] = []
    missing_files: List[str] = []
    date_drifts: List[Dict[str, str]] = []
    broken_links: List[str] = []
    integrity_issues: List[str] = []

    # 1. Integrity issues
    if ki_data["is_scaffold"]:
        integrity_issues.append("Scaffold stub is still pending (<!-- scaffold: true -->)")
    elif ki_data["is_enriched"]:
        integrity_issues.append("Scaffold is enriched but not finalized (run ki_finalize_scaffolds)")
    if ki_data["has_todo"]:
        integrity_issues.append("Contains unpopulated <!-- TODO --> markers")

    # 2. Check depends_on files existence
    for dep in depends_on:
        dep_path = Path(project_root) / dep
        if not dep_path.exists():
            missing_files.append(dep)

    # 3. Check wiki-links
    for link in ki_data["wiki_links"]:
        # Standardize target name
        target_name = link if link.endswith(".md") else f"{link}.md"
        target_path = knowledge_dir / target_name
        if not target_path.exists():
            broken_links.append(link)

    # 4. Group table symbols by file to check symbol drift
    symbols_by_file: Dict[str, Set[str]] = {}
    for entry in ki_data["table_symbols"]:
        f_norm = entry["file"].replace("\\", "/")
        symbols_by_file.setdefault(f_norm, set()).add(entry["symbol"])

    # Determine files to inspect for symbol drift
    files_to_inspect = set(symbols_by_file.keys())
    for dep in depends_on:
        dep_norm = dep.replace("\\", "/")
        dep_abs = Path(project_root) / dep
        if dep_abs.is_file() and dep_abs.suffix.lower() in (".py", ".ts", ".tsx", ".js", ".jsx", ".go"):
            files_to_inspect.add(dep_norm)

    for rel_file in files_to_inspect:
        abs_file = Path(project_root) / rel_file
        if not abs_file.exists():
            if rel_file not in missing_files:
                missing_files.append(rel_file)
            continue

        # Extract real symbols from code
        code_details = extract_symbol_details(str(abs_file))
        code_symbols_dict = {s["name"]: s for s in code_details.get("symbols", [])}
        code_symbols_set = set(code_symbols_dict.keys())

        # Check dead symbols (present in KI table, absent in code)
        documented_symbols = symbols_by_file.get(rel_file, set())
        for doc_sym in documented_symbols:
            if doc_sym not in code_symbols_set:
                dead_symbols.append({"symbol": doc_sym, "file": rel_file})

        # Check unmapped public symbols in source files
        # (Only report top-level non-private symbols)
        for sym_name, sym_info in code_symbols_dict.items():
            if sym_name not in documented_symbols and not sym_name.startswith("_"):
                unmapped_symbols.append({
                    "symbol": sym_name,
                    "kind": sym_info.get("kind", "symbol"),
                    "file": rel_file,
                })

        # Check date drift if last_verified is present
        if ki_data["last_verified"]:
            last_commit_date = get_git_commit_date(project_root, rel_file)
            if last_commit_date and last_commit_date > ki_data["last_verified"]:
                date_drifts.append({
                    "file": rel_file,
                    "commit_date": last_commit_date,
                    "last_verified": ki_data["last_verified"],
                })

    drift_count = (
        len(dead_symbols)
        + len(unmapped_symbols)
        + len(missing_files)
        + len(date_drifts)
        + len(broken_links)
        + len(integrity_issues)
    )

    return {
        "ki": ki_name,
        "drift_count": drift_count,
        "last_verified": ki_data["last_verified"],
        "dead_symbols": dead_symbols,
        "unmapped_symbols": unmapped_symbols,
        "missing_files": missing_files,
        "date_drifts": date_drifts,
        "broken_links": broken_links,
        "integrity_issues": integrity_issues,
    }


def run_drift_check(
    ki_filter: Optional[str] = None,
    project_root: Optional[str] = None,
    knowledge_root: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Runs drift check on one or all KIs."""
    if not project_root:
        project_root = ki_utils.get_project_root()
    if not knowledge_root:
        knowledge_root = ki_utils.get_knowledge_root()

    if not knowledge_root or not project_root:
        raise RuntimeError("Could not determine project root or knowledge root.")

    knowledge_dir = Path(knowledge_root) / "knowledge"
    if not knowledge_dir.exists() and Path(knowledge_root).exists():
        knowledge_dir = Path(knowledge_root)

    if not knowledge_dir.exists():
        return []

    doc_config = ki_utils.get_doc_config()

    if ki_filter:
        target_name = ki_filter if ki_filter.endswith(".md") else f"{ki_filter}.md"
        target_path = knowledge_dir / target_name
        if not target_path.exists():
            return [{"ki": target_name, "error": f"File not found: {target_name}", "drift_count": 1}]
        return [check_single_ki(target_name, target_path, doc_config, project_root, knowledge_dir)]

    results = []
    for f in sorted(knowledge_dir.glob("KI_*.md")):
        results.append(check_single_ki(f.name, f, doc_config, project_root, knowledge_dir))

    return results


def format_drift_markdown(results: List[Dict[str, Any]]) -> str:
    """Formats drift check results as clean Markdown."""
    total_kis = len(results)
    with_drift = [r for r in results if r.get("drift_count", 0) > 0]

    lines = [
        f"### Knowledge Base Drift Report",
        f"- **Checked KIs**: {total_kis}",
        f"- **KIs with drift**: {len(with_drift)}",
        "",
    ]

    if not with_drift:
        lines.append("✅ **No drift detected.** All Knowledge Items match current code and git state.")
        return "\n".join(lines)

    for item in with_drift:
        ki_name = item["ki"]
        lines.append(f"#### ⚠️ `{ki_name}` ({item['drift_count']} issues)")

        if item.get("error"):
            lines.append(f"- [!] Error: {item['error']}")
            continue

        for issue in item.get("integrity_issues", []):
            lines.append(f"- [!] **Integrity**: {issue}")

        for dead in item.get("dead_symbols", []):
            lines.append(f"- [!] **Dead symbol**: `{dead['symbol']}` (no longer in `{dead['file']}`)")

        for missing in item.get("missing_files", []):
            lines.append(f"- [!] **Missing file**: `{missing}` (does not exist on disk)")

        for broken in item.get("broken_links", []):
            lines.append(f"- [!] **Broken wiki-link**: `[[{broken}]]` (target KI does not exist)")

        for date_item in item.get("date_drifts", []):
            lines.append(
                f"- [~] **Date drift**: `{date_item['file']}` was committed on "
                f"`{date_item['commit_date']}`, after last_verified (`{date_item['last_verified']}`)"
            )

        unmapped = item.get("unmapped_symbols", [])
        if unmapped:
            sample = unmapped[:5]
            more = len(unmapped) - 5
            unmapped_str = ", ".join(f"`{u['symbol']}`" for u in sample)
            if more > 0:
                unmapped_str += f" and {more} more"
            lines.append(f"- [+] **Unmapped symbols**: {unmapped_str} in `{unmapped[0]['file']}`")

        lines.append("")

    return "\n".join(lines).strip()


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Check drift and discrepancies between KI files and codebase.")
    parser.add_argument("--ki", type=str, help="Specific KI file to check (e.g. KI_server.md)")
    parser.add_argument("--all", action="store_true", help="Check all KIs in the knowledge base")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--workspace", type=str, default=None, help=argparse.SUPPRESS)

    args = parser.parse_args()

    if args.workspace:
        ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(args.workspace)
    else:
        match = ki_utils.find_project_by_cwd(os.getcwd())
        if match:
            target_path = match.get("config_path") or match.get("workspace") or os.getcwd()
            ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(target_path)
        else:
            ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(os.getcwd())

    results = run_drift_check(ki_filter=args.ki)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print(format_drift_markdown(results))


if __name__ == "__main__":
    main()
