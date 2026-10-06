"""
facade.py

Facade tools and catalog dispatcher for compact MCP mode.
Provides:
  - ki_tools: Tool discovery and schema inspection.
  - ki_call: Dispatcher for read-only tools.
  - ki_mutate: Dispatcher for state-modifying tools.
  - ki_read: Enhanced reader for Knowledge Items & ADRs.
  - ki_search: BM25 search facade schema and routing.
"""

import os
import re
from typing import Dict, Any, List, Optional, Tuple

from ki_manager.scripts import ki_utils

# Tool Group Mapping
TOOL_GROUPS: Dict[str, List[str]] = {
    "init_registry": [
        "ki_init_project",
        "ki_migrate_project",
        "ki_register_project",
        "ki_list_projects",
        "ki_status",
        "ki_prune_registry",
    ],
    "coverage_analysis": [
        "audit_coverage",
        "generate_dir_index",
        "analyze_dependencies",
        "analyze_all_dependencies",
        "find_unmapped_files",
        "analyze_module",
        "ki_graph_visualize",
    ],
    "scaffold": [
        "ki_scaffold",
        "ki_scaffold_status",
        "ki_finalize_scaffolds",
        "update_last_verified",
    ],
    "config_adr": [
        "add_ki_to_config",
        "edit_doc_config",
        "sync_agents_md",
        "create_adr",
    ],
    "files": [
        "read_know_file",
        "write_know_file",
        "edit_know_file",
        "make_know_dir",
    ],
    "git_state": [
        "git_checkpoint",
        "git_restore",
        "git_diff_secured",
        "save_state",
        "restore_mapping",
    ],
}


# ─── Tool Schemas ─────────────────────────────────────────────────────────────

KI_SEARCH_TOOL = {
    "name": "ki_search",
    "description": (
        "Search Knowledge Items (KI) and ADRs by keywords using BM25 ranking (pure Python). "
        "Returns matching paths, titles, relevance scores, and text snippets. "
        "Use this tool to find relevant documentation without full codebase scans."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query keywords (Russian or English, e.g. 'workspace detection' or 'управление зависимостями').",
            },
            "scope": {
                "type": "string",
                "enum": ["all", "ki", "adr"],
                "default": "all",
                "description": "Scope of search: 'all' (default), 'ki' (knowledge items), or 'adr' (architecture decision records).",
            },
            "limit": {
                "type": "integer",
                "default": 10,
                "description": "Maximum number of results to return (default: 10).",
            },
        },
        "required": ["query"],
    },
    "annotations": {
        "title": "Search Knowledge Base",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    },
}

KI_READ_TOOL = {
    "name": "ki_read",
    "description": (
        "Read a Knowledge Item (KI) or ADR markdown file. "
        "Supports optional section filtering (by markdown header) and character limits to save tokens."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "rel_path": {
                "type": "string",
                "description": "Path or filename of the Knowledge Item or ADR (e.g. 'KI_architecture.md', 'knowledge/KI_architecture.md', or '001_some.md').",
            },
            "section": {
                "type": "string",
                "description": "Optional markdown section title to extract (e.g. 'Architecture' or 'Known Issues').",
            },
            "max_chars": {
                "type": "integer",
                "description": "Optional maximum number of characters to return (truncates if exceeded).",
            },
        },
        "required": ["rel_path"],
    },
    "annotations": {
        "title": "Read Knowledge Item / ADR",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    },
}

KI_TOOLS_TOOL = {
    "name": "ki_tools",
    "description": (
        "Inspect available ki-manager tools and their schemas. "
        "Call without arguments to list all tools grouped by category. "
        "Provide 'name' to inspect the exact inputSchema of a specific tool before calling it via ki_call or ki_mutate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Optional tool name to get full JSON schema (e.g. 'audit_coverage').",
            },
            "group": {
                "type": "string",
                "description": "Optional category group filter (init_registry, coverage_analysis, scaffold, config_adr, files, git_state).",
            },
        },
    },
    "annotations": {
        "title": "Tools Catalog",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    },
}

KI_CALL_TOOL = {
    "name": "ki_call",
    "description": (
        "Execute a read-only ki-manager tool. "
        "Available tools: ki_list_projects, ki_status, audit_coverage, generate_dir_index, "
        "analyze_dependencies, analyze_all_dependencies, find_unmapped_files, analyze_module, "
        "ki_graph_visualize, ki_scaffold_status, read_know_file, git_diff_secured. "
        "Use ki_tools(name=...) to check arguments. For mutating operations, use ki_mutate."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "tool": {
                "type": "string",
                "description": "Name of the read-only tool to call.",
            },
            "args": {
                "type": "object",
                "description": "Arguments dictionary to pass to the tool.",
                "default": {},
            },
        },
        "required": ["tool"],
    },
    "annotations": {
        "title": "Call Read-Only Tool",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    },
}

KI_MUTATE_TOOL = {
    "name": "ki_mutate",
    "description": (
        "Execute a state-modifying ki-manager tool. "
        "Available tools: ki_init_project, ki_migrate_project, ki_register_project, ki_prune_registry, "
        "ki_scaffold, ki_finalize_scaffolds, update_last_verified, add_ki_to_config, edit_doc_config, "
        "sync_agents_md, create_adr, write_know_file, edit_know_file, make_know_dir, git_checkpoint, "
        "git_restore, save_state, restore_mapping. "
        "Use ki_tools(name=...) to check arguments."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "tool": {
                "type": "string",
                "description": "Name of the mutating tool to call.",
            },
            "args": {
                "type": "object",
                "description": "Arguments dictionary to pass to the tool.",
                "default": {},
            },
        },
        "required": ["tool"],
    },
    "annotations": {
        "title": "Call Mutating Tool",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
    },
}


