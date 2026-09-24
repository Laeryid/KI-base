import os
import sys
import argparse
import json
from pathlib import Path
from typing import List

# Добавляем путь к ki_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils

def get_unmapped_files(target_path: str = ".") -> List[str]:
    """Returns a sorted list of unmapped files relative to project root."""
    project_root = ki_utils.get_project_root()
    doc_config = ki_utils.get_doc_config()

    if not project_root or not doc_config:
        return []

    # 1. Собираем все файлы, которые уже замаплены в doc_config.json
    mapped_paths = set()
    knowledge_items = doc_config.get("knowledge_items", {})

    for ki in knowledge_items.values():
        depends_on = ki.get("depends_on", [])
        for p in depends_on:
            abs_p = os.path.abspath(os.path.join(project_root, p))
            mapped_paths.add(abs_p)

    # 2. Сканируем целевую директорию
    abs_target = os.path.abspath(os.path.join(project_root, target_path))
    if not os.path.exists(abs_target):
        return []

    unmapped = []
    ignored_exts = {'.pyc', '.pyo', '.pyd', '.obj', '.dll', '.exe', '.bin'}
    exclude_patterns = ki_utils.get_exclude_patterns()

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

    return sorted(unmapped)


def find_unmapped_files(target_path: str):
    project_root = ki_utils.get_project_root()
    doc_config = ki_utils.get_doc_config()

    if not project_root or not doc_config:
        print("Error: Could not resolve project root or doc_config.json")
        return

    abs_target = os.path.abspath(os.path.join(project_root, target_path))
    if not os.path.exists(abs_target):
        print(f"Error: Target path '{target_path}' does not exist.")
        return

    unmapped = get_unmapped_files(target_path)
    if unmapped:
        print(f"### Unmapped Files in '{target_path}':")
        for f in unmapped:
            print(f"- {f}")
    else:
        print(f"All files in '{target_path}' are already mapped in doc_config.json.")

if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Find files in a directory not covered by any KI in doc_config.json")
    parser.add_argument("path", help="Relative path from project root to scan")
    args = parser.parse_args()
    
    find_unmapped_files(args.path)
