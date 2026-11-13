"""
ki_search.py

Lightweight, dependency-free search engine for Knowledge Items (KI) and ADRs.
Uses BM25 ranking with field weights, bilingual (RU/EN) stemming, and snippet generation.
"""

import os
import re
import math
from typing import List, Dict, Any, Optional
from pathlib import Path

from ki_manager.scripts import ki_utils


# ─── Bilingual Stemmer & Tokenizer ───────────────────────────────────────────

_RU_ENDINGS_RE = re.compile(
    r"(?:н(?:ый|ий|ая|яя|ое|ее|ые|ие|ого|его|ому|ему|ым|им|ых|их|ую|юю|ой|ей)|"
    r"овавш|евavsh|ивш|ывш|вшись|вши|"
    r"ости|ость|остей|ями|ами|ях|ах|ов|ев|ей|ом|ем|ам|ям|"
    r"ого|его|ому|ему|ыми|ых|их|ую|юю|ое|ее|ая|яя|ый|ий|ой|ей|"
    r"и|ы|а|я|о|е|ь|ю|у)$",
    re.IGNORECASE
)

_EN_ENDINGS_RE = re.compile(
    r"(?:ational|tional|enci|anci|izer|bli|alli|entli|eli|ousli|"
    r"ization|ation|ator|alism|iveness|fulness|ousness|aliti|"
    r"iviti|biliti|sses|ies|ing|ed|ly|ment|ness|tion|sion|able|ible|s|y)$",
    re.IGNORECASE
)


def stem_word(word: str) -> str:
    """Fast, lightweight stemmer for Russian and English words."""
    w = word.lower()
    if len(w) < 4:
        return w

    # Russian Cyrillic range check
    if any("\u0400" <= c <= "\u04FF" for c in w):
        stemmed = _RU_ENDINGS_RE.sub("", w)
        return stemmed if len(stemmed) >= 3 else w
    else:
        stemmed = _EN_ENDINGS_RE.sub("", w)
        return stemmed if len(stemmed) >= 3 else w


def tokenize(text: str) -> List[str]:
    """Tokenizes text, splitting camelCase, snake_case and removing punctuation."""
    if not text:
        return []
    # Split camelCase / PascalCase
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    tokens = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_]+", s)
    result = []
    for tok in tokens:
        # Also split on underscores if any
        parts = tok.split("_")
        for p in parts:
            if p:
                result.append(stem_word(p))
    return result


# ─── Document Parsing & Index Cache ──────────────────────────────────────────

_DOC_CACHE: Dict[str, Dict[str, Any]] = {}


def parse_markdown_doc(file_path: str, doc_type: str, project_root: str) -> Optional[Dict[str, Any]]:
    """Extracts metadata, headers, and weighted tokens from a Markdown file."""
    try:
        mtime = os.path.getmtime(file_path)
    except OSError:
        return None

    cached = _DOC_CACHE.get(file_path)
    if cached and cached.get("mtime") == mtime:
        return cached["doc"]

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return None

    # Title extraction: first # header or filename
    title = ""
    headers = []
    for line in content.splitlines():
        line_s = line.strip()
        if line_s.startswith("#"):
            h_text = line_s.lstrip("#").strip()
            if not title:
                title = h_text
            headers.append(h_text)

    if not title:
        title = Path(file_path).stem

    # Relative path from project root
    try:
        rel_path = os.path.relpath(file_path, project_root).replace("\\", "/")
    except Exception:
        rel_path = file_path.replace("\\", "/")

    raw_status = ki_utils.extract_raw_status_from_content(content, doc_type=doc_type)
    status = ki_utils.normalize_status(raw_status, doc_type=doc_type)
    superseded_by = ki_utils.extract_superseded_by_from_content(content) if doc_type == "adr" else None
    adr_id = ""
    if doc_type == "adr":
        m_id = re.match(r"^(\d+)", os.path.basename(file_path))
        if m_id:
            adr_id = m_id.group(1)

    title_tokens = tokenize(title)
    headers_tokens = tokenize(" ".join(headers))
    path_tokens = tokenize(rel_path)
    body_tokens = tokenize(content)

    # Weighted term counts
    # Weights: Title: 5.0, Headers: 3.0, Path: 2.0, Body: 1.0
    term_counts: Dict[str, float] = {}

    def _add_counts(toks: List[str], weight: float):
        for t in toks:
            term_counts[t] = term_counts.get(t, 0.0) + weight

    _add_counts(title_tokens, 5.0)
    _add_counts(headers_tokens, 3.0)
    _add_counts(path_tokens, 2.0)
    _add_counts(body_tokens, 1.0)

    total_weighted_len = (
        len(title_tokens) * 5.0 +
        len(headers_tokens) * 3.0 +
        len(path_tokens) * 2.0 +
        len(body_tokens) * 1.0
    )

    doc_data = {
        "file_path": file_path,
        "rel_path": rel_path,
        "title": title,
        "doc_type": doc_type,
        "status": status,
        "has_explicit_status": bool(raw_status),
        "superseded_by": superseded_by,
        "adr_id": adr_id,
        "content": content,
        "term_counts": term_counts,
        "weighted_len": max(1.0, total_weighted_len),
    }

    _DOC_CACHE[file_path] = {"mtime": mtime, "doc": doc_data}
    return doc_data