# ─── Helper Functions ────────────────────────────────────────────────────────

def format_tools_catalog(all_tools: List[Dict[str, Any]], group_filter: Optional[str] = None) -> str:
    """Formats a concise catalog of tools by group."""
    tools_map = {t["name"]: t for t in all_tools}
    out = ["# ki-manager Tools Catalog\n"]

    groups_to_show = {}
    if group_filter:
        gf = group_filter.lower().strip()
        if gf in TOOL_GROUPS:
            groups_to_show[gf] = TOOL_GROUPS[gf]
        else:
            return f"Unknown group '{group_filter}'. Available groups: {', '.join(TOOL_GROUPS.keys())}"
    else:
        groups_to_show = TOOL_GROUPS

    for g_name, t_names in groups_to_show.items():
        out.append(f"## Group: {g_name}")
        for tn in t_names:
            t = tools_map.get(tn)
            if t:
                desc = t.get("description", "").split(".")[0].strip()
                is_ro = t.get("annotations", {}).get("readOnlyHint", False)
                caller = "ki_call" if is_ro else "ki_mutate"
                out.append(f"  - **{tn}** [{caller}]: {desc}.")
        out.append("")

    out.append("### Usage:")
    out.append("  - To view schema: `ki_tools({\"name\": \"<tool_name>\"})`")
    out.append("  - To call read-only tool: `ki_call({\"tool\": \"<name>\", \"args\": {...}})`")
    out.append("  - To call mutating tool: `ki_mutate({\"tool\": \"<name>\", \"args\": {...}})`")
    return "\n".join(out)


def validate_args_against_schema(schema: Dict[str, Any], args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Simple schema validator checking required fields and basic types."""
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    for req_field in required:
        if req_field not in args:
            return False, f"Missing required parameter '{req_field}'."

    type_mapping = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    for key, val in args.items():
        if key in properties:
            expected_type_str = properties[key].get("type")
            if expected_type_str in type_mapping:
                expected_type = type_mapping[expected_type_str]
                # Special case: bool is subclass of int in Python
                if expected_type_str == "integer" and isinstance(val, bool):
                    return False, f"Parameter '{key}' must be integer, got boolean."
                if not isinstance(val, expected_type):
                    return False, f"Parameter '{key}' must be of type {expected_type_str}, got {type(val).__name__}."

    return True, None


def extract_markdown_section(content: str, section_title: str) -> Optional[str]:
    """Finds a markdown section by title and returns its content until the next header of same/higher level."""
    if not section_title:
        return content

    sec_lower = section_title.strip().lower()
    lines = content.splitlines()
    start_idx = -1
    target_level = 0

    for i, line in enumerate(lines):
        line_s = line.strip()
        if line_s.startswith("#"):
            match = re.match(r"^(#+)\s+(.+)$", line_s)
            if match:
                level = len(match.group(1))
                h_text = match.group(2).strip().lower()
                if sec_lower in h_text:
                    start_idx = i
                    target_level = level
                    break

    if start_idx == -1:
        return None

    # Collect lines until next header with level <= target_level
    section_lines = [lines[start_idx]]
    for line in lines[start_idx + 1:]:
        line_s = line.strip()
        if line_s.startswith("#"):
            match = re.match(r"^(#+)\s+", line_s)
            if match and len(match.group(1)) <= target_level:
                break
        section_lines.append(line)

    return "\n".join(section_lines)


def render_instruction(content: str, tool_mode: str = "full", ki_dir: Optional[str] = None) -> str:
    """
    Renders dynamic instructions based on tool_mode ('full' or 'compact').

    Supports directives:
      <!-- if-compact -->
      compact content
      <!-- else-compact -->
      full content
      <!-- /if-compact -->

      <!-- if-full -->
      full only content
      <!-- /if-full -->
    """
    mode = (tool_mode or "full").lower().strip()
    is_compact = (mode == "compact")

    # 1. Handle <!-- if-compact -->...[<!-- else-compact -->...]<!-- /if-compact -->
    pattern_compact = re.compile(
        r"<!--\s*if-compact\s*-->\s*(.*?)(?:<!--\s*else-compact\s*-->\s*(.*?))?<!--\s*/if-compact\s*-->",
        re.DOTALL
    )

    def repl_compact(match):
        compact_part = match.group(1) or ""
        else_part = match.group(2) or ""
        text = compact_part if is_compact else else_part
        return text.strip("\r\n")

    rendered = pattern_compact.sub(repl_compact, content)

    # 2. Handle <!-- if-full -->...<!-- /if-full -->
    pattern_full = re.compile(
        r"<!--\s*if-full\s*-->\s*(.*?)<!--\s*/if-full\s*-->",
        re.DOTALL
    )

    def repl_full(match):
        full_part = match.group(1) or ""
        return "" if is_compact else full_part.strip("\r\n")

    rendered = pattern_full.sub(repl_full, rendered)

    # 3. Dynamic substitution for knowledge folder name
    ki_folder = ki_dir or ".ki-base"
    rendered = rendered.replace("{{KI_DIR}}", ki_folder)
    if ki_folder != ".ki-base":
        rendered = rendered.replace(".ki-base/", f"{ki_folder}/")

    return rendered
