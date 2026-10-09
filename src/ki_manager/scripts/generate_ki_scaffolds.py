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
import ast
from typing import List, Dict, Tuple, Optional, Any

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
_LANG_PATTERNS[".tsx"] = _LANG_PATTERNS[".ts"]
_LANG_PATTERNS[".jsx"] = _LANG_PATTERNS[".ts"]
_LANG_PATTERNS[".js"] = _LANG_PATTERNS[".ts"]

_SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go"}
_SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "venv", "dist", "build", ".mypy_cache"}


def _extract_regex_symbols(content: str, ext: str) -> List[str]:
    patterns = _LANG_PATTERNS.get(ext, [])
    symbols = []
    for pattern, group in patterns:
        for m in pattern.finditer(content):
            name = m.group(group)
            if ext == ".py" and name.startswith("__"):
                continue
            if name not in symbols:
                symbols.append(name)
    return symbols


def extract_python_metadata(file_path: str, content: str) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    """Parses Python file using ast. Returns (module_doc, symbols, env_vars)."""
    try:
        tree = ast.parse(content, filename=file_path)
    except Exception:
        return "", [], []

    module_doc = (ast.get_docstring(tree) or "").strip()
    symbols: List[Dict[str, Any]] = []
    env_vars = set()

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if node.name.startswith("__"):
                continue
            doc = (ast.get_docstring(node) or "").strip()
            first_line = doc.splitlines()[0].strip() if doc else ""
            symbols.append({
                "name": node.name,
                "kind": "class",
                "signature": f"class {node.name}",
                "doc": first_line,
            })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("__"):
                continue
            doc = (ast.get_docstring(node) or "").strip()
            first_line = doc.splitlines()[0].strip() if doc else ""
            
            args = []
            for arg in node.args.args:
                arg_name = arg.arg
                if arg.annotation:
                    try:
                        arg_name += f": {ast.unparse(arg.annotation)}"
                    except Exception:
                        pass
                args.append(arg_name)
            sig = f"{node.name}({', '.join(args)})"
            if node.returns:
                try:
                    sig += f" -> {ast.unparse(node.returns)}"
                except Exception:
                    pass
            symbols.append({
                "name": node.name,
                "kind": "async function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                "signature": sig,
                "doc": first_line,
            })

    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Attribute) and n.func.attr in ("getenv", "get"):
                if n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                    env_vars.add(n.args[0].value)
        elif isinstance(n, ast.Subscript):
            if isinstance(n.value, ast.Attribute) and n.value.attr == "environ":
                if isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str):
                    env_vars.add(n.slice.value)

    return module_doc, symbols, sorted(list(env_vars))


def extract_ts_metadata(content: str) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    """Extract TypeScript/JavaScript symbols with JSDoc comments and env vars."""
    symbols = []
    env_vars = set()
    pattern = re.compile(
        r"(?:/\*\*\s*([\s\S]*?)\*/\s*)?"
        r"^export\s+(?:default\s+)?(?:abstract\s+)?(?:async\s+)?(class|function|const|let|var|type|interface)\s+([A-Za-z_]\w*)",
        re.MULTILINE
    )
    for m in pattern.finditer(content):
        jsdoc = m.group(1) or ""
        kind = m.group(2)
        name = m.group(3)
        doc = ""
        if jsdoc:
            clean_lines = [re.sub(r"^\s*\*?\s*", "", line).strip() for line in jsdoc.splitlines()]
            non_empty = [l for l in clean_lines if l and not l.startswith("@")]
            if non_empty:
                doc = non_empty[0]
        symbols.append({
            "name": name,
            "kind": kind,
            "signature": f"{kind} {name}",
            "doc": doc
        })
    for m in re.finditer(r"process\.env\.([A-Z0-9_]+)", content):
        env_vars.add(m.group(1))

    return "", symbols, sorted(list(env_vars))


