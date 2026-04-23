<!-- last_verified: 2026-04-22 -->
# KI: Knowledge Dependency Analysis

## Overview
An automated tool for maintaining links between Knowledge Items (KI) based on static analysis of imports in the project's source code. The tool matches imported files with corresponding KIs via the `doc_config.json` configuration and updates the "Related KIs" section.

## Key Components
| Class / Function | File | Purpose |
|---|---|---|
| `KIDependencyAnalyzer` | `.know/scripts/ki_dependency_analyzer.py` | Main class coordinating import collection and Markdown file updates. |
| `extract_python_imports` | `.know/scripts/ki_dependency_analyzer.py` | Python file analysis using AST (Abstract Syntax Tree) for accurate import extraction. |
| `extract_ts_imports` | `.know/scripts/ki_dependency_analyzer.py` | TypeScript/TSX file analysis using regular expressions to find paths in `import/from`. |
| `resolve_import` | `.know/scripts/ki_dependency_analyzer.py` | Resolution of import paths (absolute and relative) into relative paths within the project. |

## Related KIs

## Non-obvious Details
- **Analysis Methods**: 
    - For **Python**, AST parsing is used, which allows ignoring commented-out code and correctly handling `from ... import ...`.
    - For **TypeScript**, Regex-based search is used, focusing on string literals of paths.
- **Resolution Algorithm**:
    - **Absolute Imports**: Checked against the `tracked_modules` list in `doc_config.json`. If an import starts with the name of one of these modules (e.g., `app`), it is considered internal.
    - **Relative Imports**: Supports resolution of "dots" (`.`, `..`) relative to the current file's location.
- **Mapping (Reverse Index)**: The tool builds a reverse index from `doc_config.json`, linking each file in `depends_on` to a KI name. If a file is imported but not listed in any `depends_on`, no link will be created.
- **Markdown Update**:
    - The tool searches for the `## Related KIs` section. If found, it is **completely overwritten**.
    - If the section is missing, it is inserted before the "Non-obvious Details" or "Architecture" sections.
    - Entry format: `- [[KI_name.md]] (via `path/to/imported/file.py`)`.

## Common Pitfalls
- **Manual Edits Loss**: Any manual changes inside the `## Related KIs` block will be **removed** during the next analyzer run. 
- **Missing Extensions**: If an import refers to a file or directory not registered in `doc_config.json`, the analyzer will ignore this link.
- **Circular Dependencies**: The analyzer does not create a link from a KI to itself but correctly displays cycles between different KIs.
- **Docker-only Files**: Files located inside the Docker context and not listed in `doc_config.json` do not participate in dependency analysis.
