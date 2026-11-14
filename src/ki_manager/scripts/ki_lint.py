"""
ki_lint.py

Deterministic linter for ki-manager Knowledge Bases:
1. Structure checks:
   - No *.ki.md (or KI_*.md) files directly in the container root (e.g. .ki-base/).
   - _OVERVIEW.ki.md exists inside knowledge/.
2. Metadata & section checks:
   - Valid status for KIs and ADRs (using ki_utils lifecycle statuses).
   - Superseded ADRs have a valid, non-cyclic superseded_by target.
   - Active KIs have valid last_verified (YYYY-MM-DD), no leftover scaffold/TODO markers,
     and non-empty key sections.
3. Referential integrity:
   - Knowledge files are registered in doc_config.json (auto-fixable with --fix).
   - Paths in depends_on exist on disk (errors for active KIs, soft warnings for poc/draft/stub/stale,
     skipped for archived/superseded/deprecated).

Supports --staged mode to quickly lint only Git-staged knowledge files (for pre-commit hooks).
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ki_utils

OPTIONAL_KI_SECTIONS = frozenset({
    "related kis",
    "related",
    "references",
    "see also",
    "links",
})

VALID_KI_STATUSES_SET = frozenset(ki_utils.KI_STATUSES) | {"proposed"}
VALID_ADR_STATUSES_SET = frozenset(ki_utils.ADR_STATUSES) | {"proposed"}


def _make_issue(code: str, file_path: str, message: str) -> Dict[str, str]:
    return {"code": code, "file": file_path, "message": message}


def _to_rel_posix(path: str, base: str) -> str:
    try:
        rel = os.path.relpath(path, base)
    except ValueError:
        rel = path
    return rel.replace("\\", "/")


def _get_git_staged_files(project_root: str) -> Optional[Set[str]]:
    """Return normalized absolute paths of staged (ACMR) files, or None if git unavailable."""
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if res.returncode != 0:
            return None
        staged: Set[str] = set()
        for line in res.stdout.splitlines():
            p = line.strip()
            if p:
                staged.add(os.path.normcase(os.path.abspath(os.path.join(project_root, p))))
        return staged
    except Exception:
        return None


def _resolve_know_dir(project_root: str, knowledge_root: str) -> str:
    """Resolve the directory containing KI markdown files."""
    candidate = os.path.join(knowledge_root, "knowledge")
    if os.path.exists(candidate):
        return candidate
    if os.path.basename(os.path.normpath(knowledge_root)) == "knowledge":
        return knowledge_root
    # Legacy fallback: knowledge/ at project root
    proj_know = os.path.join(project_root, "knowledge")
    if os.path.exists(proj_know):
        return proj_know
    return candidate


def _extract_last_verified(content: str) -> Optional[str]:
    """Extract YYYY-MM-DD from <!-- last_verified: ... --> or YAML frontmatter."""
    m = re.search(r"<!--\s*last_verified:\s*([^\s>]+)\s*-->", content, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    if content.startswith("---"):
        lines = content.splitlines()
        for line in lines[1:]:
            if line.strip() == "---":
                break
            fm = re.match(r"^\s*last_verified\s*:\s*(.+)$", line, re.IGNORECASE)
            if fm:
                return fm.group(1).strip().strip("\"'")
    return None


def _is_valid_date(date_str: str) -> bool:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _extract_h1_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return fallback


def _parse_h2_sections(content: str) -> List[Tuple[str, str]]:
    """Return list of (section_title, body_text) for all H2 (##) sections."""
    lines = content.splitlines()
    sections: List[Tuple[str, str]] = []
    current_title: Optional[str] = None
    current_lines: List[str] = []

    in_code_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
        if not in_code_block and re.match(r"^##\s+(.+)$", stripped):
            if current_title is not None:
                sections.append((current_title, "\n".join(current_lines)))
            current_title = stripped[2:].strip()
            current_lines = []
        elif current_title is not None:
            current_lines.append(line)

    if current_title is not None:
        sections.append((current_title, "\n".join(current_lines)))

    return sections


def _strip_comments_and_whitespace(text: str) -> str:
    cleaned = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return cleaned.strip()


def _find_config_entry(
    ki_items: Dict[str, Any],
    rel_ki: str,
    filename: str,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Find matching doc_config['knowledge_items'] entry by relpath, basename, or path field."""
    rel_norm = rel_ki.replace("\\", "/")
    candidates = [
        rel_norm,
        filename,
        f"knowledge/{rel_norm}",
        f"knowledge/{filename}",
    ]
    for key in candidates:
        if key in ki_items and isinstance(ki_items[key], dict):
            return key, ki_items[key]

    for key, val in ki_items.items():
        if not isinstance(val, dict):
            continue
        key_norm = str(key).replace("\\", "/")
        if key_norm == rel_norm or os.path.basename(key_norm) == filename:
            return key, val
        path_val = str(val.get("path", "")).replace("\\", "/")
        if path_val and (path_val == rel_norm or path_val == f"knowledge/{rel_norm}" or os.path.basename(path_val) == filename):
            return key, val

    return None, None


def _dep_exists(dep: str, project_root: str, know_dir: str) -> bool:
    if not dep or not isinstance(dep, str):
        return True
    dep_clean = dep.strip()
    if any(ch in dep_clean for ch in ("*", "?", "[")):
        return bool(glob.glob(os.path.join(project_root, dep_clean)))

    candidates = [
        os.path.join(project_root, dep_clean),
        os.path.join(know_dir, dep_clean),
    ]
    return any(os.path.exists(c) for c in candidates)


def _insert_last_verified(filepath: str, content: str, today: str) -> Optional[str]:
    """Insert <!-- last_verified: YYYY-MM-DD --> atomically. Returns updated content or None on failure."""
    import tempfile

    lines = content.splitlines(keepends=True)
    res_lines: List[str] = []
    inserted = False
    for line in lines:
        res_lines.append(line)
        if not inserted and line.startswith("# "):
            res_lines.append(f"\n<!-- last_verified: {today} -->\n")
            inserted = True
    if not inserted:
        res_lines.insert(0, f"<!-- last_verified: {today} -->\n\n")
    new_content = "".join(res_lines)

    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(filepath), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(new_content)
        os.replace(tmp_path, filepath)
        return new_content
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return None


def _check_ki_file(
    filepath: str,
    rel_ki: str,
    project_root: str,
    know_dir: str,
    doc_config: Dict[str, Any],
    fix: bool,
    errors: List[Dict[str, str]],
    warnings: List[Dict[str, str]],
    fixed: List[str],
) -> bool:
    """Validate a single KI file. Returns True if doc_config was modified."""
    config_dirty = False
    rel_display = _to_rel_posix(filepath, project_root)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        errors.append(_make_issue("UNREADABLE_KI", rel_display, f"Failed to read KI file: {e}"))
        return False

    ki_items = doc_config.setdefault("knowledge_items", {})
    cfg_key, cfg_entry = _find_config_entry(ki_items, rel_ki, os.path.basename(filepath))

    # Validate explicit status in file and config
    raw_file_status = ki_utils.extract_raw_status_from_content(content, doc_type="ki")
    if raw_file_status is not None and raw_file_status.strip().lower() not in VALID_KI_STATUSES_SET:
        errors.append(
            _make_issue(
                "INVALID_STATUS",
                rel_display,
                f"Invalid KI status '{raw_file_status}'. Allowed: {', '.join(ki_utils.KI_STATUSES)}.",
            )
        )

    if cfg_entry and cfg_entry.get("status") is not None:
        raw_cfg_status = str(cfg_entry.get("status")).strip()
        if raw_cfg_status.lower() not in VALID_KI_STATUSES_SET:
            errors.append(
                _make_issue(
                    "INVALID_CONFIG_STATUS",
                    rel_display,
                    f"Invalid doc_config status '{raw_cfg_status}' for '{cfg_key}'.",
                )
            )

    status = ki_utils.get_ki_status(rel_ki, cfg_entry, filepath)

    # Registration in doc_config.json
    if cfg_entry is None:
        if fix:
            title = _extract_h1_title(content, os.path.basename(filepath))
            new_entry: Dict[str, Any] = {
                "description": title,
                "covers": [],
                "depends_on": [],
                "status": status,
            }
            ki_items[rel_ki] = new_entry
            cfg_key = rel_ki
            cfg_entry = new_entry
            config_dirty = True
            fixed.append(f"Registered '{rel_ki}' in doc_config.json (status={status}).")
        else:
            errors.append(
                _make_issue(
                    "UNREGISTERED_KI",
                    rel_display,
                    f"KI '{rel_ki}' is not registered in doc_config.json (run with --fix to register).",
                )
            )

    # Active KI metadata & section checks
    is_overview = os.path.basename(filepath) == "_OVERVIEW.ki.md"
    if status == "active":
        last_verified = _extract_last_verified(content)
        if not last_verified:
            if fix:
                today = datetime.now().strftime("%Y-%m-%d")
                updated = _insert_last_verified(filepath, content, today)
                if updated is not None:
                    content = updated
                    last_verified = today
                    fixed.append(f"Inserted '<!-- last_verified: {today} -->' into '{rel_ki}'.")
            if not last_verified:
                errors.append(
                    _make_issue(
                        "MISSING_LAST_VERIFIED",
                        rel_display,
                        "Active KI must contain '<!-- last_verified: YYYY-MM-DD -->'.",
                    )
                )
        elif not _is_valid_date(last_verified):
            errors.append(
                _make_issue(
                    "INVALID_LAST_VERIFIED",
                    rel_display,
                    f"Invalid last_verified date '{last_verified}' (expected YYYY-MM-DD).",
                )
            )

        if re.search(r"<!--\s*scaffold:\s*true\s*-->", content, re.IGNORECASE):
            errors.append(
                _make_issue(
                    "UNFINALIZED_SCAFFOLD",
                    rel_display,
                    "Active KI still has '<!-- scaffold: true -->'. Finalize content or set status to 'stub'/'draft'.",
                )
            )

        if re.search(r"<!--\s*TODO\b", content, re.IGNORECASE):
            errors.append(
                _make_issue(
                    "LEFTOVER_TODO",
                    rel_display,
                    "Active KI contains unresolved '<!-- TODO ... -->' marker.",
                )
            )

        sections = _parse_h2_sections(content)
        if not sections:
            errors.append(
                _make_issue(
                    "MISSING_SECTIONS",
                    rel_display,
                    "Active KI must contain at least one '## <Section>' heading with content.",
                )
            )
        else:
            empty_non_optional = []
            for sec_title, sec_body in sections:
                if sec_title.strip().lower() in OPTIONAL_KI_SECTIONS:
                    continue
                if not _strip_comments_and_whitespace(sec_body):
                    empty_non_optional.append(sec_title)

            if empty_non_optional:
                if is_overview and len(empty_non_optional) == len(
                    [s for s, _ in sections if s.strip().lower() not in OPTIONAL_KI_SECTIONS]
                ):
                    warnings.append(
                        _make_issue(
                            "EMPTY_OVERVIEW_STUB",
                            rel_display,
                            "_OVERVIEW.ki.md still contains template placeholders; enrich it with project details.",
                        )
                    )
                else:
                    errors.append(
                        _make_issue(
                            "EMPTY_SECTION",
                            rel_display,
                            f"Active KI has empty key section(s): {', '.join(empty_non_optional)}.",
                        )
                    )

    # Referential integrity: depends_on
    if cfg_entry:
        deps = cfg_entry.get("depends_on", [])
        if isinstance(deps, list) and status not in ("archived", "superseded", "deprecated"):
            for dep in deps:
                if not _dep_exists(dep, project_root, know_dir):
                    if status == "active":
                        errors.append(
                            _make_issue(
                                "BROKEN_DEPENDS_ON",
                                rel_display,
                                f"depends_on path '{dep}' does not exist on disk.",
                            )
                        )
                    else:
                        warnings.append(
                            _make_issue(
                                "BROKEN_DEPENDS_ON_SOFT",
                                rel_display,
                                f"depends_on path '{dep}' does not exist on disk (status={status}).",
                            )
                        )

    return config_dirty


def _is_template_adr(filepath: str) -> bool:
    name = os.path.basename(filepath).lower()
    return name == "000_adr_template.md" or (name.startswith("000_") and "template" in name)


def _collect_adr_paths(proj_root: str, know_root: str) -> List[str]:
    paths: List[str] = []
    seen: Set[str] = set()
    for d in ki_utils.get_decisions_dirs(proj_root, know_root):
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if fname.endswith(".md"):
                full = os.path.abspath(os.path.join(d, fname))
                key = os.path.normcase(full)
                if key not in seen:
                    seen.add(key)
                    paths.append(full)
    return paths


def _check_adr_files(
    adr_paths_to_check: List[str],
    all_adr_paths: List[str],
    project_root: str,
    errors: List[Dict[str, str]],
) -> int:
    """Validate ADR statuses and superseded_by references (including cycle detection)."""
    parsed_by_path: Dict[str, Dict[str, Any]] = {}
    id_to_record: Dict[str, Dict[str, Any]] = {}
    filename_to_id: Dict[str, str] = {}

    for p in all_adr_paths:
        if _is_template_adr(p):
            continue
        rec = ki_utils.parse_adr_file(p, project_root)
        parsed_by_path[p] = rec
        adr_id = rec.get("id")
        if adr_id:
            id_to_record[str(adr_id)] = rec
            filename_to_id[os.path.basename(p).lower()] = str(adr_id)

    def _resolve_target_id(raw_target: Optional[str]) -> Optional[str]:
        if not raw_target:
            return None
        val = str(raw_target).strip()
        if val in id_to_record:
            return val
        m = re.match(r"^(?:ADR\s+)?(\d{3,})", val, re.IGNORECASE)
        if m and m.group(1) in id_to_record:
            return m.group(1)
        base = os.path.basename(val).lower()
        if base in filename_to_id:
            return filename_to_id[base]
        return None

    checked = 0
    for p in adr_paths_to_check:
        if _is_template_adr(p):
            continue
        checked += 1
        rel_display = _to_rel_posix(p, project_root)
        rec = parsed_by_path.get(p) or ki_utils.parse_adr_file(p, project_root)

        try:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            raw_status = ki_utils.extract_raw_status_from_content(content, doc_type="adr")
        except Exception as e:
            errors.append(_make_issue("UNREADABLE_ADR", rel_display, f"Failed to read ADR: {e}"))
            continue

        if raw_status is not None and raw_status.strip().lower() not in VALID_ADR_STATUSES_SET:
            errors.append(
                _make_issue(
                    "INVALID_ADR_STATUS",
                    rel_display,
                    f"Invalid ADR status '{raw_status}'. Allowed: {', '.join(ki_utils.ADR_STATUSES)}.",
                )
            )

        if rec.get("status") == "superseded":
            raw_target = rec.get("superseded_by")
            if not raw_target:
                errors.append(
                    _make_issue(
                        "MISSING_SUPERSEDED_BY",
                        rel_display,
                        "Superseded ADR must declare 'superseded_by: <ID>' (or 'Superseded by ADR <ID>').",
                    )
                )
                continue

            target_id = _resolve_target_id(raw_target)
            if not target_id:
                errors.append(
                    _make_issue(
                        "BROKEN_SUPERSEDED_BY",
                        rel_display,
                        f"superseded_by target '{raw_target}' does not match any existing ADR.",
                    )
                )
                continue

            # Detect cycles along superseded_by chain
            visited: Set[str] = set()
            start_id = str(rec.get("id") or "")
            if start_id:
                visited.add(start_id)
            cur = target_id
            while cur:
                if cur in visited:
                    errors.append(
                        _make_issue(
                            "SUPERSEDED_CYCLE",
                            rel_display,
                            f"Cycle detected in ADR superseded_by chain at ADR {cur}.",
                        )
                    )
                    break
                visited.add(cur)
                nxt_rec = id_to_record.get(cur)
                cur = _resolve_target_id(nxt_rec.get("superseded_by")) if nxt_rec else None

    return checked


def lint_knowledge_base(
    project_root: Optional[str] = None,
    knowledge_root: Optional[str] = None,
    staged: bool = False,
    fix: bool = False,
) -> Dict[str, Any]:
    """Run deterministic lint checks across structure, metadata, and referential integrity."""
    prev_ws = ki_utils.ACTIVE_WORKSPACE_PATH
    switched_ws = False
    if project_root:
        norm_proj = ki_utils.normalize_path(project_root)
        if not prev_ws or os.path.abspath(prev_ws) != os.path.abspath(norm_proj):
            ki_utils.ACTIVE_WORKSPACE_PATH = norm_proj
            ki_utils._CACHE.clear()
            switched_ws = True

    try:
        proj_root = ki_utils.normalize_path(project_root) if project_root else ki_utils.get_project_root()
        know_root = ki_utils.normalize_path(knowledge_root) if knowledge_root else ki_utils.get_knowledge_root()

        errors: List[Dict[str, str]] = []
        warnings: List[Dict[str, str]] = []
        fixed: List[str] = []

        if not proj_root or not os.path.exists(proj_root):
            errors.append(_make_issue("PROJECT_ROOT_MISSING", str(proj_root), "Project root directory does not exist."))
            return {
                "ok": False,
                "errors": errors,
                "warnings": warnings,
                "fixed": fixed,
                "checked_kis": 0,
                "checked_adrs": 0,
                "staged_only": staged,
                "skipped": False,
            }

        if not know_root or not os.path.exists(know_root):
            errors.append(
                _make_issue(
                    "KB_ROOT_MISSING",
                    _to_rel_posix(know_root or "", proj_root),
                    "Knowledge container directory does not exist. Run ki_init_project first.",
                )
            )
            return {
                "ok": False,
                "errors": errors,
                "warnings": warnings,
                "fixed": fixed,
                "checked_kis": 0,
                "checked_adrs": 0,
                "staged_only": staged,
                "skipped": False,
            }

        know_dir = _resolve_know_dir(proj_root, know_root)
        doc_config = ki_utils.get_doc_config() or {}

        staged_files: Optional[Set[str]] = None
        doc_config_staged = False
        if staged:
            staged_files = _get_git_staged_files(proj_root)
            if staged_files is None:
                warnings.append(_make_issue("GIT_STAGED_UNAVAILABLE", ".", "Could not inspect git staged files; linting all files."))
            else:
                know_root_nc = os.path.normcase(os.path.abspath(know_root))
                know_dir_nc = os.path.normcase(os.path.abspath(know_dir))
                decisions_dirs_nc = [
                    os.path.normcase(os.path.abspath(os.path.join(know_root, "decisions"))),
                    os.path.normcase(os.path.abspath(os.path.join(proj_root, "decisions"))),
                ]
                doc_cfg_paths = {
                    os.path.normcase(os.path.abspath(os.path.join(know_root, "doc_config.json"))),
                    os.path.normcase(os.path.abspath(os.path.join(proj_root, "doc_config.json"))),
                }
                doc_config_staged = any(p in staged_files for p in doc_cfg_paths)

                def _is_kb_path(abs_nc: str) -> bool:
                    if abs_nc in doc_cfg_paths:
                        return True
                    for d in [know_root_nc, know_dir_nc, *decisions_dirs_nc]:
                        if abs_nc.startswith(d + os.sep) or abs_nc == d:
                            return True
                    return False

                staged_kb = [p for p in staged_files if _is_kb_path(p)]
                if not staged_kb:
                    return {
                        "ok": True,
                        "errors": [],
                        "warnings": [],
                        "fixed": [],
                        "checked_kis": 0,
                        "checked_adrs": 0,
                        "staged_only": True,
                        "skipped": True,
                    }

        # 1. Structural checks
        # 1a. No *.ki.md or KI_*.md directly in container root (when container root != knowledge dir and != project root)
        if (
            os.path.abspath(know_root) != os.path.abspath(proj_root)
            and os.path.abspath(know_root) != os.path.abspath(know_dir)
        ):
            for entry in sorted(os.listdir(know_root)):
                full = os.path.join(know_root, entry)
                if os.path.isfile(full) and (entry.endswith(".ki.md") or (entry.startswith("KI_") and entry.endswith(".md"))):
                    if staged_files is not None and not doc_config_staged:
                        if os.path.normcase(os.path.abspath(full)) not in staged_files:
                            continue
                    errors.append(
                        _make_issue(
                            "MISPLACED_KI",
                            _to_rel_posix(full, proj_root),
                            f"KI file '{entry}' must live inside 'knowledge/', not in '{os.path.basename(know_root)}/' root.",
                        )
                    )

        # 1b. knowledge/ dir and _OVERVIEW.ki.md presence
        if not os.path.exists(know_dir):
            errors.append(
                _make_issue(
                    "KNOWLEDGE_DIR_MISSING",
                    _to_rel_posix(know_dir, proj_root),
                    "Missing 'knowledge/' directory inside knowledge container.",
                )
            )
        else:
            overview_path = os.path.join(know_dir, "_OVERVIEW.ki.md")
            if not os.path.exists(overview_path):
                errors.append(
                    _make_issue(
                        "MISSING_OVERVIEW",
                        _to_rel_posix(overview_path, proj_root),
                        "Required '_OVERVIEW.ki.md' is missing from 'knowledge/' directory.",
                    )
                )

        # 2. Collect KI files
        ki_files: List[Tuple[str, str]] = []
        if os.path.exists(know_dir):
            for root, dirs, files in os.walk(know_dir):
                dirs[:] = sorted(d for d in dirs if d != "decisions" and not d.startswith("."))
                for fname in sorted(files):
                    if ki_utils.is_ki_filename(fname, include_overview=True):
                        full = os.path.join(root, fname)
                        rel_ki = _to_rel_posix(full, know_dir)
                        ki_files.append((full, rel_ki))

        if staged_files is not None and not doc_config_staged:
            ki_targets = [
                (full, rel_ki)
                for full, rel_ki in ki_files
                if os.path.normcase(os.path.abspath(full)) in staged_files
            ]
        else:
            ki_targets = ki_files

        config_dirty = False
        for full, rel_ki in ki_targets:
            if _check_ki_file(full, rel_ki, proj_root, know_dir, doc_config, fix, errors, warnings, fixed):
                config_dirty = True

        if config_dirty and fix:
            ki_utils.save_doc_config(doc_config)

        # 3. Collect & check ADR files
        all_adr_paths = _collect_adr_paths(proj_root, know_root)
        if staged_files is not None and not doc_config_staged:
            adr_targets = [
                p for p in all_adr_paths if os.path.normcase(os.path.abspath(p)) in staged_files
            ]
        else:
            adr_targets = all_adr_paths

        checked_adrs = _check_adr_files(adr_targets, all_adr_paths, proj_root, errors)

        return {
            "ok": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "fixed": fixed,
            "checked_kis": len(ki_targets),
            "checked_adrs": checked_adrs,
            "staged_only": staged,
            "skipped": False,
        }
    finally:
        if switched_ws:
            ki_utils.ACTIVE_WORKSPACE_PATH = prev_ws
            ki_utils._CACHE.clear()


def format_lint_report(result: Dict[str, Any]) -> str:
    """Format lint_knowledge_base() output into readable Markdown."""
    if result.get("skipped"):
        return "✅ ki_lint: no knowledge files staged; skipped."

    errors = result.get("errors", [])
    warnings = result.get("warnings", [])
    fixed = result.get("fixed", [])
    checked_kis = result.get("checked_kis", 0)
    checked_adrs = result.get("checked_adrs", 0)

    status_icon = "✅" if result.get("ok") else "❌"
    lines = [
        f"{status_icon} **ki_lint**: checked {checked_kis} KI(s), {checked_adrs} ADR(s) — "
        f"{len(errors)} error(s), {len(warnings)} warning(s)."
    ]

    if fixed:
        lines.append("")
        lines.append("**Auto-fixed:**")
        for item in fixed:
            lines.append(f"- [FIXED] {item}")

    if errors:
        lines.append("")
        lines.append("**Errors:**")
        for err in errors:
            lines.append(f"- [{err['code']}] `{err['file']}`: {err['message']}")

    if warnings:
        lines.append("")
        lines.append("**Warnings:**")
        for warn in warnings:
            lines.append(f"- [{warn['code']}] `{warn['file']}`: {warn['message']}")

    return "\n".join(lines)


def main():
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Lint ki-manager knowledge base.")
    parser.add_argument("--staged", action="store_true", help="Lint only Git-staged knowledge files")
    parser.add_argument("--fix", action="store_true", help="Auto-fix safe issues (e.g., register KIs in doc_config.json)")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--workspace", type=str, default=None, help="Explicit project workspace path")

    args = parser.parse_args()

    if args.workspace:
        ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(args.workspace)
    else:
        match = ki_utils.find_project_by_cwd(os.getcwd())
        if match:
            target_path = match.get("config_path") or match.get("workspace") or os.getcwd()
            ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(target_path)
        else:
            ki_utils.ACTIVE_WORKSPACE_PATH = ki_utils.normalize_path(os.getcwd())

    res = lint_knowledge_base(staged=args.staged, fix=args.fix)
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(format_lint_report(res))

    sys.exit(0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