# ─── Snippet Generation ──────────────────────────────────────────────────────

def extract_snippet(content: str, query_tokens: List[str], max_len: int = 220) -> str:
    """Extracts a readable text snippet around the first matching term."""
    if not content or not query_tokens:
        clean = " ".join(content.split())
        return clean[:max_len] + ("..." if len(clean) > max_len else "")

    lower_content = content.lower()
    best_pos = -1

    # Try finding exact query terms first
    for tok in query_tokens:
        pos = lower_content.find(tok)
        if pos != -1 and (best_pos == -1 or pos < best_pos):
            best_pos = pos

    if best_pos == -1:
        # Fallback to first line of text
        clean = " ".join(content.split())
        return clean[:max_len] + ("..." if len(clean) > max_len else "")

    # Window around best_pos
    start = max(0, best_pos - 60)
    end = min(len(content), best_pos + max_len - 60)

    # Adjust to word boundaries
    if start > 0:
        sp = content.find(" ", start)
        if sp != -1 and sp < best_pos:
            start = sp + 1
    if end < len(content):
        ep = content.rfind(" ", best_pos, end)
        if ep != -1 and ep > best_pos:
            end = ep

    snippet = " ".join(content[start:end].split())
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."
    return snippet


# ─── BM25 Search Engine ──────────────────────────────────────────────────────

