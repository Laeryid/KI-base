"""
split_ki.py

Tool and script for analyzing and splitting overloaded Knowledge Items (>10 files)
into two balanced, cohesive KIs.

Follows the B-tree split model:
1. analyze_split: static import graph analysis & layer bisection into Group A & B
2. apply_split: atomic creation of two KIs, removal of original, updating doc_config.json
"""

import os
import sys
import json
import ast
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils
from generate_ki_scaffolds import extract_symbol_details


def _resolve_project_and_knowledge(project_root: Optional[str] = None):
    p_root = project_root or ki_utils.get_project_root()
    k_root = ki_utils.get_knowledge_root()
    return p_root, k_root


def analyze_split(ki_name: str, project_root: Optional[str] = None) -> Dict[str, Any]:
    """
    Analyzes an overloaded KI and calculates an optimal bisection into two balanced groups.
    """
    p_root, k_root = _resolve_project_and_knowledge(project_root)
    doc_config = ki_utils.get_doc_config()

    if not doc_config:
        return {"isError": True, "message": "doc_config.json not found."}

    ki_items = doc_config.get("knowledge_items", {})
    if ki_name not in ki_items:
        # Check without .md extension
        for k in ki_items:
            if k == f"{ki_name}.md" or Path(k).stem == ki_name:
                ki_name = k
                break
        else:
            return {"isError": True, "message": f"KI '{ki_name}' not found in doc_config.json"}

    entry = ki_items[ki_name]
    raw_deps = entry.get("depends_on", [])
    
    # Filter to actual files
    files = []
    for d in raw_deps:
        norm_d = d.replace("\\", "/")
        abs_d = os.path.join(p_root, norm_d)
        if not os.path.isdir(abs_d):
            files.append(norm_d)

    total_files = len(files)
    if total_files <= 1:
        return {
            "isError": True,
            "message": f"KI '{ki_name}' has only {total_files} file(s), splitting is not needed."
        }

    # Map filename stems to relative paths
    stem_to_file = {Path(f).stem: f for f in files}
    in_degrees = {f: 0 for f in files}
    out_degrees = {f: 0 for f in files}
    file_details = {}

    for f in files:
        abs_f = os.path.join(p_root, f)
        details = extract_symbol_details(abs_f)
        file_details[f] = details

        if f.endswith(".py") and os.path.isfile(abs_f):
            try:
                with open(abs_f, "r", encoding="utf-8", errors="replace") as fp:
                    tree = ast.parse(fp.read(), filename=abs_f)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            parts = alias.name.split(".")
                            for part in parts:
                                if part in stem_to_file and stem_to_file[part] != f:
                                    out_degrees[f] += 1
                                    in_degrees[stem_to_file[part]] += 1
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            parts = node.module.split(".")
                            for part in parts:
                                if part in stem_to_file and stem_to_file[part] != f:
                                    out_degrees[f] += 1
                                    in_degrees[stem_to_file[part]] += 1
                        for alias in node.names:
                            if alias.name in stem_to_file and stem_to_file[alias.name] != f:
                                out_degrees[f] += 1
                                in_degrees[stem_to_file[alias.name]] += 1
            except Exception:
                pass

    # Score each file by abstractness (in_degree - out_degree) + size
    scored_files = []
    for f in files:
        abstractness = in_degrees[f] - out_degrees[f]
        abs_f = os.path.join(p_root, f)
        size_kb = os.path.getsize(abs_f) / 1024.0 if os.path.exists(abs_f) else 0.0
        # Prefix clusters (e.g. progress_*, table_*, style_*)
        stem = Path(f).stem
        prefix = stem.split("_")[0] if "_" in stem else stem
        scored_files.append({
            "path": f,
            "abstractness": abstractness,
            "in_degree": in_degrees[f],
            "out_degree": out_degrees[f],
            "size_kb": round(size_kb, 1),
            "prefix": prefix,
            "symbols": [s["name"] for s in file_details[f]["symbols"][:5]]
        })

    # Sort files: foundation (high in-degree/abstractness) first, consumers last
    scored_files.sort(key=lambda x: (x["abstractness"], x["in_degree"], -x["out_degree"]), reverse=True)

    # Balanced split between 1/3 and 2/3
    split_idx = max(len(files) // 2, 1)
    # Ensure at least ceil(N/3) on each side
    min_size = max(1, (len(files) + 2) // 3)
    if split_idx < min_size:
        split_idx = min_size
    elif len(files) - split_idx < min_size:
        split_idx = len(files) - min_size

    group_a_info = scored_files[:split_idx]
    group_b_info = scored_files[split_idx:]

    group_a_files = [x["path"] for x in group_a_info]
    group_b_files = [x["path"] for x in group_b_info]

    # Suggest KI names based on common prefixes or roles
    base_stem = Path(ki_name).stem
    if base_stem.startswith("KI_"):
        base_stem = base_stem[3:]

    # Inspect predominant names/prefixes
    a_prefixes = {x["prefix"] for x in group_a_info}
    b_prefixes = {x["prefix"] for x in group_b_info}

    name_a = f"KI_{base_stem}_core.md" if any(p in ("color", "style", "core", "base", "cells", "box") for p in a_prefixes) else f"KI_{base_stem}_part1.md"
    name_b = f"KI_{base_stem}_components.md" if any(p in ("table", "panel", "progress", "live", "prompt", "syntax") for p in b_prefixes) else f"KI_{base_stem}_part2.md"

    # Build markdown report
    report_lines = [
        f"# Split Analysis for `{ki_name}`",
        f"- **Total Files**: {total_files}",
        f"- **Recommended Split**: Group A ({len(group_a_files)} files) vs Group B ({len(group_b_files)} files)",
        "",
        f"## Group A: Suggested `{name_a}` (Foundation / Core)",
        "| File | In | Out | Size | Key Symbols |",
        "|---|:---:|:---:|---:|---|",
    ]
    for x in group_a_info:
        syms = ", ".join(f"`{s}`" for s in x["symbols"][:3]) or "*(none)*"
        report_lines.append(f"| `{x['path']}` | {x['in_degree']} | {x['out_degree']} | {x['size_kb']} KB | {syms} |")

    report_lines.extend([
        "",
        f"## Group B: Suggested `{name_b}` (High-level / Features)",
        "| File | In | Out | Size | Key Symbols |",
        "|---|:---:|:---:|---:|---|",
    ])
    for x in group_b_info:
        syms = ", ".join(f"`{s}`" for s in x["symbols"][:3]) or "*(none)*"
        report_lines.append(f"| `{x['path']}` | {x['in_degree']} | {x['out_degree']} | {x['size_kb']} KB | {syms} |")

    report_lines.extend([
        "",
        "### Next Step:",
        f"Call `ki_split` with `target_a` and `target_b` payloads to apply this split atomically."
    ])

    return {
        "ki_name": ki_name,
        "total_files": total_files,
        "group_a": {
            "suggested_ki_name": name_a,
            "files": group_a_files,
        },
        "group_b": {
            "suggested_ki_name": name_b,
            "files": group_b_files,
        },
        "markdown_report": "\n".join(report_lines)
    }


def apply_split(
    ki_name: str,
    target_a: Dict[str, Any],
    target_b: Dict[str, Any],
    project_root: Optional[str] = None
) -> Dict[str, Any]:
    """
    Atomically applies KI split:
    - Verifies no files lost and no duplicate files between A and B
    - Writes both target KI markdown files
    - Updates doc_config.json
    - Deletes original KI if renamed
    """
    p_root, k_root = _resolve_project_and_knowledge(project_root)
    doc_config = ki_utils.get_doc_config()

    if not doc_config:
        return {"isError": True, "message": "doc_config.json not found."}

    ki_items = doc_config.get("knowledge_items", {})
    if ki_name not in ki_items:
        # Match by stem or with .md
        for k in ki_items:
            if k == f"{ki_name}.md" or Path(k).stem == ki_name:
                ki_name = k
                break
        else:
            return {"isError": True, "message": f"Original KI '{ki_name}' not found in doc_config.json"}

    original_entry = ki_items[ki_name]
    raw_deps = original_entry.get("depends_on", [])
    
    # Original files
    orig_files = set()
    for d in raw_deps:
        norm_d = d.replace("\\", "/")
        abs_d = os.path.join(p_root, norm_d)
        if not os.path.isdir(abs_d):
            orig_files.add(norm_d)

    a_name = target_a.get("ki_name", "").strip()
    b_name = target_b.get("ki_name", "").strip()

    if not a_name or not b_name:
        return {"isError": True, "message": "Both target_a and target_b must have 'ki_name'."}

    a_deps = set(d.replace("\\", "/") for d in target_a.get("depends_on", []))
    b_deps = set(d.replace("\\", "/") for d in target_b.get("depends_on", []))

    # Validation: Disjoint
    overlap = a_deps & b_deps
    if overlap:
        return {
            "isError": True,
            "message": f"Overlapping files between target_a and target_b: {sorted(list(overlap))}"
        }

    # Validation: No lost files
    missing_files = orig_files - (a_deps | b_deps)
    if missing_files:
        return {
            "isError": True,
            "message": f"Files from original KI were lost in split: {sorted(list(missing_files))}"
        }

    # Write target files
    ki_dir = os.path.join(k_root, "knowledge")
    os.makedirs(ki_dir, exist_ok=True)

    path_a = os.path.join(ki_dir, a_name)
    path_b = os.path.join(ki_dir, b_name)

    content_a = target_a.get("content", f"# KI: {a_name}\n\n## Overview\nSplit from {ki_name}\n")
    content_b = target_b.get("content", f"# KI: {b_name}\n\n## Overview\nSplit from {ki_name}\n")

    with open(path_a, "w", encoding="utf-8") as f:
        f.write(content_a)

    with open(path_b, "w", encoding="utf-8") as f:
        f.write(content_b)

    # Update doc_config.json
    ki_items[a_name] = {
        "summary": target_a.get("summary", f"Split part A of {ki_name}"),
        "depends_on": sorted(list(a_deps))
    }
    ki_items[b_name] = {
        "summary": target_b.get("summary", f"Split part B of {ki_name}"),
        "depends_on": sorted(list(b_deps))
    }

    # Remove old KI if it was replaced with different names
    if ki_name not in (a_name, b_name):
        if ki_name in ki_items:
            del ki_items[ki_name]
        old_path = os.path.join(ki_dir, ki_name)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

    ki_utils.save_doc_config(doc_config)

    # Trigger dependency updates
    try:
        from ki_dependency_analyzer import KIDependencyAnalyzer
        analyzer = KIDependencyAnalyzer()
        # Refresh analyzer state
        analyzer.doc_config = ki_utils.get_doc_config()
        analyzer.file_to_ki = analyzer._build_reverse_index()
    except Exception:
        pass

    return {
        "isError": False,
        "message": f"Successfully split '{ki_name}' into '{a_name}' ({len(a_deps)} files) and '{b_name}' ({len(b_deps)} files).",
        "created_kis": [a_name, b_name],
        "removed_ki": ki_name if ki_name not in (a_name, b_name) else None
    }


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Split overloaded Knowledge Items into balanced KIs.")
    subparsers = parser.add_subparsers(dest="subcommand")

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="Analyze KI for split")
    p_analyze.add_argument("ki_name", help="Name of KI file to analyze")
    p_analyze.add_argument("--json", action="store_true", help="Output raw JSON")

    # apply
    p_apply = subparsers.add_parser("apply", help="Apply KI split")
    p_apply.add_argument("ki_name", help="Original KI name")
    p_apply.add_argument("--payload", help="JSON payload containing target_a and target_b")

    args = parser.parse_args()

    if args.subcommand == "analyze":
        res = analyze_split(args.ki_name)
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(res.get("markdown_report", res.get("message", "")))
    elif args.subcommand == "apply":
        try:
            payload = json.loads(args.payload)
            res = apply_split(args.ki_name, payload.get("target_a", {}), payload.get("target_b", {}))
            print(json.dumps(res, indent=2, ensure_ascii=False))
        except Exception as e:
            print(json.dumps({"isError": True, "message": str(e)}))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
