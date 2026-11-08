import os
import sys
import argparse
import json
from pathlib import Path
from typing import List

# Add path to ki_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils


def _scan_path(target_path: str, project_root: str, mapped_paths: set, exclude_patterns: set, ignored_exts: set) -> List[str]:
    abs_target = os.path.abspath(os.path.join(project_root, target_path))
    if not ki_utils.is_subpath(abs_target, project_root) or not os.path.exists(abs_target):
        return []

    unmapped = []
    if os.path.isfile(abs_target):
        rel_to_project = os.path.relpath(abs_target, project_root).replace("\\", "/")
        fname = os.path.basename(abs_target)
        if fname.startswith(".") or any(fname.endswith(ext) for ext in ignored_exts):
            return []
        if ki_utils.should_exclude(fname, rel_to_project, exclude_patterns):
            return []
        if abs_target in mapped_paths:
            return []
        for mapped in mapped_paths:
            if os.path.isdir(mapped) and abs_target.startswith(os.path.join(mapped, "")):
                return []
        return [rel_to_project]

    for root, dirs, files in os.walk(abs_target):
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".")
            and not ki_utils.should_exclude(d, os.path.relpath(os.path.join(root, d), project_root), exclude_patterns)
        ]

        for f in files:
            if f.startswith(".") or any(f.endswith(ext) for ext in ignored_exts):
                continue

            full_path = os.path.abspath(os.path.join(root, f))
            rel_to_project = os.path.relpath(full_path, project_root).replace("\\", "/")
            if ki_utils.should_exclude(f, rel_to_project, exclude_patterns):
                continue

            if full_path in mapped_paths:
                continue

            is_parent_mapped = False
            for mapped in mapped_paths:
                if os.path.isdir(mapped):
                    if full_path.startswith(os.path.join(mapped, "")):
                        is_parent_mapped = True
                        break

            if not is_parent_mapped:
                unmapped.append(rel_to_project)

    return unmapped


def sort_unmapped_by_weight(unmapped_files: List[str], project_root: str) -> List[str]:
    """Sort unmapped files: architectural hubs (high imports/size) first, private/leaf files last."""
    if len(unmapped_files) <= 1 or not project_root:
        return unmapped_files

    stems = {}
    for f in unmapped_files:
        p = Path(f)
        stems[p.stem] = f

    in_degrees = {f: 0 for f in unmapped_files}

    # AST parsing for .py files
    for f in unmapped_files:
        if f.endswith(".py"):
            abs_p = os.path.join(project_root, f)
            try:
                with open(abs_p, "r", encoding="utf-8", errors="replace") as fp:
                    content = fp.read()
                import ast
                tree = ast.parse(content, filename=abs_p)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            parts = alias.name.split(".")
                            for part in parts:
                                if part in stems and stems[part] != f:
                                    in_degrees[stems[part]] += 1
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            parts = node.module.split(".")
                            for part in parts:
                                if part in stems and stems[part] != f:
                                    in_degrees[stems[part]] += 1
                        for alias in node.names:
                            if alias.name in stems and stems[alias.name] != f:
                                in_degrees[stems[alias.name]] += 1
            except Exception:
                pass

    def file_score(f: str):
        p = Path(f)
        ext = p.suffix.lower()
        is_code = 1 if ext in ki_utils.CODE_EXTENSIONS else 0
        is_private = 1 if p.name.startswith("_") and p.name != "__init__.py" else 0
        abs_p = os.path.join(project_root, f)
        size_kb = 0.0
        try:
            size_kb = os.path.getsize(abs_p) / 1024.0
        except OSError:
            pass
        score = in_degrees.get(f, 0) * 100.0 + size_kb - (50.0 if is_private else 0.0)
        return (is_code, score)

    return sorted(unmapped_files, key=file_score, reverse=True)