def search_knowledge(
    query: str,
    project_root: Optional[str] = None,
    scope: str = "all",
    limit: int = 5,
    offset: int = 0,
    page: Optional[int] = None,
    include_inactive: bool = False,
    k1: float = 1.5,
    b: float = 0.75,
) -> Dict[str, Any]:
    """
    Searches Knowledge Items and ADRs with BM25 ranking.

    :param query: Search string (e.g. "workspace detection" or "dependency management")
    :param project_root: Root path of the project. If None, resolved via ki_utils.
    :param scope: "all", "ki", or "adr".
    :param limit: Max number of results to return (default: 5).
    :param offset: Offset index for pagination (default: 0).
    :param page: 1-based page number for pagination (calculates offset if provided).
    :param include_inactive: If True, includes superseded/deprecated/archived items (penalized).
    :param k1: BM25 k1 parameter.
    :param b: BM25 b parameter.
    """
    if not project_root:
        project_root = ki_utils.get_project_root()
    if not project_root:
        return {"error": "No project root found. Run ki_init_project or specify workspace.", "results": []}

    if page is not None:
        try:
            p = int(page)
            if p > 0:
                offset = (p - 1) * limit
        except (ValueError, TypeError):
            pass

    knowledge_root = ki_utils.get_knowledge_root()
    if not knowledge_root or not os.path.exists(knowledge_root) or not ki_utils.is_subpath(knowledge_root, project_root):
        for cand in [
            os.path.join(project_root, ".ki-base", "knowledge"),
            os.path.join(project_root, "knowledge"),
            os.path.join(project_root, ".know", "knowledge"),
            os.path.join(project_root, ".know"),
        ]:
            if os.path.exists(cand) and os.path.isdir(cand):
                knowledge_root = cand
                break

    q_tokens = tokenize(query)
    if not q_tokens:
        return {"query": query, "total": 0, "offset": offset, "limit": limit, "page": 1, "total_pages": 1, "results": []}

    docs: List[Dict[str, Any]] = []
    doc_config = ki_utils.get_doc_config() or {}
    cfg_items = doc_config.get("knowledge_items", {})

    # 1. Collect Knowledge Items
    if scope in ("all", "ki") and knowledge_root and os.path.exists(knowledge_root):
        for root, dirs, files in os.walk(knowledge_root):
            dirs[:] = [dn for dn in dirs if dn.lower() != "decisions"]
            for f in files:
                if f.endswith(".md"):
                    full_p = os.path.join(root, f)
                    d = parse_markdown_doc(full_p, "ki", project_root)
                    if d:
                        if not d.get("has_explicit_status"):
                            meta = cfg_items.get(f) or cfg_items.get(d["rel_path"]) or {}
                            if meta.get("status"):
                                d = dict(d)
                                d["status"] = ki_utils.normalize_status(str(meta["status"]), doc_type="ki")
                        docs.append(d)

    # 2. Collect ADRs
    adr_records_for_chain: List[Dict[str, Any]] = []
    if scope in ("all", "adr"):
        jail_for_decisions = (
            os.path.dirname(knowledge_root)
            if knowledge_root and os.path.basename(knowledge_root) == "knowledge"
            else knowledge_root
        )
        candidates = ki_utils.get_decisions_dirs(project_root, jail_for_decisions)
        seen_adrs = set()
        for c in candidates:
            if os.path.exists(c) and os.path.isdir(c):
                for f in os.listdir(c):
                    if f.endswith(".md") and f not in seen_adrs:
                        seen_adrs.add(f)
                        full_p = os.path.join(c, f)
                        d = parse_markdown_doc(full_p, "adr", project_root)
                        if d:
                            docs.append(d)
                            if d.get("adr_id"):
                                adr_records_for_chain.append({"id": d["adr_id"], "superseded_by": d.get("superseded_by")})

    if not include_inactive:
        docs = [d for d in docs if d.get("status", "active") not in ki_utils.INACTIVE_STATUSES]

    total_docs = len(docs)
    if total_docs == 0:
        return {"query": query, "total": 0, "offset": offset, "limit": limit, "page": 1, "total_pages": 1, "results": []}

    avg_dl = sum(d["weighted_len"] for d in docs) / total_docs

    # Document frequency for query terms
    df: Dict[str, int] = {}
    for t in set(q_tokens):
        df[t] = sum(1 for d in docs if t in d["term_counts"])

    # Score documents
    scored_results = []
    for d in docs:
        score = 0.0
        tc = d["term_counts"]
        doc_len = d["weighted_len"]
        len_norm = 1.0 - b + b * (doc_len / avg_dl)

        for t in q_tokens:
            if t not in tc:
                continue
            n_t = df.get(t, 0)
            idf = math.log(((total_docs - n_t + 0.5) / (n_t + 0.5)) + 1.0)
            f = tc[t]
            term_score = idf * (f * (k1 + 1.0)) / (f + k1 * len_norm)
            score += term_score

        if score > 0.001:
            doc_status = d.get("status", "active")
            if doc_status in ki_utils.INACTIVE_STATUSES:
                score *= 0.25

            snippet = extract_snippet(d["content"], q_tokens)
            res_entry: Dict[str, Any] = {
                "path": d["rel_path"],
                "title": d["title"],
                "type": d["doc_type"],
                "status": doc_status,
                "score": round(score, 3),
                "snippet": snippet,
            }
            if doc_status == "superseded":
                chain = ki_utils.resolve_superseding_chain(d.get("adr_id", ""), adr_records_for_chain)
                target_id = chain[-1] if chain else d.get("superseded_by")
                if target_id:
                    res_entry["superseded_by"] = target_id
            scored_results.append(res_entry)

    scored_results.sort(key=lambda x: x["score"], reverse=True)
    total_count = len(scored_results)
    safe_offset = max(0, offset)
    final_results = scored_results[safe_offset : safe_offset + limit]
    current_page = (safe_offset // limit) + 1 if limit > 0 else 1
    total_pages = max(1, math.ceil(total_count / limit)) if limit > 0 else 1

    return {
        "query": query,
        "total": total_count,
        "offset": safe_offset,
        "limit": limit,
        "page": current_page,
        "total_pages": total_pages,
        "results": final_results,
    }


def format_search_markdown(search_dict: Dict[str, Any]) -> str:
    """Formats search results into a clean, compact Markdown summary."""
    query = search_dict.get("query", "")
    total = search_dict.get("total", 0)
    results = search_dict.get("results", [])
    offset = search_dict.get("offset", 0)
    limit = search_dict.get("limit", 5)
    page = search_dict.get("page")
    total_pages = search_dict.get("total_pages")

    if total == 0 or not results:
        return f'No documentation matching "{query}" found.'

    if page is None and limit > 0:
        page = (offset // limit) + 1
    if total_pages is None and limit > 0:
        total_pages = max(1, math.ceil(total / limit))

    start_idx = offset + 1
    end_idx = offset + len(results)
    out = [f'Found {total} result(s) for "{query}" [Page {page}/{total_pages} (showing {start_idx}-{end_idx})]:\n']

    if end_idx < total:
        next_page = (page or 1) + 1
        out.append(f'> 💡 **Next page**: `ki_search(query="{query}", page={next_page})` (or `offset={end_idx}`)\n')

    for i, r in enumerate(results, start=start_idx):
        doc_type = r.get("type", "ki").upper()
        title = r.get("title", "")
        path = r.get("path", "")
        score = r.get("score", 0.0)
        snippet = r.get("snippet", "").strip()
        status = r.get("status", "active")

        badge = ""
        if status == "superseded":
            sup_by = r.get("superseded_by")
            badge = f" [SUPERSEDED -> ADR {sup_by}]" if sup_by else " [SUPERSEDED]"
        elif status in ("deprecated", "archived", "poc", "draft", "stale", "stub"):
            badge = f" [{status.upper()}]"

        out.append(f"{i}. [{doc_type}]{badge} **{title}** (`{path}`, score: {score})")
        if snippet:
            out.append(f"   > {snippet}")

    if end_idx < total:
        next_page = (page or 1) + 1
        out.append(f"\n*Showing {end_idx} of {total} results. Call `ki_search(query='{query}', page={next_page})` (or `offset={end_idx}`) to view more.*")

    return "\n".join(out)
