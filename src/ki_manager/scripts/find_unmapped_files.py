import os
import sys
import argparse
import json
from pathlib import Path

# Добавляем путь к ki_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils

def find_unmapped_files(target_path: str):
    project_root = ki_utils.get_project_root()
    doc_config = ki_utils.get_doc_config()
    
    if not project_root or not doc_config:
        print("Error: Could not resolve project root or doc_config.json")
        return

    # 1. Собираем все файлы, которые уже замаплены в doc_config.json
    mapped_paths = set()
    knowledge_items = doc_config.get("knowledge_items", {})
    
    for ki in knowledge_items.values():
        depends_on = ki.get("depends_on", [])
        for p in depends_on:
            # Превращаем в абсолютный путь для корректного сравнения
            abs_p = os.path.abspath(os.path.join(project_root, p))
            mapped_paths.add(abs_p)

    # 2. Сканируем целевую директорию
    abs_target = os.path.abspath(os.path.join(project_root, target_path))
    if not os.path.exists(abs_target):
        print(f"Error: Target path '{target_path}' does not exist.")
        return

    unmapped = []
    
    # Расширения, которые мы обычно игнорируем (артефакты компиляции и т.д.)
    ignored_exts = {'.pyc', '.pyo', '.pyd', '.obj', '.dll', '.exe', '.bin'}
    ignored_dirs = {'__pycache__', '.git', '.venv', 'node_modules'}

    for root, dirs, files in os.walk(abs_target):
        # Фильтруем игнорируемые директории
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        
        for f in files:
            if any(f.endswith(ext) for ext in ignored_exts):
                continue
                
            full_path = os.path.abspath(os.path.join(root, f))
            
            # Проверяем, замаплен ли файл напрямую
            if full_path in mapped_paths:
                continue
                
            # Проверяем, не замаплена ли родительская директория (как папка)
            is_parent_mapped = False
            for mapped in mapped_paths:
                if os.path.isdir(mapped):
                    if full_path.startswith(os.path.join(mapped, "")):
                        is_parent_mapped = True
                        break
            
            if not is_parent_mapped:
                # Возвращаем путь относительно корня проекта для удобства
                rel_to_project = os.path.relpath(full_path, project_root)
                unmapped.append(rel_to_project)

    if unmapped:
        print(f"### Unmapped Files in '{target_path}':")
        for f in sorted(unmapped):
            print(f"- {f}")
    else:
        print(f"All files in '{target_path}' are already mapped in doc_config.json.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find files in a directory not covered by any KI in doc_config.json")
    parser.add_argument("path", help="Relative path from project root to scan")
    args = parser.parse_args()
    
    find_unmapped_files(args.path)
