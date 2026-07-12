import os
import sys
import argparse
import io
from typing import Dict, List, Optional

# Добавляем путь к скриптам, чтобы импортировать ki_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils

def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"

def get_tracked_files(config: Dict) -> Dict[str, str]:
    """Возвращает мапу {путь_к_файлу: имя_KI}"""
    tracked = {}
    ki_items = config.get("knowledge_items", {})
    for ki_name, ki_data in ki_items.items():
        for file_path in ki_data.get("depends_on", []):
            tracked[os.path.normpath(file_path)] = ki_name
    return tracked

def analyze_path(target_path: str, recursive: bool = False):
    project_root = ki_utils.get_project_root()
    config = ki_utils.get_doc_config()
    tracked_map = get_tracked_files(config)
    
    # Резолвим абсолютный путь
    abs_target = os.path.normpath(os.path.join(project_root, target_path))

    if not os.path.exists(abs_target):
        print(f"Error: Path {target_path} not found.")
        return

    print(f"### Analysis for: `{target_path}`")
    print("| Status | File / Directory | Size | KI Link | Density |")
    print("|:---:|:---|:---|:---|:---|")

    items = []
    if os.path.isfile(abs_target):
        items = [abs_target]
    elif os.path.isdir(abs_target):
        if recursive:
            for root, dirs, files in os.walk(abs_target):
                if any(part in root.split(os.sep) for part in ["__pycache__", ".git", "node_modules", "venv", ".venv"]):
                    continue
                for name in files:
                    items.append(os.path.join(root, name))
        else:
            for name in os.listdir(abs_target):
                items.append(os.path.join(abs_target, name))

    for item_path in sorted(items):
        try:
            rel_path = os.path.relpath(item_path, project_root)
            is_dir = os.path.isdir(item_path)
            size = 0
            if is_dir:
                for root, _, files in os.walk(item_path):
                    for f in files:
                        fp = os.path.join(root, f)
                        if os.path.exists(fp):
                            size += os.path.getsize(fp)
            else:
                size = os.path.getsize(item_path)

            ki_name = tracked_map.get(os.path.normpath(rel_path), "")
            status = "✅" if ki_name else "❌"
            
            density = "-"
            if ki_name:
                ki_path = os.path.join(ki_utils.get_knowledge_root(), "knowledge", ki_name)
                if os.path.exists(ki_path):
                    ki_size = os.path.getsize(ki_path)
                    if ki_size > 0:
                        density_val = size / ki_size
                        density = f"{density_val:.1f} B_code/B_doc"
            
            name_display = f"`{os.path.basename(item_path)}`" + ("/" if is_dir else "")
            print(f"| {status} | {name_display} | {format_size(size)} | {ki_name} | {density} |")
        except:
            continue

def main():
    # Исправление кодировки для Windows при прямом запуске
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Analyze module statistics with knowledge context.")
    parser.add_argument("path", help="Path relative to project root")
    parser.add_argument("--recursive", action="store_true", help="Recursive analysis")
    
    args = parser.parse_args()
    analyze_path(args.path, args.recursive)

if __name__ == "__main__":
    main()
