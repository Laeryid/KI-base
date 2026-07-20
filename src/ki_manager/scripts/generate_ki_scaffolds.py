"""
generate_ki_scaffolds.py

Generates scaffold KI files for modules not yet covered by the knowledge base.

Uses regex-based symbol extraction — no external dependencies, works for:
  - Python (.py):           class Foo, def bar
  - TypeScript/JS (.ts/.tsx/.js/.jsx): export class, export function, export const
  - Go (.go):               func Foo, type Foo struct
  - Universal fallback:     lists files and their sizes only

Generated KI files are marked with <!-- scaffold: true --> and have empty
semantic sections (Overview, Non-obvious Details, Common Pitfalls).
These markers signal to /scaffold-knowledge workflow that flash enrichment is needed.

Usage:
    python generate_ki_scaffolds.py
    python generate_ki_scaffolds.py --dry-run
    python generate_ki_scaffolds.py --modules src/auth,src/api
    python generate_ki_scaffolds.py --force
"""

import os
import sys
import re
import json
import argparse
from datetime import date
from pathlib import Path
from typing import List, Dict, Tuple, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils

# ─── Language Extractors ──────────────────────────────────────────────────────

# (regex_pattern, group_index_for_symbol_name)
_LANG_PATTERNS: Dict[str, List[Tuple[re.Pattern, int]]] = {
    ".py": [
        (re.compile(r"^class\s+([A-Za-z_]\w*)", re.MULTILINE), 1),
        (re.compile(r"^def\s+([A-Za-z_]\w*)", re.MULTILINE), 1),
    ],
    ".ts": [
        (re.compile(r"^export\s+(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_]\w*)", re.MULTILINE), 1),
        (re.compile(r"^export\s+(?:async\s+)?function\s+([A-Za-z_]\w*)", re.MULTILINE), 1),
        (re.compile(r"^export\s+(?:const|let|var)\s+([A-Za-z_]\w*)", re.MULTILINE), 1),
        (re.compile(r"^export\s+(?:type|interface)\s+([A-Za-z_]\w*)", re.MULTILINE), 1),
    ],
    ".go": [
        (re.compile(r"^func\s+(?:\([^)]+\)\s+)?([A-Z][A-Za-z_]\w*)", re.MULTILINE), 1),
        (re.compile(r"^type\s+([A-Za-z_]\w*)\s+struct", re.MULTILINE), 1),
        (re.compile(r"^type\s+([A-Za-z_]\w*)\s+interface", re.MULTILINE), 1),
    ],
}
# Aliases: tsx → ts patterns, jsx → js (no explicit patterns → fallback)
_LANG_PATTERNS[".tsx"] = _LANG_PATTERNS[".ts"]
_LANG_PATTERNS[".jsx"] = _LANG_PATTERNS[".ts"]
_LANG_PATTERNS[".js"] = _LANG_PATTERNS[".ts"]

_SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go"}
_SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "venv", "dist", "build", ".mypy_cache"}


def extract_symbols(file_path: str) -> List[str]:
    """Extract top-level symbols from a source file via regex. Returns list of symbol names."""
    ext = Path(file_path).suffix.lower()
    patterns = _LANG_PATTERNS.get(ext)
    if not patterns:
        return []

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return []

    symbols = []
    for pattern, group in patterns:
        for m in pattern.finditer(content):
            name = m.group(group)
            # Skip dunder methods and private names in Python
            if ext == ".py" and name.startswith("__"):
                continue
            if name not in symbols:
                symbols.append(name)
    return symbols


def scan_module(project_root: str, module_path: str) -> List[Dict]:
    """Scan a module directory and return per-file symbol info."""
    abs_module = os.path.join(project_root, module_path.replace("/", os.sep))
    results = []

    for root, dirs, files in os.walk(abs_module):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
        for fname in sorted(files):
            ext = Path(fname).suffix.lower()
            if ext not in _SOURCE_EXTENSIONS:
                continue
            if fname.startswith("__") and fname.endswith("__.py"):
                continue  # skip __init__.py etc. from symbol table (often empty)

            abs_file = os.path.join(root, fname)
            rel_file = os.path.relpath(abs_file, project_root).replace(os.sep, "/")
            size = 0
            try:
                size = os.path.getsize(abs_file)
            except OSError:
                pass

            symbols = extract_symbols(abs_file)
            results.append({
                "rel_path": rel_file,
                "fname": fname,
                "ext": ext,
                "size": size,
                "symbols": symbols,
            })

    return results


# ─── KI Content Builder ───────────────────────────────────────────────────────

def ki_filename_from_module(module_path: str) -> str:
    """Convert 'src/ki_manager/scripts' → 'KI_src_ki_manager_scripts.md'."""
    parts = module_path.strip("/").replace("\\", "/").split("/")
    slug = "_".join(p for p in parts if p)
    return f"KI_{slug}.md"


