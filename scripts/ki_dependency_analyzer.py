"""
ki_dependency_analyzer.py

Analyzes dependencies between Knowledge Items based on static code analysis.
This tool follows the 'No Russian' and 'No Hardcoded Paths' rules.
- Uses ki_utils.py for path resolution.
- Uses doc_config.json for module tracking.
"""

import os
import re
import ast
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

# Universal import for ki_utils
try:
    import ki_utils
    from knowledge_engine import KnowledgeEngine
except ImportError:
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import ki_utils
    from knowledge_engine import KnowledgeEngine

class KIDependencyAnalyzer:
    def __init__(self):
        self.project_root = Path(ki_utils.get_project_root())
        self.knowledge_root = Path(ki_utils.get_knowledge_root())
        self.doc_config = ki_utils.get_doc_config()
        self.file_to_ki = self._build_reverse_index()
        self.root_packages = self._get_root_packages()

    def _build_reverse_index(self) -> Dict[str, str]:
        """Maps project-relative file paths to KI filenames."""
        index = {}
        ki_items = self.doc_config.get("knowledge_items", {})
        for ki_name, info in ki_items.items():
            for dep in info.get("depends_on", []):
                norm_path = os.path.normpath(dep).replace("\\", "/")
                index[norm_path] = ki_name
        return index

    def _get_root_packages(self) -> List[str]:
        """Extracts root package names (e.g., 'app', 'ui') from tracked_modules."""
        modules = self.doc_config.get("coverage_settings", {}).get("tracked_modules", [])
        return [m[0] for m in modules if isinstance(m, list) and len(m) > 0]

    def extract_python_imports(self, file_path: Path) -> Set[str]:
        """Extracts imports from a Python file using AST."""
        imports = set()
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(file_path))
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        level_prefix = "." * node.level
                        imports.add(f"{level_prefix}{node.module}")
        except Exception as e:
            print(f"Error parsing Python file {file_path}: {e}")
        return imports

    def extract_ts_imports(self, file_path: Path) -> Set[str]:
        """Extracts imports from TS/TSX files using Regex."""
        imports = set()
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Match: from 'path' or import 'path'
            matches = re.finditer(r"from\s+['\"]([^'\"]+)['\"]|import\s+['\"]([^'\"]+)['\"]", content)
            for match in matches:
                path = match.group(1) or match.group(2)
                if path:
                    imports.add(path)
        except Exception as e:
            print(f"Error reading TS file {file_path}: {e}")
        return imports

    def resolve_import(self, import_str: str, source_file: Path) -> Optional[str]:
        """Resolves an import string to a project-relative path."""
        # 1. Internal absolute imports based on root packages
        for pkg in self.root_packages:
            if import_str == pkg or import_str.startswith(f"{pkg}."):
                possible_path = Path(*import_str.split("."))
                for suffix in [".py", "/__init__.py", ".ts", ".tsx"]:
                    p = possible_path.with_suffix(suffix) if not suffix.startswith("/") else possible_path / suffix.lstrip("/")
                    if (self.project_root / p).exists():
                        return str(p).replace("\\", "/")
                # Check directory
                if (self.project_root / possible_path).is_dir():
                    return str(possible_path).replace("\\", "/")

        # 2. Relative imports
        if import_str.startswith("."):
            m = re.match(r"^(\.+)(.*)", import_str)
            if not m: return None
            dots, remaining = m.groups()
            levels = len(dots)
            parts = remaining.split(".") if remaining else []
            base = source_file.parent
            for _ in range(levels - 1):
                base = base.parent
            
            resolved = base.joinpath(*parts)
            try:
                rel_to_root = os.path.relpath(resolved, self.project_root)
                for suffix in [".py", ".ts", ".tsx", "/__init__.py"]:
                     p = Path(rel_to_root + suffix) if not suffix.startswith("/") else Path(rel_to_root) / suffix.lstrip("/")
                     if (self.project_root / p).exists():
                         return str(p).replace("\\", "/")
                if (self.project_root / rel_to_root).is_dir():
                     return str(rel_to_root).replace("\\", "/")
            except (ValueError, OSError):
                pass

        return None

    def analyze_ki(self, ki_name: str) -> List[Tuple[str, str]]:
        """Analyzes all files covered by a KI and returns related KIs."""
        files = self.doc_config.get("knowledge_items", {}).get(ki_name, {}).get("depends_on", [])
        related_results = []
        seen_targets = set() # (target_ki, via_file)

        for rel_path in files:
            abs_path = self.project_root / rel_path
            if not abs_path.exists():
                continue

            imports = set()
            if abs_path.suffix == ".py":
                imports = self.extract_python_imports(abs_path)
            elif abs_path.suffix in [".ts", ".tsx"]:
                imports = self.extract_ts_imports(abs_path)

            for imp in imports:
                resolved = self.resolve_import(imp, abs_path)
                if resolved and resolved in self.file_to_ki:
                    target_ki = self.file_to_ki[resolved]
                    if target_ki != ki_name and (target_ki, resolved) not in seen_targets:
                        related_results.append((target_ki, resolved))
                        seen_targets.add((target_ki, resolved))
        
        return sorted(related_results)

    def update_ki(self, ki_name: str, relations: List[Tuple[str, str]]):
        """Updates the markdown file of a KI with 'Related KIs' section."""
        # KI directory is assumed to be 'knowledge' under knowledge_root as per AGENTS.md
        ki_path = self.knowledge_root / "knowledge" / ki_name
        if not ki_path.exists():
            print(f"Skipping update: KI file not found at {ki_path}")
            return

        with open(ki_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_section = ["\n", "## Related KIs\n"]
        for target_ki, via in relations:
            new_section.append(f"- [[{target_ki}]] (via `{via}`)\n")
        new_section.append("\n")

        start_idx = -1
        end_idx = -1
        for i, line in enumerate(lines):
            if line.strip() == "## Related KIs":
                start_idx = i
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith("## "):
                        end_idx = j
                        break
                if end_idx == -1:
                    end_idx = len(lines)
                break

        if start_idx != -1:
            lines[start_idx:end_idx] = new_section
        else:
            insert_pos = len(lines)
            target_markers = ["## Architecture", "## Architecture & Flow", "## Non-obvious Details"]
            for i, line in enumerate(lines):
                if any(line.startswith(m) for m in target_markers):
                    insert_pos = i
                    break
            lines.insert(insert_pos, "".join(new_section))

        with open(ki_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"Updated {ki_name} with {len(relations)} relations.")

def main():
    parser = argparse.ArgumentParser(description="KI Dependency Analyzer (Internal Tool)")
    parser.add_argument("--ki", help="Analyze a specific KI file (e.g. KI_orchestration.md)")
    parser.add_argument("--changed", action="store_true", help="Analyze KIs affected by current modifications")
    parser.add_argument("--all", action="store_true", help="Analyze all KIs in doc_config.json")
    args = parser.parse_args()

    analyzer = KIDependencyAnalyzer()

    if args.ki:
        relations = analyzer.analyze_ki(args.ki)
        analyzer.update_ki(args.ki, relations)
    elif args.all:
        ki_items = analyzer.doc_config.get("knowledge_items", {})
        print(f"Analyzing all {len(ki_items)} KIs...")
        for ki_name in ki_items.keys():
            relations = analyzer.analyze_ki(ki_name)
            analyzer.update_ki(ki_name, relations)
    elif args.changed:
        engine = KnowledgeEngine(analyzer.project_root)
        modified, new, _ = engine.check_for_changes()
        affected_ki_map = engine.get_affected_ki_map(modified + new)
        
        for ki_name in affected_ki_map.keys():
            relations = analyzer.analyze_ki(ki_name)
            analyzer.update_ki(ki_name, relations)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