def get_unmapped_files(target_path: str = ".") -> List[str]:
    """Returns a sorted list of unmapped files relative to project root, weighted by relevance."""
    project_root = ki_utils.get_project_root()
    doc_config = ki_utils.get_doc_config()

    if not project_root or not doc_config:
        return []

    # 1. Collect all files that are already mapped in doc_config.json
    mapped_paths = set()
    knowledge_items = doc_config.get("knowledge_items", {})

    for ki in knowledge_items.values():
        depends_on = ki.get("depends_on", [])
        for p in depends_on:
            abs_p = os.path.abspath(os.path.join(project_root, p))
            mapped_paths.add(abs_p)

    ignored_exts = {'.pyc', '.pyo', '.pyd', '.obj', '.dll', '.exe', '.bin'}
    exclude_patterns = ki_utils.get_exclude_patterns()

    norm_target = (target_path or ".").strip()

    # If target is root/empty, scope to tracked_modules if defined
    if norm_target in (".", ""):
        tracked_modules = doc_config.get("coverage_settings", {}).get("tracked_modules") or doc_config.get("tracked_modules", [])
        target_dirs = set()
        if isinstance(tracked_modules, list) and tracked_modules:
            for m in tracked_modules:
                mod_path = m[0] if isinstance(m, (list, tuple)) else m
                if isinstance(mod_path, str) and mod_path.strip():
                    norm_p = mod_path.replace("\\", "/").strip("/")
                    top_segment = norm_p.split("/")[0] if "/" in norm_p else norm_p
                    if top_segment:
                        target_dirs.add(top_segment)

        if target_dirs:
            unmapped_set = set()
            for td in sorted(target_dirs):
                unmapped_set.update(_scan_path(td, project_root, mapped_paths, exclude_patterns, ignored_exts))
            return sort_unmapped_by_weight(list(unmapped_set), project_root)
        else:
            return sort_unmapped_by_weight(_scan_path(".", project_root, mapped_paths, exclude_patterns, ignored_exts), project_root)

    return sort_unmapped_by_weight(_scan_path(norm_target, project_root, mapped_paths, exclude_patterns, ignored_exts), project_root)


def find_unmapped_files(target_path: str = "."):
    project_root = ki_utils.get_project_root()
    doc_config = ki_utils.get_doc_config()

    if not project_root or not doc_config:
        print("Error: Could not resolve project root or doc_config.json")
        return

    display_target = (target_path or ".").strip()
    if display_target != ".":
        abs_target = os.path.abspath(os.path.join(project_root, display_target))
        if not os.path.exists(abs_target):
            print(f"Error: Target path '{display_target}' does not exist.")
            return

    unmapped = get_unmapped_files(display_target)

    # Show existing KIs covering this target area
    existing_kis = []
    knowledge_items = doc_config.get("knowledge_items", {})
    norm_disp = display_target.replace("\\", "/").strip("./")
    for ki_name, entry in knowledge_items.items():
        deps = [d.replace("\\", "/").strip("./") for d in entry.get("depends_on", [])]
        matched_deps = [d for d in deps if (not norm_disp) or d.startswith(norm_disp + "/") or d == norm_disp]
        if matched_deps:
            existing_kis.append((ki_name, len(matched_deps), entry.get("summary", "")))

    if existing_kis:
        print(f"\nExisting KIs for '{display_target}':")
        for kn, count, summ in existing_kis:
            s_info = f" - {summ}" if summ else ""
            print(f"  • `{kn}` ({count} files){s_info}")
        print()

    if unmapped:
        print(f"### Unmapped Files in '{display_target}' (ordered by architectural weight):")
        for f in unmapped:
            print(f"- {f}")
    else:
        print(f"All files in '{display_target}' are already mapped in doc_config.json.")


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Find files in a directory not covered by any KI in doc_config.json")
    parser.add_argument("path", nargs="?", default=".", help="Relative path from project root to scan (default: tracked_modules or .)")
    args = parser.parse_args()

    find_unmapped_files(args.path)
