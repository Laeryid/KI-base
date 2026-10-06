import os
import pytest
from pathlib import Path
from ki_manager.scripts import ki_search, ki_utils


def test_stemming_and_tokenization():
    # English stemming
    assert ki_search.stem_word("searching") == "search"
    assert ki_search.stem_word("dependencies") == ki_search.stem_word("dependency") == "dependenc"
    assert ki_search.stem_word("scanners") == "scanner"

    # Russian stemming
    assert ki_search.stem_word("зависимости") == ki_search.stem_word("зависимость")
    assert ki_search.stem_word("архитектурный") == ki_search.stem_word("архитектура")

    # Tokenize camelCase, snake_case, punctuation
    tokens = ki_search.tokenize("DependencyAnalyzer_v2 testCase")
    assert "dependenc" in tokens
    assert "analyzer" in tokens
    assert "test" in tokens
    assert "case" in tokens


def test_snippet_extraction():
    content = (
        "Introduction to the system.\n\n"
        "The workspace detection engine is responsible for automatically resolving the active project root.\n\n"
        "Conclusion."
    )
    tokens = ["detect", "workspac"]
    snippet = ki_search.extract_snippet(content, tokens, max_len=80)
    assert "workspace detection" in snippet
    assert len(snippet) <= 120


def test_search_knowledge_with_temp_repo(tmp_path):
    project_dir = tmp_path / "my_project"
    project_dir.mkdir()
    ki_dir = project_dir / ".ki-base"
    ki_dir.mkdir()
    know_dir = ki_dir / "knowledge"
    know_dir.mkdir()
    decisions_dir = project_dir / "decisions"
    decisions_dir.mkdir()

    # Create dummy KI file
    ki_file = know_dir / "architecture.ki.md"
    ki_file.write_text(
        "# System Architecture\n\n"
        "## Components\n"
        "The server implements an MCP stdio communication loop and a BM25 search engine.\n",
        encoding="utf-8"
    )

    # Create dummy ADR file
    adr_file = decisions_dir / "0001_compact_facade.md"
    adr_file.write_text(
        "# ADR 1: Compact Facade Mode\n\n"
        "## Context\n"
        "Large tool listings consume context window. We introduce a compact facade mode.\n",
        encoding="utf-8"
    )

    # Search in all
    res = ki_search.search_knowledge(
        query="architecture",
        project_root=str(project_dir),
        scope="all"
    )
    assert res["total"] >= 1
    paths = [r["path"].replace("\\", "/") for r in res["results"]]
    assert any("architecture.ki.md" in p for p in paths)

    # Search for ADR specific term
    res_adr = ki_search.search_knowledge(
        query="facade",
        project_root=str(project_dir),
        scope="adr"
    )
    assert res_adr["total"] >= 1
    assert any("0001_compact_facade.md" in r["path"] for r in res_adr["results"])

    # Search scope=ki shouldn't find ADR
    res_ki_only = ki_search.search_knowledge(
        query="facade",
        project_root=str(project_dir),
        scope="ki"
    )
    assert not any("0001_compact_facade.md" in r["path"] for r in res_ki_only["results"])


def test_search_empty_query_and_corpus(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    res = ki_search.search_knowledge("", project_root=str(empty_dir))
    assert res["total"] == 0
    assert res["results"] == []


def test_search_pagination_and_formatting(tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    know_dir = project_dir / ".ki-base" / "knowledge"
    know_dir.mkdir(parents=True)

    for i in range(7):
        (know_dir / f"item_{i}.ki.md").write_text(
            f"# Item {i}\nInformation about architecture topic {i}.\n",
            encoding="utf-8"
        )

    # Test limit=3, offset=0
    res_page1 = ki_search.search_knowledge("architecture", project_root=str(project_dir), limit=3, offset=0)
    assert res_page1["total"] == 7
    assert len(res_page1["results"]) == 3
    assert res_page1["offset"] == 0

    # Test limit=3, offset=3
    res_page2 = ki_search.search_knowledge("architecture", project_root=str(project_dir), limit=3, offset=3)
    assert res_page2["total"] == 7
    assert len(res_page2["results"]) == 3
    assert res_page2["offset"] == 3
    assert res_page1["results"][0]["path"] != res_page2["results"][0]["path"]

    # Test markdown formatting
    md = ki_search.format_search_markdown(res_page1)
    assert "Found 7 result(s)" in md
    assert "showing 1-3" in md
    assert "to view more" in md

    # Empty search markdown
    empty_md = ki_search.format_search_markdown({"query": "unknown", "total": 0, "results": []})
    assert "No documentation matching" in empty_md

