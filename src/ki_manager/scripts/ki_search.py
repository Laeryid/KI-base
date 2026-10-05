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
    limit: int = 10,
    k1: float = 1.5,
    b: float = 0.75,
) -> Dict[str, Any]:
    """
    Searches Knowledge Items and ADRs with BM25 ranking.

    :param query: Search string (e.g. "workspace detection" or "управление зависимостями")
    :param project_root: Root path of the project. If None, resolved via ki_utils.
    :param scope: "all", "ki", or "adr".
    :param limit: Max number of results to return.
    :param k1: BM25 k1 parameter.
    :param b: BM25 b parameter.
    """
    if not project_root:
        project_root = ki_utils.get_project_root()
    if not project_root:
        return {"error": "No project root found. Run ki_init_project or specify workspace.", "results": []}

    knowledge_root = ki_utils.get_knowledge_root()
    if not knowledge_root or not os.path.exists(knowledge_root) or not os.path.normcase(os.path.abspath(knowledge_root)).startswith(os.path.normcase(os.path.abspath(project_root))):
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
        return {"query": query, "total": 0, "results": []}

    docs: List[Dict[str, Any]] = []

    # 1. Collect Knowledge Items
    if scope in ("all", "ki") and knowledge_root and os.path.exists(knowledge_root):
        for root, _, files in os.walk(knowledge_root):
            for f in files:
                if f.endswith(".md"):
                    full_p = os.path.join(root, f)
                    d = parse_markdown_doc(full_p, "ki", project_root)
                    if d:
                        docs.append(d)

    # 2. Collect ADRs
    if scope in ("all", "adr"):
        candidates = ki_utils.get_decisions_dirs(project_root, knowledge_root)
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

    total_docs = len(docs)
    if total_docs == 0:
        return {"query": query, "total": 0, "results": []}

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
            snippet = extract_snippet(d["content"], q_tokens)
            scored_results.append({
                "path": d["rel_path"],
                "title": d["title"],
                "type": d["doc_type"],
                "score": round(score, 3),
                "snippet": snippet,
            })

    scored_results.sort(key=lambda x: x["score"], reverse=True)
    final_results = scored_results[:limit]

    return {
        "query": query,
        "total": len(scored_results),
        "results": final_results,
    }
