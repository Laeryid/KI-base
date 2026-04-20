"""
audit_coverage.py

Audit of Knowledge Base coverage for the project.

Compares:
- Project directories tracked in doc_config.json
- Knowledge Items registered in doc_config.json

Outputs a coverage matrix with priority recommendations for /expand-knowledge.
Saves the result to <knowledge_root>/coverage_matrix.md

Usage:
    .venv/Scripts/python.exe scripts/audit_coverage.py
    .venv/Scripts/python.exe scripts/audit_coverage.py --root /path/to/project
    .venv/Scripts/python.exe scripts/audit_coverage.py --no-save
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Add scripts dir to path so ki_utils is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils

KNOWLEDGE_ROOT = ki_utils.KNOWLEDGE_ROOT

EXCLUDED_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build"}
DENSITY_THRESHOLD = 50.0   # KI bytes per 1 KB of code
COMPLEXITY_THRESHOLD = 10  # Files per one KI


# ─── Data Loading ─────────────────────────────────────────────────────────────

def load_tracked_modules():
    doc_config = ki_utils.get_doc_config()
    return doc_config.get("coverage_settings", {}).get("tracked_modules", [])


def load_doc_config() -> dict:
    """Loads doc_config.json."""
    return ki_utils.get_doc_config()


def load_ki_files() -> list:
    """Returns a list of KI file names."""
    ki_dir = os.path.join(KNOWLEDGE_ROOT, "knowledge")
    if not os.path.isdir(ki_dir):
        return []
    return [f for f in os.listdir(ki_dir) if f.startswith("KI_") and f.endswith(".md")]


# ─── Metrics ──────────────────────────────────────────────────────────────────

def count_code_size_kb(dirpath: str) -> float:
    total = 0
    for root, dirs, files in os.walk(dirpath):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for f in files:
            if f.endswith((".py", ".ts", ".tsx", ".js", ".jsx")):
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    return round(total / 1024, 1)


def get_module_files(project_root: str, module_path: str) -> list:
    abs_module = os.path.join(project_root, module_path.replace("/", os.sep))
    if not os.path.isdir(abs_module):
        return []
    files_list = []
    for root, dirs, files in os.walk(abs_module):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for f in files:
            if f.endswith((".py", ".ts", ".tsx", ".js", ".jsx")) and not f.startswith("__"):
                rel_path = os.path.relpath(os.path.join(root, f), project_root)
                files_list.append(rel_path)
    return files_list


def get_covered_paths(doc_config: dict) -> set:
    paths = set()
    for entry in doc_config.get("knowledge_items", {}).values():
        for p in entry.get("depends_on", []):
            paths.add(p.replace("/", os.sep).rstrip(os.sep))
    return paths


def is_path_covered(file_path: str, covered_paths: set) -> bool:
    return file_path in covered_paths


def has_ki_coverage(module_path: str, ki_files: list, doc_config: dict) -> bool:
    module_norm = module_path.replace("/", os.sep).rstrip(os.sep) + os.sep
    for ki_name, entry in doc_config.get("knowledge_items", {}).items():
        for dep in entry.get("depends_on", []):
            dep_norm = dep.replace("/", os.sep)
            if dep_norm.startswith(module_norm):
                return True
    return False


def get_ki_size(project_root: str, module_path: str, doc_config: dict) -> int:
    module_norm = module_path.replace("/", os.sep).rstrip(os.sep)
    total_size = 0
    ki_dir = os.path.join(KNOWLEDGE_ROOT, "knowledge")

    for ki_name, entry in doc_config.get("knowledge_items", {}).items():
        covered = any(
            dep.replace("/", os.sep).startswith(module_norm)
            for dep in entry.get("depends_on", [])
        )
        if covered:
            ki_path = os.path.join(ki_dir, ki_name)
            if os.path.exists(ki_path):
                total_size += os.path.getsize(ki_path)
    return total_size


def find_untracked_dirs(project_root: str, tracked_modules: list) -> list:
    tracked_paths = {m[0].replace("/", os.sep).rstrip(os.sep) for m in tracked_modules}
    untracked = []
    for item in os.listdir(project_root):
        abs_item = os.path.join(project_root, item)
        if not os.path.isdir(abs_item) or item in EXCLUDED_DIRS or item.startswith("."):
            continue
        for root, dirs, files in os.walk(abs_item):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]
            rel_path = os.path.relpath(root, project_root)
            norm_rel = rel_path.replace("/", os.sep).rstrip(os.sep)
            if any(not f.startswith(".") for f in files):
                is_sub_covered = any(
                    norm_rel == tp or norm_rel.startswith(tp + os.sep)
                    for tp in tracked_paths
                )
                if not is_sub_covered:
                    untracked.append(rel_path)
                    dirs[:] = []
    return untracked


def priority_label(priority: int) -> str:
    if priority >= 8:
        return "🔴 Critical"
    elif priority >= 5:
        return "🟡 Medium"
    else:
        return "🟢 Low"


# ─── Matrix Builder ────────────────────────────────────────────────────────────

def build_coverage_matrix(project_root: str, tracked_modules: list) -> dict:
    doc_config = load_doc_config()
    ki_files = load_ki_files()
    covered_paths = get_covered_paths(doc_config)

    ki_complexity = {
        ki_name: len(entry.get("depends_on", []))
        for ki_name, entry in doc_config.get("knowledge_items", {}).items()
    }

    rows = []
    for module_path, label, importance in tracked_modules:
        module_files = get_module_files(project_root, module_path)
        total_files = len(module_files)

        if total_files == 0:
            coverage_pct = 100.0 if os.path.exists(os.path.join(project_root, module_path)) else 0.0
            size_kb = 0.0
        else:
            covered_count = sum(1 for f in module_files if is_path_covered(f, covered_paths))
            coverage_pct = (covered_count / total_files) * 100
            size_kb = count_code_size_kb(os.path.join(project_root, module_path.replace("/", os.sep)))

        has_ki = has_ki_coverage(module_path, ki_files, doc_config)
        ki_size = get_ki_size(project_root, module_path, doc_config)
        density = round(ki_size / size_kb, 1) if size_kb > 0 else 0.0

        complex_kis = [
            k for k, v in ki_complexity.items()
            if v > COMPLEXITY_THRESHOLD and any(
                dep.startswith(module_path)
                for dep in doc_config["knowledge_items"][k].get("depends_on", [])
            )
        ]

        gap_factor = 1.0 + (100 - coverage_pct) / 50.0
        if not has_ki:
            gap_factor += 1.0
        density_factor = 1.5 if (has_ki and size_kb > 5 and density < DENSITY_THRESHOLD) else 1.0
        computed_priority = round(importance * gap_factor * (1 + size_kb / 200) * density_factor)

        rows.append({
            "module": module_path,
            "label": label,
            "files": total_files,
            "size_kb": size_kb,
            "has_ki": has_ki,
            "ki_size": ki_size,
            "density": density,
            "coverage_pct": round(coverage_pct, 1),
            "importance": importance,
            "priority": computed_priority,
            "complex_kis": complex_kis,
            "status": "✅ Covered" if coverage_pct == 100 else
                      "⚠️ Partial" if coverage_pct > 0 else "❌ Not Covered"
        })

    rows.sort(key=lambda r: (-r["priority"], r["label"]))
    untracked = find_untracked_dirs(project_root, tracked_modules)
    return {"rows": rows, "untracked": untracked}


# ─── Formatters ───────────────────────────────────────────────────────────────

def format_markdown(data: dict, generated_at: str) -> str:
    rows = data["rows"]
    untracked = data["untracked"]

    lines = [
        f"<!-- generated: {generated_at} -->",
        "# Knowledge Base Coverage Matrix",
        "",
        f"> Generated by: `scripts/audit_coverage.py`  ",
        f"> Date: {generated_at}",
        "",
        "## Module Coverage",
        "",
        "| Module | Label | KI | Cov | KB | Density | Priority | Status |",
        "|---|---|:---:|:---:|---:|---:|---|---|",
    ]

    for r in rows:
        ki = "✅" if r["has_ki"] else "❌"
        cov = f"{r['coverage_pct']}%"
        p = priority_label(r["importance"])
        warn = ""
        if r["complex_kis"]:
            warn += " 🔥"
        if r["has_ki"] and r["density"] < DENSITY_THRESHOLD and r["size_kb"] > 5:
            warn += " ❄️"
        lines.append(
            f"| `{r['module']}` | {r['label']}{warn} | {ki} | {cov} | "
            f"{r['size_kb']} | {r['density']} | {p} | {r['status']} |"
        )

    covered = sum(1 for r in rows if r["has_ki"] and r["coverage_pct"] == 100)
    total = len(rows)
    progress = round(covered / total * 100) if total > 0 else 0

    lines += [
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "|---|---|",
        f"| ✅ Fully Covered | {covered} / {total} |",
        f"| 📊 Progress | **{progress}%** |",
        "",
    ]

    if untracked:
        lines += [
            "## ⚠️ Undocumented Areas (Blind Spots)",
            "",
            "The following directories contain code but are not included in the audit:",
            "",
        ]
        for u in untracked:
            lines.append(f"- `{u}`")
        lines.append("")

    lines += ["## Recommendations for /expand-knowledge", ""]
    top = [r for r in rows
           if r["coverage_pct"] < 100
           or (r["has_ki"] and r["density"] < DENSITY_THRESHOLD and r["size_kb"] > 5)][:5]
    for i, r in enumerate(top, 1):
        missing = []
        if not r["has_ki"]:
            missing.append("no KI file")
        elif r["density"] < DENSITY_THRESHOLD:
            missing.append(f"low knowledge density ({r['density']} bytes/KB)")
        if r["coverage_pct"] < 100:
            missing.append(f"only {r['coverage_pct']}% files covered")
        lines += [
            f"### {i}. {r['label']} — {priority_label(r['importance'])}",
            f"- **Path**: `{r['module']}`",
            f"- **Size**: {r['size_kb']} KB, {r['files']} files",
            f"- **Gaps**: {', '.join(missing)}",
            "",
        ]

    complex_list = [r for r in rows if r["complex_kis"]]
    if complex_list:
        lines += [
            "## Complexity Warnings",
            "",
            "KIs that cover too many files (>10) — consider splitting:",
            "",
        ]
        for r in complex_list:
            kis = ", ".join(f"`{k}`" for k in r["complex_kis"])
            lines.append(f"- **{r['label']}**: {kis}")
        lines.append("")

    return "\n".join(lines)


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Knowledge base coverage audit.")
    parser.add_argument("--root", default=".", help="Project root directory (default: current)")
    parser.add_argument("--no-save", action="store_true", help="Do not save coverage_matrix.md")
    parser.add_argument("--output", default=None, help="Custom output path for coverage_matrix.md")
    args = parser.parse_args()

    project_root = ki_utils.PROJECT_ROOT
    tracked_modules = load_tracked_modules()
    if not tracked_modules:
        print("[!] No tracked_modules found in doc_config.json. Please fill in coverage_settings.")
        sys.exit(0)

    print(f"[*] Auditing project: {project_root}")
    data = build_coverage_matrix(project_root, tracked_modules)

    # Terminal output
    print("\n" + "=" * 70)
    print("  COVERAGE MATRIX")
    print("=" * 70)
    header = f"{'Module':<32} {'KI':^3} {'Cov':>6} | {'Density':>8}"
    print(header)
    print("-" * 70)
    for r in data["rows"]:
        ki = "✅" if r["has_ki"] else "❌"
        print(f"{r['label']:<32} {ki:^3} {r['coverage_pct']:>5}% | {r['density']:>6.1f} B/KB")

    if data["untracked"]:
        print("\n[!] Untracked directories:", ", ".join(data["untracked"]))

    # Save Markdown
    if not args.no_save:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        md_content = format_markdown(data, generated_at)
        output_path = args.output or os.path.join(KNOWLEDGE_ROOT, "coverage_matrix.md")
        output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"[+] Matrix saved: {output_path}")


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    main()