def extract_go_metadata(content: str) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    """Extract Go symbols with leading comments."""
    symbols = []
    pattern = re.compile(
        r"(?:((?://[^\n]*\n)+)\s*)?"
        r"^(func\s+(?:\([^)]+\)\s+)?([A-Z][A-Za-z_]\w*)|type\s+([A-Za-z_]\w*)\s+(struct|interface))",
        re.MULTILINE
    )
    for m in pattern.finditer(content):
        comment = m.group(1) or ""
        func_name = m.group(3)
        type_name = m.group(4)
        type_kind = m.group(5)
        name = func_name or type_name
        kind = "function" if func_name else (type_kind or "type")
        doc = ""
        if comment:
            lines = [l.strip().lstrip("/").strip() for l in comment.splitlines()]
            non_empty = [l for l in lines if l]
            if non_empty:
                doc = non_empty[0]
        if name:
            symbols.append({
                "name": name,
                "kind": kind,
                "signature": f"{kind} {name}",
                "doc": doc
            })
    return "", symbols, []


def extract_symbol_details(file_path: str) -> Dict[str, Any]:
    """Extract rich symbol metadata, module docstring, and environment variables."""
    ext = Path(file_path).suffix.lower()
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return {"symbols": [], "module_doc": "", "env_vars": []}

    if ext == ".py":
        module_doc, symbols, env_vars = extract_python_metadata(file_path, content)
        if not symbols:
            symbols = [{"name": s, "kind": "symbol", "signature": s, "doc": ""} for s in _extract_regex_symbols(content, ext)]
        return {"symbols": symbols, "module_doc": module_doc, "env_vars": env_vars}
    elif ext in (".ts", ".tsx", ".js", ".jsx"):
        module_doc, symbols, env_vars = extract_ts_metadata(content)
        if not symbols:
            symbols = [{"name": s, "kind": "symbol", "signature": s, "doc": ""} for s in _extract_regex_symbols(content, ext)]
        return {"symbols": symbols, "module_doc": module_doc, "env_vars": env_vars}
    elif ext == ".go":
        module_doc, symbols, env_vars = extract_go_metadata(content)
        if not symbols:
            symbols = [{"name": s, "kind": "symbol", "signature": s, "doc": ""} for s in _extract_regex_symbols(content, ext)]
        return {"symbols": symbols, "module_doc": module_doc, "env_vars": env_vars}

    return {"symbols": [], "module_doc": "", "env_vars": []}


def extract_symbols(file_path: str) -> List[str]:
    """Extract top-level symbols from a source file. Returns list of symbol names."""
    details = extract_symbol_details(file_path)
    return [sym["name"] for sym in details["symbols"]]


def find_module_tests(project_root: Optional[str], module_path: str, file_infos: List[Dict]) -> Tuple[List[str], str]:
    """Find tests related to the module or its files."""
    if not project_root or not os.path.isdir(project_root):
        return [], "pytest tests/"

    tests_dir = os.path.join(project_root, "tests")
    if not os.path.isdir(tests_dir):
        return [], "pytest"

    stems = {Path(fi.get("fname") or fi.get("rel_path", "")).stem for fi in file_infos if fi.get("fname") or fi.get("rel_path")}
    stems.add(Path(module_path).name)

    matched = []
    for root, _, files in os.walk(tests_dir):
        for f in sorted(files):
            f_stem = Path(f).stem
            for s in stems:
                if s and (f_stem == f"test_{s}" or f_stem == f"{s}_test" or s in f_stem):
                    rel = os.path.relpath(os.path.join(root, f), project_root).replace(os.sep, "/")
                    if rel not in matched:
                        matched.append(rel)

    test_cmd = f"pytest {' '.join(matched)}" if matched else "pytest tests/"
    return matched, test_cmd


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
            if fname.startswith("__") and fname.endswith("__.py") and fname != "__init__.py":
                continue

            abs_file = os.path.join(root, fname)
            rel_file = os.path.relpath(abs_file, project_root).replace(os.sep, "/")
            size = 0
            try:
                size = os.path.getsize(abs_file)
            except OSError:
                pass

            details = extract_symbol_details(abs_file)
            results.append({
                "rel_path": rel_file,
                "fname": fname,
                "ext": ext,
                "size": size,
                "symbols": [s["name"] for s in details["symbols"]],
                "rich_symbols": details["symbols"],
                "module_doc": details["module_doc"],
                "env_vars": details["env_vars"],
            })

    return results


# ─── KI Content Builder ───────────────────────────────────────────────────────

