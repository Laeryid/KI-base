"""
ki_graph_visualize.py

Generates Mermaid diagrams visualizing project structure and semantic relationships
based on Knowledge Items (KIs) and file dependencies.

Supported modes:
- 'semantic': (Default) Groups files into KI subgraphs with dependency edges between KIs.
- 'ki-only': High-level architectural map showing only KI nodes and their relationships.
- 'coverage': Semantic map including an 'Unmapped Files' cluster to highlight documentation gaps.
"""

import os
import sys
import re
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

# Universal import for ki_utils and dependencies
try:
    import ki_utils
    from ki_dependency_analyzer import KIDependencyAnalyzer
    from find_unmapped_files import get_unmapped_files
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ki_utils
    from ki_dependency_analyzer import KIDependencyAnalyzer
    from find_unmapped_files import get_unmapped_files


def sanitize_id(raw: str, prefix: str = "") -> str:
    """Creates a valid Mermaid identifier from arbitrary strings with optional prefix."""
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", raw)
    clean = re.sub(r"_+", "_", clean).strip("_")
    if prefix:
        clean = f"{prefix}_{clean}" if clean else prefix
    elif not clean or clean[0].isdigit():
        clean = f"id_{clean}" if clean else "id"
    return clean


def clean_label(text: str) -> str:
    """Escapes strings for Mermaid node labels."""
    return text.replace('"', "'").replace("\n", " ").strip()


def build_mermaid_graph(
    mode: str = "semantic",
    ki_filter: Optional[str] = None,
    direction: str = "TD",
    max_unmapped: int = 15,
) -> str:
    """
    Generates Mermaid graph markdown based on doc_config.json and dependency analysis.
    """
    direction = direction.upper() if direction.upper() in ("TD", "LR", "TB", "RL", "BT") else "TD"
    doc_config = ki_utils.get_doc_config()
    knowledge_items: Dict[str, Any] = doc_config.get("knowledge_items", {}) if doc_config else {}

    if not knowledge_items:
        return f"```mermaid\nflowchart {direction}\n  empty[\"No Knowledge Items registered in doc_config.json\"]\n```"

    analyzer = None
    try:
        analyzer = KIDependencyAnalyzer()
    except Exception:
        pass

    # Collect dependencies between KIs: source_ki -> list of (target_ki, via_file)
    edges: Set[Tuple[str, str]] = set()
    all_ki_keys = list(knowledge_items.keys())

    if analyzer:
        for ki_name in all_ki_keys:
            try:
                relations = analyzer.analyze_ki(ki_name)
                for target_ki, _ in relations:
                    if target_ki in knowledge_items:
                        edges.add((ki_name, target_ki))
            except Exception:
                pass

    # Filter logic: focus on a specific KI and its 1-hop neighborhood
    visible_kis = set(all_ki_keys)
    if ki_filter:
        norm_filter = ki_filter.strip().lower()
        matched_target = None
        for ki_name in all_ki_keys:
            base_name = os.path.splitext(ki_name)[0].lower()
            full_name = ki_name.lower()
            if norm_filter in (base_name, full_name):
                matched_target = ki_name
                break

        if matched_target:
            visible_kis = {matched_target}
            for src, dst in edges:
                if src == matched_target:
                    visible_kis.add(dst)
                elif dst == matched_target:
                    visible_kis.add(src)
        else:
            # Filter didn't match any KI
            return f"```mermaid\nflowchart {direction}\n  notFound[\"KI '{ki_filter}' not found\"]\n```"

    lines: List[str] = [f"flowchart {direction}"]

    # Render based on mode
    if mode == "ki-only":
        for ki_name in sorted(visible_kis):
            info = knowledge_items.get(ki_name, {})
            files_count = len(info.get("depends_on", []))
            ki_id = sanitize_id(ki_name, prefix="ki")
            display_title = info.get("summary") or os.path.splitext(ki_name)[0]
            lines.append(f'  {ki_id}["{clean_label(display_title)}<br/>({files_count} files)"]')

        for src, dst in sorted(edges):
            if src in visible_kis and dst in visible_kis:
                lines.append(f"  {sanitize_id(src, 'ki')} --> {sanitize_id(dst, 'ki')}")

    else:
        # Semantic or Coverage mode
        for ki_name in sorted(visible_kis):
            info = knowledge_items.get(ki_name, {})
            depends_on = info.get("depends_on", [])
            subgraph_id = sanitize_id(ki_name, prefix="sg")
            display_title = info.get("summary") or os.path.splitext(ki_name)[0]

            lines.append(f'  subgraph {subgraph_id} ["{clean_label(display_title)}"]')
            if depends_on:
                for file_path in sorted(depends_on):
                    fid = sanitize_id(f"{ki_name}_{file_path}", prefix="f")
                    basename = os.path.basename(file_path)
                    lines.append(f'    {fid}["{clean_label(basename)}"]')
            else:
                placeholder_id = sanitize_id(f"empty_{ki_name}", prefix="node")
                lines.append(f'    {placeholder_id}["(no tracked files)"]')
            lines.append("  end")

        # Dependency connections between subgraphs
        for src, dst in sorted(edges):
            if src in visible_kis and dst in visible_kis:
                lines.append(f"  {sanitize_id(src, 'sg')} --> {sanitize_id(dst, 'sg')}")

        # Coverage mode: append unmapped files cluster
        if mode == "coverage":
            try:
                unmapped = get_unmapped_files(".")
            except Exception:
                unmapped = []

            if unmapped:
                lines.append(f'  subgraph sg_unmapped ["⚠️ Unmapped Files ({len(unmapped)})"]')
                display_items = unmapped[:max_unmapped]
                for uf in display_items:
                    uf_id = sanitize_id(uf, prefix="uf")
                    lines.append(f'    {uf_id}["{clean_label(uf)}"]')
                if len(unmapped) > max_unmapped:
                    overflow_count = len(unmapped) - max_unmapped
                    lines.append(f'    uf_more["... and {overflow_count} more unmapped files"]')
                lines.append("  end")
                # Visual styling for unmapped cluster
                lines.append("  style sg_unmapped fill:#fff3cd,stroke:#ffeeba,stroke-width:2px,color:#856404")

    content = "\n".join(lines)
    return f"```mermaid\n{content}\n```"


def main():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="KI Knowledge Graph Visualizer")
    parser.add_argument(
        "--mode",
        choices=["semantic", "ki-only", "coverage"],
        default="semantic",
        help="Visualization mode (default: semantic)",
    )
    parser.add_argument(
        "--ki",
        help="Filter and focus on a specific KI and its direct neighbors",
    )
    parser.add_argument(
        "--direction",
        choices=["TD", "LR", "TB", "RL", "BT"],
        default="TD",
        help="Mermaid flowchart direction (default: TD)",
    )
    args = parser.parse_args()

    graph_markdown = build_mermaid_graph(
        mode=args.mode,
        ki_filter=args.ki,
        direction=args.direction,
    )
    print(graph_markdown)


if __name__ == "__main__":
    main()
