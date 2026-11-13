"""
ki_context.py

Just-in-time architectural context extractor for ki-manager.
Matches target source file paths/directories/globs against doc_config.json
(`depends_on`) and ADR scope sections, extracting concise active invariants,
non-obvious details, and pitfalls within a strict character budget.
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import ki_utils
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ki_utils


_PLACEHOLDER_PATTERNS = (
    re.compile(r"^[-*]?\s*<[^>\n]{3,}>\s*$"),
    re.compile(r"^[-*]?\s*\[(?:MUST|MUST NOT)\]\s*<[^>\n]+>\s*$"),
    re.compile(r"^[-*]?\s*\*\*<[^>\n]+>\*\*:\s*<[^>\n]+>\s*$"),
    re.compile(r"^[-*]?\s*`?(?:ClassName|function_name|SymbolName|path/to/file\.ext)`?\b"),
)

_IGNORE_ADR_FILENAMES = {"000_adr_template.md", "adr_template.md"}


def _normalize_rel_path(raw: str, project_root: str) -> Tuple[str, bool]:
    """Normalizes a path or glob to project-relative POSIX form.

    Returns (normalized_path, explicitly_directory_trailing_slash).
    """
    if not raw:
        return "", False
    cleaned = str(raw).strip().strip("`\"'")
    if not cleaned:
        return "", False
    trailing_slash = cleaned.endswith("/") or cleaned.endswith("\\")

    # Convert absolute paths inside project_root to relative paths
    is_win_abs = bool(re.match(r"^[A-Za-z]:[/\\]", cleaned))
    if (os.path.isabs(cleaned) or is_win_abs) and project_root:
        try:
            rel = os.path.relpath(os.path.normpath(cleaned), os.path.normpath(project_root))
            if not rel.startswith(".."):
                cleaned = rel
        except ValueError:
            pass

    posix = cleaned.replace("\\", "/")
    posix = re.sub(r"/+", "/", posix)
    while posix.startswith("./"):
        posix = posix[2:]
    if posix != ".":
        posix = posix.rstrip("/")
    return posix, trailing_slash


def _path_key(path_str: str) -> str:
    """Case-normalizes path strings on Windows while preserving case on POSIX."""
    return path_str.lower() if os.name == "nt" else path_str


def _has_glob_chars(pattern: str) -> bool:
    return any(ch in pattern for ch in ("*", "?", "["))


def _glob_match(path_str: str, pattern: str) -> bool:
    """Matches a POSIX path against a glob pattern supporting **, *, and ?."""
    if not path_str or not pattern:
        return False

    regex_parts = ["^"]
    i = 0
    n = len(pattern)
    while i < n:
        if pattern[i : i + 3] == "**/":
            regex_parts.append("(?:.+/)?")
            i += 3
        elif pattern[i : i + 2] == "**":
            regex_parts.append(".*")
            i += 2
        elif pattern[i] == "*":
            regex_parts.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            regex_parts.append("[^/]")
            i += 1
        else:
            regex_parts.append(re.escape(pattern[i]))
            i += 1
    regex_parts.append("$")
    flags = re.IGNORECASE if os.name == "nt" else 0
    return bool(re.match("".join(regex_parts), path_str, flags=flags))


def _match_path_to_dep(
    target_norm: str,
    target_is_dir: bool,
    dep_norm: str,
    dep_is_dir: bool,
    project_root: str,
) -> bool:
    """Matches a requested target file/dir/glob against a dependency pattern."""
    if not target_norm or not dep_norm:
        return False

    t_key = _path_key(target_norm)
    d_key = _path_key(dep_norm)

    if t_key == d_key:
        return True

    if _has_glob_chars(dep_norm):
        if _glob_match(target_norm, dep_norm):
            return True
        if target_is_dir:
            # E.g. target='src/api', dep='src/api/*.py' -> check static prefix
            dep_prefix = dep_norm.split("*")[0].split("?")[0].rstrip("/")
            if dep_prefix and (
                _path_key(dep_prefix) == t_key or _path_key(dep_prefix).startswith(t_key + "/")
            ):
                return True
        return False

    if _has_glob_chars(target_norm):
        return _glob_match(dep_norm, target_norm)

    # Directory containment in either direction
    if t_key.startswith(d_key + "/"):
        return True
    if d_key.startswith(t_key + "/"):
        return True

    # Explicit filesystem check if target exists as directory
    if target_is_dir and project_root:
        target_abs = os.path.join(project_root, target_norm)
        if os.path.isdir(target_abs) and d_key.startswith(t_key + "/"):
            return True
    if dep_is_dir and project_root:
        dep_abs = os.path.join(project_root, dep_norm)
        if os.path.isdir(dep_abs) and t_key.startswith(d_key + "/"):
            return True

    return False


def _strip_comments_and_placeholders(raw_text: str) -> str:
    """Removes HTML comments, blank clutter, and unfilled template placeholders."""
    no_comments = re.sub(r"<!--[\s\S]*?-->", "", raw_text)
    cleaned_lines: List[str] = []
    for line in no_comments.splitlines():
        stripped = line.strip()
        if not stripped:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        if any(pat.match(stripped) for pat in _PLACEHOLDER_PATTERNS):
            continue
        cleaned_lines.append(line.rstrip())

    while cleaned_lines and cleaned_lines[0] == "":
        cleaned_lines.pop(0)
    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()

    return "\n".join(cleaned_lines).strip()


def _extract_h2_sections(content: str) -> List[Tuple[str, str]]:
    """Extracts all level-2 (##) sections in document order with cleaned bodies."""
    sections: List[Tuple[str, str]] = []
    lines = content.splitlines()
    current_title: Optional[str] = None
    current_lines: List[str] = []

    for line in lines:
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if current_title is not None:
                cleaned = _strip_comments_and_placeholders("\n".join(current_lines))
                if cleaned:
                    sections.append((current_title, cleaned))
            current_title = m.group(1).strip()
            current_lines = []
        elif current_title is not None:
            current_lines.append(line)

    if current_title is not None:
        cleaned = _strip_comments_and_placeholders("\n".join(current_lines))
        if cleaned:
            sections.append((current_title, cleaned))

    return sections


def _extract_ki_rules(content: str, fallback_summary: str = "") -> str:
    """Extracts priority rule sections from a KI markdown document.

    Priority:
      1. Invariants / Non-obvious Details / Common Pitfalls (or Known Issues)
      2. Overview (fallback if priority sections are missing/empty)
      3. fallback_summary from doc_config.json
    """
    sections = _extract_h2_sections(content)
    priority_blocks: List[str] = []
    overview_body = ""

    invariants_body = ""
    non_obvious_body = ""
    pitfalls_body = ""

    for title, body in sections:
        tl = title.lower()
        if "invariant" in tl:
            invariants_body = body
        elif "non-obvious" in tl or "non obvious" in tl:
            non_obvious_body = body
        elif "pitfall" in tl or "known issue" in tl:
            pitfalls_body = body
        elif "overview" in tl and not overview_body:
            overview_body = body

    if invariants_body:
        priority_blocks.append(f"**Invariants:**\n{invariants_body}")
    if non_obvious_body:
        priority_blocks.append(f"**Non-obvious Details:**\n{non_obvious_body}")
    if pitfalls_body:
        priority_blocks.append(f"**Common Pitfalls:**\n{pitfalls_body}")

    if priority_blocks:
        return "\n\n".join(priority_blocks)
    if overview_body:
        return f"**Overview:**\n{overview_body}"
    return fallback_summary.strip()


def _extract_adr_rules(content: str, fallback_summary: str = "") -> str:
    """Extracts Invariants & Rules for AI or concise Decisions Made from an ADR."""
    sections = _extract_h2_sections(content)
    invariants_body = ""
    decisions_body = ""

    for title, body in sections:
        tl = title.lower()
        if "invariant" in tl or "rules for ai" in tl:
            invariants_body = body
        elif "decision" in tl and "context" not in tl:
            decisions_body = body

    if invariants_body:
        return invariants_body

    if decisions_body:
        # Keep Decisions Made concise
        lines = [l for l in decisions_body.splitlines() if l.strip()]
        snippet = "\n".join(lines[:6])
        if len(snippet) > 450:
            snippet = snippet[:447].rstrip() + "..."
        return f"**Decision:**\n{snippet}"

    return fallback_summary.strip()


def _is_adr_entry(ki_name: str, info: dict) -> bool:
    norm_name = ki_name.replace("\\", "/").lower()
    norm_path = str(info.get("path", "")).replace("\\", "/").lower()
    base = os.path.basename(ki_name)
    return (
        "decisions/" in norm_name
        or "decisions/" in norm_path
        or bool(re.match(r"^(?:ADR[_\-])?\d+_", base))
    )


def _match_adr_text_scope(
    content: str,
    target_items: List[Tuple[str, bool]],
    matched_ki_keys: Set[str],
    project_root: str,
) -> bool:
    """Checks if an ADR's Scope & Affected Files section references target files or matched KIs."""
    sections = _extract_h2_sections(content)
    scope_body = ""
    for title, body in sections:
        tl = title.lower()
        if "scope" in tl or "affected" in tl:
            scope_body = body
            break

    if not scope_body:
        return False

    # Check references to matched KI names/basenames
    scope_lower = scope_body.lower()
    for ki_key in matched_ki_keys:
        if ki_key.lower() in scope_lower:
            return True

    # Extract path-like tokens (inside backticks or list bullets)
    tokens: Set[str] = set()
    for m in re.findall(r"`([^`\n]+)`", scope_body):
        tokens.add(m.strip())
    for line in scope_body.splitlines():
        m_bullet = re.match(r"^\s*[-*]\s+([^\s(]+)", line)
        if m_bullet:
            tokens.add(m_bullet.group(1).strip())

    for tok in tokens:
        dep_norm, dep_is_dir = _normalize_rel_path(tok, project_root)
        if not dep_norm or "://" in dep_norm:
            continue
        for t_norm, t_is_dir in target_items:
            if _match_path_to_dep(t_norm, t_is_dir, dep_norm, dep_is_dir, project_root):
                return True

    return False


def _truncate_block(text: str, max_len: int, read_hint: str = "") -> Tuple[str, bool]:
    """Truncates a text block cleanly at line/word boundaries to fit within max_len."""
    if max_len <= 0:
        return "", True
    if len(text) <= max_len:
        return text, False

    suffix = f"\n... (truncated; call `ki_read(\"{read_hint}\")`)" if read_hint else "\n... (truncated)"
    if len(suffix) >= max_len:
        suffix = "..."
    avail = max(0, max_len - len(suffix))
    cut = text[:avail]
    if "\n" in cut and cut.rfind("\n") > avail // 2:
        cut = cut[: cut.rfind("\n")]
    return cut.rstrip() + suffix, True


def format_context_markdown(result: Dict[str, Any], max_chars: int = 2000) -> str:
    """Formats context extraction result into compact Markdown within max_chars."""
    files = result.get("files", [])
    adrs = result.get("adrs", [])
    kis = result.get("kis", [])

    if not adrs and not kis:
        files_str = ", ".join(f"`{f}`" for f in files) if files else "(none)"
        return (
            f"No active KI or ADR rules matched for: {files_str}.\n"
            "Tip: Check `_OVERVIEW.ki.md` or run `ki_search` if looking for general architecture."
        )

    targets_str = ", ".join(f"`{f}`" for f in files[:5])
    if len(files) > 5:
        targets_str += f" (+{len(files) - 5} more)"

    summary_parts: List[str] = []
    if adrs:
        adr_labels = [
            f"ADR {a['id']}" + (f" [{a['status'].upper()}]" if a["status"] != "accepted" else "")
            for a in adrs
        ]
        summary_parts.append(f"ADRs ({len(adrs)}): {', '.join(adr_labels)}")
    if kis:
        ki_labels = [
            f"`{k['display_name']}`" + (f" [{k['status'].upper()}]" if k["status"] in ("stale", "poc", "stub") else "")
            for k in kis
        ]
        summary_parts.append(f"KIs ({len(kis)}): {', '.join(ki_labels)}")

    header = f"## Architectural Context for {targets_str}\n" + " | ".join(summary_parts)

    blocks: List[Tuple[str, str, str]] = []  # (heading_and_meta, body, rel_path)
    for adr in adrs:
        badge = f" [{adr['status'].upper()}]" if adr["status"] != "accepted" else ""
        head = f"### ADR {adr['id']}: {adr['title']}{badge}\n_Source: `{adr['rel_path']}`_"
        body = adr.get("rules_text") or adr.get("summary") or "(no explicit invariants)"
        blocks.append((head, body, adr["rel_path"]))

    for ki in kis:
        badge = f" [{ki['status'].upper()}]" if ki["status"] in ("stale", "poc", "stub") else ""
        stale_warn = " — *Warning: rules may be outdated, verify against code.*" if ki["status"] == "stale" else ""
        head = f"### KI: `{ki['display_name']}`{badge}\n_Source: `{ki['rel_path']}`_{stale_warn}"
        body = ki.get("rules_text") or ki.get("summary") or "(no extracted rules)"
        blocks.append((head, body, ki["rel_path"]))

    full_sections = [f"{head}\n{body}" for head, body, _ in blocks]
    full_text = header + "\n\n" + "\n\n".join(full_sections)

    if not max_chars or max_chars <= 0 or len(full_text) <= max_chars:
        result["truncated"] = False
        return full_text

    # Budgeted fit: preserve header and allocate remaining characters fairly across items
    result["truncated"] = True
    if len(header) >= max_chars:
        return header[: max(0, max_chars - 3)].rstrip() + "..."

    remaining = max_chars - len(header) - 2  # for "\n\n"
    out_sections: List[str] = []
    n_blocks = len(blocks)

    for idx, (head, body, rel_path) in enumerate(blocks):
        blocks_left = n_blocks - idx
        sep_cost = 2 if out_sections else 0
        # Reserve minimal room for subsequent headings if needed
        reserved_for_rest = max(0, (blocks_left - 1) * 40)
        slot_budget = max(80, (remaining - sep_cost - reserved_for_rest))
        if blocks_left > 1:
            fair_share = max(160, (remaining - sep_cost) // blocks_left)
            slot_budget = min(slot_budget, fair_share + 120)

        if remaining - sep_cost < len(head) + 20:
            # No space left for body, just mention remaining count
            omitted = n_blocks - idx
            note = f"_+ {omitted} more rule block(s) omitted due to `max_chars={max_chars}` limit._"
            if len(note) + sep_cost <= remaining:
                out_sections.append(note)
            break

        body_budget = remaining - sep_cost - len(head) - 1
        target_body_budget = min(body_budget, max(60, slot_budget - len(head) - 1))
        clipped_body, _ = _truncate_block(body, target_body_budget, read_hint=rel_path)
        section_str = f"{head}\n{clipped_body}"

        if len(section_str) + sep_cost > remaining:
            section_str, _ = _truncate_block(section_str, remaining - sep_cost, read_hint=rel_path)

        out_sections.append(section_str)
        remaining -= len(section_str) + sep_cost

    final_text = header + "\n\n" + "\n\n".join(out_sections)
    if len(final_text) > max_chars:
        final_text = final_text[: max(0, max_chars - 3)].rstrip() + "..."
    return final_text


def get_context_for(
    files: Optional[List[str]] = None,
    max_chars: int = 2000,
    include_poc: bool = True,
    force: bool = False,
    project_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Extracts relevant active KI and ADR rules for the given list of file paths.

    Args:
        files: List of relative/absolute paths, directories, or glob patterns.
        max_chars: Maximum formatted output length in characters.
        include_poc: Whether to include items marked 'poc' (default True).
        force: Reserved for Stage 5 deduplication cache bypass.
        project_root: Optional workspace override.
    """
    _ = force  # Hooked in Stage 5 deduplication

    if not files:
        return {
            "files": [],
            "adrs": [],
            "kis": [],
            "text": "Error: 'files' must be a non-empty list of file or directory paths.",
            "char_count": 0,
            "truncated": False,
        }

    prev_workspace = ki_utils.ACTIVE_WORKSPACE_PATH
    switched_workspace = False
    if project_root:
        norm_root = ki_utils.normalize_path(project_root)
        if not prev_workspace or os.path.normcase(prev_workspace) != os.path.normcase(norm_root):
            ki_utils.ACTIVE_WORKSPACE_PATH = norm_root
            ki_utils._CACHE.clear()
            switched_workspace = True

    try:
        proj = ki_utils.get_project_root()
        jail = ki_utils.get_knowledge_root()
        doc_config = ki_utils.get_doc_config()
        dec_dirs = ki_utils.get_decisions_dirs(proj, jail)

        # Normalize requested files
        target_items: List[Tuple[str, bool]] = []
        target_display_files: List[str] = []
        for raw_f in files:
            norm_f, is_dir_flag = _normalize_rel_path(raw_f, proj)
            if not norm_f:
                continue
            if not is_dir_flag and proj and os.path.isdir(os.path.join(proj, norm_f)):
                is_dir_flag = True
            target_items.append((norm_f, is_dir_flag))
            target_display_files.append(norm_f)

        ki_items_cfg = doc_config.get("knowledge_items", {}) or {}

        matched_kis: List[Dict[str, Any]] = []
        matched_ki_keys: Set[str] = set()
        config_matched_adrs: Dict[str, Tuple[dict, str]] = {}  # abs_or_key -> (info, key)

        # 1. Match KIs and config-registered ADRs via depends_on
        for ki_name, info in sorted(ki_items_cfg.items()):
            if not isinstance(info, dict):
                continue

            deps = info.get("depends_on", []) or []
            is_adr = _is_adr_entry(ki_name, info)

            display_name, file_path = ki_utils._resolve_ki_display_and_path(
                ki_name, info, jail, proj, dec_dirs
            )

            direct_hit = False
            # Also match if user explicitly passed the KI file itself
            rel_path_from_proj = (
                os.path.relpath(file_path, proj).replace("\\", "/")
                if file_path and proj
                else display_name
            )
            for t_norm, t_is_dir in target_items:
                if _path_key(t_norm) in (
                    _path_key(ki_name),
                    _path_key(display_name),
                    _path_key(rel_path_from_proj),
                ):
                    direct_hit = True
                    break

            dep_hit = direct_hit
            if not dep_hit:
                for dep in deps:
                    if not isinstance(dep, str):
                        continue
                    dep_norm, dep_is_dir = _normalize_rel_path(dep, proj)
                    for t_norm, t_is_dir in target_items:
                        if _match_path_to_dep(t_norm, t_is_dir, dep_norm, dep_is_dir, proj):
                            dep_hit = True
                            break
                    if dep_hit:
                        break

            if is_adr:
                if file_path:
                    config_matched_adrs[os.path.normcase(os.path.abspath(file_path))] = (info, ki_name)
                continue

            if not dep_hit:
                continue

            status = ki_utils.get_ki_status(ki_name, info, file_path)
            if status in ki_utils.INACTIVE_STATUSES or status == "draft":
                continue
            if status == "poc" and not include_poc:
                continue

            content = ""
            if file_path and os.path.isfile(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except Exception:
                    content = ""

            summary = str(info.get("summary") or info.get("description") or "").strip()
            rules_text = _extract_ki_rules(content, fallback_summary=summary) if content else summary

            matched_kis.append({
                "name": ki_name,
                "display_name": display_name,
                "rel_path": rel_path_from_proj,
                "status": status,
                "summary": summary,
                "rules_text": rules_text,
            })
            matched_ki_keys.add(ki_name)
            matched_ki_keys.add(os.path.basename(ki_name))
            matched_ki_keys.add(display_name)
            matched_ki_keys.add(os.path.basename(display_name))

        # 2. Scan ADR files in decisions directories + match by doc_config depends_on or Scope section
        seen_adr_paths: Set[str] = set()
        matched_adrs: List[Dict[str, Any]] = []

        adr_candidates: List[str] = []
        for d_dir in dec_dirs:
            if not d_dir or not os.path.isdir(d_dir):
                continue
            for fname in sorted(os.listdir(d_dir)):
                if not fname.lower().endswith(".md") or fname.lower() in _IGNORE_ADR_FILENAMES:
                    continue
                adr_candidates.append(os.path.join(d_dir, fname))

        # Include any config-registered ADR path outside standard dec_dirs
        for abs_norm_p, (info, ki_name) in config_matched_adrs.items():
            _, fp = ki_utils._resolve_ki_display_and_path(ki_name, info, jail, proj, dec_dirs)
            if fp and os.path.isfile(fp):
                adr_candidates.append(fp)

        for adr_path in adr_candidates:
            norm_abs = os.path.normcase(os.path.abspath(adr_path))
            if norm_abs in seen_adr_paths:
                continue
            seen_adr_paths.add(norm_abs)

            meta = ki_utils.parse_adr_file(adr_path, proj)
            adr_status = meta.get("status", "accepted")

            # ADR lifecycle filter: only 'accepted' and optionally 'poc'
            if adr_status == "poc":
                if not include_poc:
                    continue
            elif adr_status != "accepted":
                continue

            try:
                with open(adr_path, "r", encoding="utf-8", errors="replace") as f:
                    adr_content = f.read()
            except Exception:
                adr_content = ""

            adr_matched = False
            # Check doc_config entry depends_on (against target files OR matched KIs)
            if norm_abs in config_matched_adrs:
                info, _ = config_matched_adrs[norm_abs]
                for dep in info.get("depends_on", []) or []:
                    if not isinstance(dep, str):
                        continue
                    dep_norm, dep_is_dir = _normalize_rel_path(dep, proj)
                    if dep in matched_ki_keys or os.path.basename(dep) in matched_ki_keys:
                        adr_matched = True
                        break
                    for t_norm, t_is_dir in target_items:
                        if _match_path_to_dep(t_norm, t_is_dir, dep_norm, dep_is_dir, proj):
                            adr_matched = True
                            break
                    if adr_matched:
                        break

            # Also check ADR file's own Scope & Affected Files section
            if not adr_matched and adr_content:
                adr_matched = _match_adr_text_scope(
                    adr_content, target_items, matched_ki_keys, proj
                )

            if not adr_matched:
                continue

            rules_text = _extract_adr_rules(
                adr_content, fallback_summary=meta.get("summary", "")
            )
            matched_adrs.append({
                "id": meta.get("id", "—"),
                "title": meta.get("title", os.path.basename(adr_path)),
                "rel_path": meta.get("rel_path", os.path.basename(adr_path)),
                "status": adr_status,
                "summary": meta.get("summary", ""),
                "rules_text": rules_text,
            })

        result: Dict[str, Any] = {
            "files": target_display_files,
            "adrs": matched_adrs,
            "kis": matched_kis,
            "truncated": False,
        }
        formatted = format_context_markdown(result, max_chars=max_chars)
        result["text"] = formatted
        result["char_count"] = len(formatted)
        return result
    finally:
        if switched_workspace:
            ki_utils.ACTIVE_WORKSPACE_PATH = prev_workspace
            ki_utils._CACHE.clear()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Extract active KI/ADR context for target files.")
    parser.add_argument("files", nargs="+", help="Target file or directory paths.")
    parser.add_argument("--max-chars", type=int, default=2000, help="Maximum response characters.")
    parser.add_argument("--no-poc", action="store_true", help="Exclude poc documents.")
    parser.add_argument("--workspace", type=str, default=None, help="Explicit project root.")
    args = parser.parse_args(argv)

    res = get_context_for(
        files=args.files,
        max_chars=args.max_chars,
        include_poc=not args.no_poc,
        project_root=args.workspace,
    )
    print(res["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