def ki_filename_from_module(module_path: str) -> str:
    """Convert 'src/ki_manager/scripts' → 'KI_src_ki_manager_scripts.md'."""
    parts = module_path.strip("/").replace("\\", "/").split("/")
    slug = "_".join(p for p in parts if p)
    return f"KI_{slug}.md"


def build_scaffold_content(
    module_path: str,
    label: str,
    file_infos: List[Dict],
    project_root: Optional[str] = None
) -> str:
    """Build a scaffold KI markdown file content with AST pre-enrichment."""
    today = date.today().isoformat()
    module_name = label or module_path.split("/")[-1].replace("_", " ").title()

    if not project_root:
        project_root = ki_utils.get_project_root()

    # 1. Overview from module docstrings
    overview_text = ""
    for fi in file_infos:
        doc = fi.get("module_doc", "")
        if doc:
            first_p = doc.strip().split("\n\n")[0].strip().replace("\n", " ")
            if first_p and len(first_p) > 10:
                overview_text = first_p
                break

    overview_section = overview_text if overview_text else (
        "<!-- TODO: describe this module (filled by /scaffold-knowledge enrichment phase) -->"
    )

    # 2. Entry points (first 3 public classes / functions)
    entry_points = []
    for fi in file_infos:
        symbols_source = fi.get("rich_symbols") or fi.get("symbols", [])
        for sym in symbols_source:
            s_name = sym["name"] if isinstance(sym, dict) else str(sym)
            s_kind = sym.get("kind", "") if isinstance(sym, dict) else ""
            s_doc = sym.get("doc", "") if isinstance(sym, dict) else ""
            if not s_name.startswith("_"):
                desc = s_doc or f"Primary {s_kind or 'symbol'} in `{fi['rel_path']}`"
                entry_points.append(f"- `{s_name}`: {desc}")
                if len(entry_points) >= 3:
                    break
        if len(entry_points) >= 3:
            break

    # 3. Tests
    matched_tests, test_cmd = find_module_tests(project_root, module_path, file_infos)

    # 4. Environment variables
    all_env = set()
    for fi in file_infos:
        all_env.update(fi.get("env_vars", []))

    lines = [
        "<!-- scaffold: true -->",
        f"<!-- last_verified: {today} -->",
        f"# KI: {module_name}",
        "",
        "## Overview",
        overview_section,
        "",
        "## Entry Points & Public API",
    ]

    if entry_points:
        lines.extend(entry_points)
    else:
        lines.append("- `SymbolName`: <!-- Primary interface / entry function -->")

    lines.extend([
        "",
        "## Key Components",
        "| Class / Function | File | Purpose |",
        "|---|---|---|",
    ])

    if file_infos:
        for info in file_infos:
            rel = info["rel_path"]
            symbols_source = info.get("rich_symbols") or info.get("symbols", [])
            if symbols_source:
                for sym in symbols_source:
                    sym_name = sym["name"] if isinstance(sym, dict) else str(sym)
                    sym_doc = sym.get("doc", "") if isinstance(sym, dict) else ""
                    purpose = sym_doc if sym_doc else "<!-- TODO -->"
                    lines.append(f"| `{sym_name}` | `{rel}` | {purpose} |")
            else:
                size_kb = round(info["size"] / 1024, 1) if info["size"] else 0
                lines.append(f"| *(file)* | `{rel}` | {size_kb} KB |")
    else:
        lines.append("| — | — | *(no source files found)* |")

    lines.extend([
        "",
        "## Testing & Verification",
        f"- Test commands: `{test_cmd}`",
    ])
    if matched_tests:
        lines.append(f"- Test files: {', '.join(f'`{t}`' for t in matched_tests)}")

    lines.extend([
        "",
        "## Non-obvious Details",
    ])
    if all_env:
        lines.append(f"- Environment variables: {', '.join(f'`{v}`' for v in sorted(all_env))}")
    lines.extend([
        "<!-- TODO -->",
        "",
        "## Common Pitfalls",
        "<!-- TODO -->",
        "",
        "## Related KIs",
        "<!-- Populated by analyze_all_dependencies -->",
    ])

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
            content = build_scaffold_content(module_path, label, file_infos, project_root=project_root)
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
