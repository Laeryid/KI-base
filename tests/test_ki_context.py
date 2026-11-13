import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / "src" / "ki_manager" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import ki_context


def _setup_workspace(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    kb = proj / ".ki-base"
    know = kb / "knowledge"
    dec = kb / "decisions"
    src_auth = proj / "src" / "auth"
    src_api = proj / "src" / "api"

    know.mkdir(parents=True)
    dec.mkdir(parents=True)
    src_auth.mkdir(parents=True)
    src_api.mkdir(parents=True)

    (src_auth / "tokens.py").write_text("# token logic\n", encoding="utf-8")
    (src_api / "routes.py").write_text("# routes\n", encoding="utf-8")
    (src_api / "health.py").write_text("# health\n", encoding="utf-8")
    (proj / "README.md").write_text("# Readme\n", encoding="utf-8")

    (kb / "ki_config.json").write_text(
        json.dumps({"project_name": "CtxProj", "knowledge_root": ".ki-base", "language": "python"}),
        encoding="utf-8",
    )

    # KI 1: Active KI with Invariants, Non-obvious Details, Common Pitfalls
    (know / "KI_auth.md").write_text(
        "<!-- last_verified: 2026-11-01 -->\n"
        "# KI: Auth\n\n"
        "## Overview\nAuthentication subsystem overview.\n\n"
        "## Invariants\n- [MUST] Always rotate signing keys via KeyStore.\n\n"
        "## Non-obvious Details\n- Tokens are cached in memory for 30s.\n\n"
        "## Common Pitfalls\n- **Clock skew**: Allow +/-60s leeway on exp checks.\n",
        encoding="utf-8",
    )

    # KI 2: Stale KI matched by glob, with only Overview populated (fallback test)
    (know / "KI_api.md").write_text(
        "<!-- last_verified: 2025-01-01 -->\n"
        "<!-- status: stale -->\n"
        "# KI: API\n\n"
        "## Overview\nHTTP API endpoints validate payloads with Pydantic v2.\n\n"
        "## Non-obvious Details\n- <Implementation constraint, side effect, initialization order, or environment variable>\n",
        encoding="utf-8",
    )

    # KI 3: PoC KI matched by directory
    (know / "KI_poc_cache.md").write_text(
        "<!-- last_verified: 2026-11-10 -->\n"
        "<!-- status: poc -->\n"
        "# KI: PoC Cache\n\n"
        "## Overview\nExperimental Redis cache.\n\n"
        "## Non-obvious Details\n- Uses local fallback when REDIS_URL is unset.\n",
        encoding="utf-8",
    )

    # KI 4: Archived KI (must be excluded)
    (know / "KI_legacy_auth.md").write_text(
        "<!-- last_verified: 2024-01-01 -->\n"
        "<!-- status: archived -->\n"
        "# KI: Legacy Auth\n\n"
        "## Overview\nDeprecated auth flow.\n",
        encoding="utf-8",
    )

    # ADR 001: Superseded (must NEVER appear)
    (dec / "001_old_jwt.md").write_text(
        "<!-- created: 2025-01-01 -->\n"
        "<!-- status: Superseded -->\n"
        "<!-- superseded_by: 002 -->\n"
        "# ADR 001: Old JWT\n\n"
        "## Invariants & Rules for AI\n- [MUST NOT] Never use this old HS256 secret rule.\n\n"
        "## Scope & Affected Files\n- `src/auth/tokens.py` (Related KI: `KI_auth.md`)\n",
        encoding="utf-8",
    )

    # ADR 002: Accepted (must appear via Scope/Related KI)
    (dec / "002_eddsa_jwt.md").write_text(
        "<!-- created: 2026-10-01 -->\n"
        "<!-- status: Accepted -->\n"
        "# ADR 002: Use EdDSA JWT\n\n"
        "## Decisions Made\nSigned all JWT tokens with EdDSA.\n\n"
        "## Invariants & Rules for AI\n- [MUST] Reject alg=none and HS256 tokens immediately.\n\n"
        "## Scope & Affected Files\n- `src/auth/tokens.py` (Related KI: `KI_auth.md`)\n",
        encoding="utf-8",
    )

    # ADR 003: Accepted without Invariants section (fallback to Decisions Made)
    (dec / "003_api_errors.md").write_text(
        "<!-- created: 2026-10-05 -->\n"
        "<!-- status: Accepted -->\n"
        "# ADR 003: Unified API Errors\n\n"
        "## Decisions Made\nReturn RFC 7807 problem+json responses on 4xx/5xx.\n\n"
        "## Scope & Affected Files\n- `src/api/`\n",
        encoding="utf-8",
    )

    # ADR 004: PoC ADR (controlled by include_poc)
    (dec / "004_experimental_rate_limit.md").write_text(
        "<!-- created: 2026-11-02 -->\n"
        "<!-- status: poc -->\n"
        "# ADR 004: Token Bucket Rate Limiter\n\n"
        "## Invariants & Rules for AI\n- [MUST] Bypass rate limit for /health checks.\n\n"
        "## Scope & Affected Files\n- `src/api/*.py`\n",
        encoding="utf-8",
    )

    # ADR 005: Draft ADR (must NEVER appear)
    (dec / "005_draft_oauth.md").write_text(
        "<!-- created: 2026-11-12 -->\n"
        "<!-- status: draft -->\n"
        "# ADR 005: Draft OAuth\n\n"
        "## Invariants & Rules for AI\n- Draft only rule.\n\n"
        "## Scope & Affected Files\n- `src/auth/tokens.py`\n",
        encoding="utf-8",
    )

    doc_config = {
        "knowledge_items": {
            "KI_auth.md": {
                "summary": "Auth summary",
                "depends_on": ["src/auth/tokens.py"],
                "status": "active",
            },
            "KI_api.md": {
                "summary": "API summary",
                "depends_on": ["src/api/*.py"],
                "status": "stale",
            },
            "KI_poc_cache.md": {
                "summary": "PoC cache summary",
                "depends_on": ["src/auth"],
                "status": "poc",
            },
            "KI_legacy_auth.md": {
                "summary": "Legacy auth",
                "depends_on": ["src/auth/tokens.py"],
                "status": "archived",
            },
        }
    }
    (kb / "doc_config.json").write_text(json.dumps(doc_config, indent=2), encoding="utf-8")
    return proj


def test_context_for_file_extracts_priority_rules_and_filters_statuses(tmp_path):
    proj = _setup_workspace(tmp_path)
    res = ki_context.get_context_for(files=["src/auth/tokens.py"], project_root=str(proj))
    text = res["text"]

    # Active KI sections included
    assert "KI_auth.md" in text
    assert "Always rotate signing keys via KeyStore." in text
    assert "Tokens are cached in memory for 30s." in text
    assert "Allow +/-60s leeway" in text

    # PoC KI included with [POC] badge when include_poc=True
    assert "KI_poc_cache.md" in text
    assert "[POC]" in text

    # Accepted ADR included, Superseded/Draft/Archived excluded
    assert "ADR 002" in text
    assert "Reject alg=none and HS256 tokens immediately." in text
    assert "ADR 001" not in text
    assert "HS256 secret rule" not in text
    assert "ADR 005" not in text
    assert "Draft only rule" not in text
    assert "KI_legacy_auth.md" not in text


def test_context_for_glob_stale_warning_and_decisions_fallback(tmp_path):
    proj = _setup_workspace(tmp_path)
    res = ki_context.get_context_for(files=["src/api/routes.py"], project_root=str(proj))
    text = res["text"]

    # Matched via glob src/api/*.py, flagged [STALE], falls back to Overview (ignores placeholder)
    assert "KI_api.md" in text
    assert "[STALE]" in text
    assert "Pydantic v2" in text
    assert "<Implementation constraint" not in text

    # ADR 003 matched via directory scope, falls back to Decisions Made
    assert "ADR 003" in text
    assert "RFC 7807" in text

    # ADR 004 PoC matched via glob in Scope
    assert "ADR 004" in text
    assert "Bypass rate limit" in text


def test_context_for_include_poc_false(tmp_path):
    proj = _setup_workspace(tmp_path)
    res = ki_context.get_context_for(
        files=["src/auth/tokens.py", "src/api/routes.py"],
        include_poc=False,
        project_root=str(proj),
    )
    text = res["text"]

    assert "ADR 002" in text
    assert "KI_auth.md" in text
    assert "ADR 004" not in text
    assert "KI_poc_cache.md" not in text


def test_context_for_directory_target_and_windows_paths(tmp_path):
    proj = _setup_workspace(tmp_path)
    abs_path = str(proj / "src" / "auth" / "tokens.py")
    res = ki_context.get_context_for(files=[abs_path], project_root=str(proj))
    assert "KI_auth.md" in res["text"]

    res_dir = ki_context.get_context_for(files=["src/api/"], project_root=str(proj))
    assert "KI_api.md" in res_dir["text"]
    assert "ADR 003" in res_dir["text"]


def test_context_for_max_chars_budget_enforced(tmp_path):
    proj = _setup_workspace(tmp_path)
    # Add a verbose section to KI_auth.md
    ki_auth = proj / ".ki-base" / "knowledge" / "KI_auth.md"
    ki_auth.write_text(
        ki_auth.read_text(encoding="utf-8")
        + "\n"
        + "\n".join(f"- Detailed invariant line number {i} with extra padding text." for i in range(60)),
        encoding="utf-8",
    )

    res = ki_context.get_context_for(
        files=["src/auth/tokens.py", "src/api/routes.py"],
        max_chars=700,
        project_root=str(proj),
    )
    assert len(res["text"]) <= 700
    assert res["truncated"] is True
    # Summary header still mentions affected docs
    assert "ADR 002" in res["text"]


def test_context_for_unmatched_file_and_empty_input(tmp_path):
    proj = _setup_workspace(tmp_path)
    res = ki_context.get_context_for(files=["untracked/script.py"], project_root=str(proj))
    assert "No active KI or ADR rules matched" in res["text"]

    empty_res = ki_context.get_context_for(files=[], project_root=str(proj))
    assert "Error" in empty_res["text"]