def build_scaffold_content(module_path: str, label: str, file_infos: List[Dict]) -> str:
    """Build a scaffold KI markdown file content."""
    today = date.today().isoformat()
    module_name = label or module_path.split("/")[-1].replace("_", " ").title()

    lines = [
        "<!-- scaffold: true -->",
        f"<!-- last_verified: {today} -->",
        f"# KI: {module_name}",
        "",
        "## Overview",
        "<!-- TODO: describe this module (filled by /scaffold-knowledge enrichment phase) -->",
        "",
        "## Key Components",
        "| Class / Function | File | Purpose |",
        "|---|---|---|",
    ]

    if file_infos:
        for info in file_infos:
            rel = info["rel_path"]
            if info["symbols"]:
                for sym in info["symbols"]:
                    lines.append(f"| `{sym}` | `{rel}` | <!-- TODO --> |")
            else:
                # No symbols extracted — add the file itself as a row
                size_kb = round(info["size"] / 1024, 1) if info["size"] else 0
                lines.append(f"| *(file)* | `{rel}` | {size_kb} KB |")
    else:
        lines.append("| — | — | *(no source files found)* |")

    lines += [
        "",
        "## Non-obvious Details",
        "<!-- TODO -->",
        "",
        "## Common Pitfalls",
        "<!-- TODO -->",
    ]

    return "\n".join(lines) + "\n"


# ─── doc_config.json Integration ─────────────────────────────────────────────

def load_doc_config() -> dict:
    return ki_utils.get_doc_config()


def save_doc_config(config: dict) -> None:
    path = ki_utils.get_doc_config_path()
    if not path:
        raise RuntimeError("doc_config.json path not found — is the project initialized?")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")


def register_ki_in_config(config: dict, ki_name: str, label: str, module_path: str,
                           file_infos: List[Dict]) -> None:
    """Add or update a KI entry in doc_config.json under knowledge_items."""
    if "knowledge_items" not in config:
        config["knowledge_items"] = {}

    depends_on = [info["rel_path"] for info in file_infos]
    # Also include the module directory itself as a dependency
    if module_path not in depends_on:
        depends_on = [module_path] + depends_on

    config["knowledge_items"][ki_name] = {
        "summary": f"[scaffold] {label}",
        "depends_on": depends_on,
    }


# ─── Main Logic ───────────────────────────────────────────────────────────────

def get_uncovered_modules(doc_config: dict) -> List[Tuple[str, str, int]]:
    """Return tracked modules that have no KI coverage yet."""
    tracked = doc_config.get("coverage_settings", {}).get("tracked_modules", [])
    existing_ki = set(doc_config.get("knowledge_items", {}).keys())

    # Build set of module paths already covered
    covered_module_paths = set()
    for ki_name, entry in doc_config.get("knowledge_items", {}).items():
        for dep in entry.get("depends_on", []):
            covered_module_paths.add(dep.replace("/", os.sep).rstrip(os.sep))

    uncovered = []
    for item in tracked:
        module_path, label, importance = item[0], item[1], item[2]
        norm = module_path.replace("/", os.sep).rstrip(os.sep)
        # Check if this module path (or its parent) is already in covered_module_paths
        is_covered = any(
            norm == cp or norm.startswith(cp + os.sep)
            for cp in covered_module_paths
        )
        if not is_covered:
            uncovered.append((module_path, label, importance))

    return uncovered


def is_scaffold_ki(ki_path: str) -> bool:
    """Return True if the KI file has scaffold marker (and thus safe to overwrite with --force)."""
    try:
        with open(ki_path, "r", encoding="utf-8") as f:
            first_line = f.readline()
        return "<!-- scaffold: true -->" in first_line
    except OSError:
        return False


def print_scaffold_status() -> None:
    """Print a concise status of all scaffold KIs by reading their headers."""
    knowledge_root = ki_utils.get_knowledge_root()
    if not knowledge_root:
        print("[ERROR] No active project. Run ki_init_project first.")
        sys.exit(1)

    ki_dir = os.path.join(knowledge_root, "knowledge")
    if not os.path.exists(ki_dir):
        print("No knowledge base found.")
        return

    print("### KI Scaffold Status")
    print("| KI File | Status | Date | Name |")
    print("|---|---|---|---|")

    found_any = False
    pending_count = 0
    enriched_count = 0
    
    for fname in sorted(os.listdir(ki_dir)):
        if not (fname.startswith("KI_") and fname.endswith(".md")):
            continue
            
        ki_path = os.path.join(ki_dir, fname)
        status = "Complete"
        date_str = "-"
        title = fname
        
        try:
            with open(ki_path, "r", encoding="utf-8") as f:
                # Read up to 5 lines to find our metadata
                for _ in range(5):
                    line = f.readline().strip()
                    if not line:
                        continue
                    if "<!-- scaffold: true -->" in line:
                        status = "🚧 Pending (True)"
                        pending_count += 1
                    elif "<!-- scaffold: enriched -->" in line:
                        status = "✅ Enriched"
                        enriched_count += 1
                    elif line.startswith("<!-- last_verified:"):
                        # Extract date
                        parts = line.split(":")
                        if len(parts) > 1:
                            date_str = parts[1].replace("-->", "").strip()
                    elif line.startswith("# KI:"):
                        title = line[5:].strip()
        except OSError:
            status = "Error reading"
            
        # We only care to summarize scaffold files (true or enriched), 
        # but showing all helps the AI see the big picture. 
        # Let's show all KI files for completeness.
        print(f"| `{fname}` | {status} | {date_str} | {title} |")
        found_any = True

    if not found_any:
        print("| _No KI files found_ | - | - | - |")
        
    print(f"\n**Summary:** {pending_count} pending enrichment, {enriched_count} enriched scaffolds.")



def generate_scaffolds(
    modules_filter: Optional[List[str]] = None,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    project_root = ki_utils.get_project_root()
    knowledge_root = ki_utils.get_knowledge_root()

    if not knowledge_root:
        print("[ERROR] No active project. Run ki_init_project first.")
        sys.exit(1)

    ki_dir = os.path.join(knowledge_root, "knowledge")
    os.makedirs(ki_dir, exist_ok=True)

    doc_config = load_doc_config()
    uncovered = get_uncovered_modules(doc_config)

    # Apply optional module filter
    if modules_filter:
        filter_set = {m.strip() for m in modules_filter}
        uncovered = [(p, l, i) for p, l, i in uncovered
                     if p in filter_set or l in filter_set]

    if not uncovered:
        print("[OK] No uncovered modules found — nothing to scaffold.")
        return

    print(f"[*] Project root: {project_root}")
    print(f"[*] Knowledge root: {knowledge_root}")
    print(f"[*] Found {len(uncovered)} uncovered module(s).")
    if dry_run:
        print("[!] DRY RUN — no files will be written.\n")

    created, skipped, overwritten = 0, 0, 0

    for module_path, label, importance in uncovered:
        ki_name = ki_filename_from_module(module_path)
        ki_path = os.path.join(ki_dir, ki_name)

        # Conflict resolution
        if os.path.exists(ki_path):
            if force and is_scaffold_ki(ki_path):
                action = "overwrite"
            elif force:
                print(f"  [SKIP] {ki_name} — exists and is NOT a scaffold (--force skips non-scaffold KIs)")
                skipped += 1
                continue
            else:
                print(f"  [SKIP] {ki_name} — already exists (use --force to overwrite scaffold KIs)")
                skipped += 1
                continue
        else:
            action = "create"

        # Scan module
        file_infos = scan_module(project_root, module_path)
        symbol_count = sum(len(fi["symbols"]) for fi in file_infos)
        lang_set = {fi["ext"] for fi in file_infos}
        langs_str = ", ".join(sorted(lang_set)) if lang_set else "unknown"

        print(f"  [{action.upper()}] {ki_name}")
        print(f"           module: {module_path}  ({len(file_infos)} files, {symbol_count} symbols, langs: {langs_str})")

        if not dry_run:
            content = build_scaffold_content(module_path, label, file_infos)
            with open(ki_path, "w", encoding="utf-8") as f:
                f.write(content)
            register_ki_in_config(doc_config, ki_name, label, module_path, file_infos)
            # Save after EVERY KI write — makes the run crash-safe.
            # If interrupted, already-created KIs are registered and won't be re-created.
            save_doc_config(doc_config)

            if action == "create":
                created += 1
            else:
                overwritten += 1

    if not dry_run and (created + overwritten) > 0:
        print(f"[+] doc_config.json updated ({created + overwritten} entries written).")


    print(f"\n── Summary ──────────────────────────────────────")
    print(f"  Created:     {created}")
    print(f"  Overwritten: {overwritten}")
    print(f"  Skipped:     {skipped}")
    if dry_run:
        print(f"  (dry run — no files written)")
    print(f"\n[NEXT] Run /scaffold-knowledge workflow (Phase 2) to enrich Overview sections with flash AI.")


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Generate scaffold KI files for uncovered modules."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be created without writing any files."
    )
    parser.add_argument(
        "--modules", type=str, default=None,
        help="Comma-separated list of module paths or labels to scaffold (default: all uncovered)."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing KI files that have the scaffold marker."
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Print status of KI files (pending vs enriched) and exit."
    )
    # --workspace is consumed by ki_utils.load_ki_config() via its own parse_known_args
    parser.add_argument("--workspace", type=str, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    # Allow direct invocation: if --workspace passed, set ACTIVE_WORKSPACE_PATH explicitly
    if args.workspace:
        ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(args.workspace)
    else:
        # Detect from cwd (works when invoked via run_script() which sets cwd=project_root)
        cwd = os.getcwd()
        match = ki_utils.find_project_by_cwd(cwd)
        if match:
            ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(match["config_path"])

    if args.status:
        print_scaffold_status()
        return

    modules_filter = [m.strip() for m in args.modules.split(",")] if args.modules else None
    generate_scaffolds(
        modules_filter=modules_filter,
        dry_run=args.dry_run,
        force=args.force,
    )


if __name__ == "__main__":
    main()
