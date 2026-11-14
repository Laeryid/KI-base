<p align="center">
  <img src="https://raw.githubusercontent.com/Laeryid/KI-base/main/ki_manager_logo.png" width="150" alt="ki-manager Logo">
</p>

# ki-manager — Knowledge Item MCP Server

> AI-powered knowledge management for software projects.  
> Install once, use across all your projects.


---

## What is ki-manager?

**ki-manager** is an MCP (Model Context Protocol) server that turns any project into a **self-documenting codebase** for AI agents (Claude, Antigravity, Cursor, Windsurf, etc.).

It provides:
- **Just-in-Time Context (`ki_context_for`)** — delivers concise active invariants, pitfalls, and ADR rules matched to the file(s) you are about to edit (within a strict token/character budget, with session deduplication)
- **Knowledge Items (KI)** & **ADRs** — structured Markdown snapshots and lifecycle-tracked decisions (`draft`, `poc`, `accepted`, `superseded`, `deprecated`, `archived`) in `.ki-base/`
- **Deterministic Linter & Single-Call Sync (`ki_lint`, `ki_sync`)** — validates structure, metadata, and `depends_on` references, then syncs `DIR_INDEX.md`, `doc_state.json`, and `AGENTS.md` cleanly
- **Coverage Audit & Dependency Analysis** — measures how well your KI base covers your actual code and auto-links related KIs
- **Optional Git & Declarative Agent Hooks** — zero-dependency Git `pre-commit` hook plus config-driven harness manifests (`antigravity`/`agy`/`vaib`, `claude`, or custom user JSON)
- **Scaffolding** — one command creates the complete `.ki-base/` structure in any project

---

## Installation

### Option A: uv tool install (recommended)

1. Install `ki-manager` globally via [uv](https://docs.astral.sh/uv/):
   ```bash
   uv tool install ki-manager
   ```

2. Add to your IDE MCP configuration (`mcp_config.json`):
   ```json
   {
     "mcpServers": {
       "ki-manager": {
         "command": "ki-manager",
         "args": ["--tool-mode", "compact"],
         "directTools": true,
         "lifecycle": "eager"
       }
     }
   }
   ```
   > **Note for Windows / ADI Antigravity:** If `ki-manager` is not found in PATH by your IDE, specify the full path to the executable:
   > - **Windows:** `"C:\\Users\\<username>\\.local\\bin\\ki-manager.exe"`
   > - **Linux/macOS:** `"/home/<username>/.local/bin/ki-manager"`

### Option B: pip / uv pip

```bash
pip install ki-manager
# or
uv pip install ki-manager
```

### Option С: Local development

If you cloned the repository and are developing locally, point your IDE to the `.venv` Python directly:

```json
{
  "mcpServers": {
    "ki-manager": {
      "command": "/absolute/path/to/repo/.venv/bin/python",
      "args": ["-m", "ki_manager.server"]
    }
  }
}
```

On Windows:
```json
{
  "mcpServers": {
    "ki-manager": {
      "command": "C:\\path\\to\\repo\\.venv\\Scripts\\python.exe",
      "args": ["-m", "ki_manager.server"]
    }
  }
}
```

### Compact Mode (Token Saver)

By default, `ki-manager` runs in `full` mode and exposes all 40 tools directly. For AI clients that inject tool definitions into the context window, you can enable compact facade mode to expose only 8 essential tools (`ki_instructions`, `ki_list`, `ki_search`, `ki_read`, `ki_context_for`, `ki_tools`, `ki_call`, `ki_mutate`):

```json
{
  "mcpServers": {
    "ki-manager": {
      "command": "ki-manager",
      "args": ["--tool-mode", "compact"]
    }
  }
}
```

Alternatively, set the environment variable `KI_TOOL_MODE=compact`.

---

## Quickstart

### 1. Add the MCP server to your IDE

Pick one of the options above and add it to your MCP config.

### 2. Initialize a project

In your IDE chat, call the `ki_init_project` tool:

```
ki_init_project(project_path="/absolute/path/to/your-project")
```

This creates:

```
your-project/
└── .ki-base/
    ├── config.json          ← machine-specific (auto-added to .gitignore)
    ├── ki_config.json       ← project settings (commit to git)
    ├── doc_config.json      ← file→KI map (commit to git)
    ├── AGENTS.md            ← agent instructions (commit to git)
    ├── DIR_INDEX.md         ← directory index (commit to git)
    └── knowledge/
        └── _OVERVIEW.ki.md  ← starter Knowledge Item
```

### 3. Daily workflow & documenting

| Tool / Command | Action |
|----------------|--------|
| `ki_context_for` | **Before editing code:** get concise active KI invariants and ADR rules for target files |
| `ki_list` | List active Knowledge Items and ADRs (`status`: `active` \| `all` \| specific) |
| `ki_search` | BM25 search across active documentation (`include_inactive=true` for archived/superseded) |
| `ki_read` | Read a KI or ADR (supports `section` and `max_chars`) |
| `ki_lint` | Deterministic validation of structure, statuses, `superseded_by`, and `depends_on` |
| `ki_sync` | Single-call sync: `ki_lint` → diff → `check_ki_drift` → targeted `update_last_verified` → `DIR_INDEX` → `save_state` → `AGENTS.md` |
| `audit_coverage` | Find documentation gaps |
| `generate_dir_index` | Rebuild directory index (`DIR_INDEX.md`) |
| `find_unmapped_files` | List source files not covered by any KI |
| `ki_scaffold` | Create stub KI files for uncovered modules |
| `ki_scaffold_status` | Show pending vs enriched scaffold KIs |
| `ki_finalize_scaffolds` | Strip scaffold markers, update `doc_config.json` summaries |
| `add_ki_to_config` | Register or update Knowledge Item in `doc_config.json` |
| `edit_doc_config` | Safely modify `doc_config.json` (`tracked_modules`, `artifacts`, `coverage_settings`, `ignore_dirs`) |
| `sync_agents_md` | Sync active Knowledge Items and ADR tables in `AGENTS.md` |
| `create_adr` | Create structured ADR with sequential ID, template, bidirectional `supersedes`, and registration |
| `analyze_all_dependencies` | Update "Related KIs" links across all KIs |
| `git_checkpoint` | Check pending KB changes (commits when `commit=true` or `auto_git_checkpoint: true` in `ki_config.json`) |
| `/scaffold-knowledge` | Bootstrap KI stubs → AI enrichment → finalize |
| `/expand-knowledge` | Iteratively add KIs for undocumented modules |
| `/sync-knowledge` | Synchronize KI system (`ki_sync`) |
| `/create-adr` | Record an architectural decision |

---

## Agent Skills

`ki-manager` distributes workflow instructions using the [Agent Skills](https://agentskills.io) standard format.

### Installing Skills

You can install the bundled workflow skills to your IDE's skills folder (e.g., for Google Antigravity):

```bash
# CD into your skills directory and run:
ki-manager install-skills
# (or: ki-manager-skills install-skills)

# Or specify the target path explicitly:
ki-manager install-skills --path ~/.gemini/config/skills/
```

This copies all workflow instructions (`create-adr`, `expand-knowledge`, `scaffold-knowledge`, `sync-knowledge`, `agent-rules`) as standard `SKILL.md` files and skips existing ones.

---

## Optional CLI Linter & Hooks (Any IDE or Harness)

Core features (`ki_context_for`, `ki_lint`, `ki_sync`) work out of the box via MCP in any IDE with **zero hook dependency**. Optionally, you can enforce checks automatically via Git or declarative agent hooks:

### 1. Git `pre-commit` Hook (Universal)

Run fast staged validation (`ki-manager lint --staged`) on every commit modifying knowledge files:

```bash
ki-manager install-hooks
# Manual lint commands:
ki-manager lint
ki-manager lint --staged
ki-manager lint --fix
```

### 2. Declarative Agent Harness Hooks (`--harness`)

`ki-manager` uses standalone JSON manifests to integrate with AI agent lifecycle hooks (`pre-edit`, `stop-lint`) without hardcoding IDE specifics:

```bash
# List discovered manifests and aliases:
ki-manager install-hooks --list-harnesses

# Install Antigravity (.agents/hooks.json) using any alias: agy, antigravity, vaib
ki-manager install-hooks --harness agy

# Install Claude Code (.claude/settings.json) using: claude, claude-code
ki-manager install-hooks --harness claude

# Or install any custom harness manifest:
ki-manager install-hooks --harness path/to/my_agent.json
```

Custom manifests can be placed in `.ki-base/harnesses/<name>.json` (project-local) or `~/.ki_base/harnesses/<name>.json` (user-global).

- **Unified MCP + Hook Cache**: Calling MCP `ki_context_for(files=[...])` caches delivered rule hashes in `~/.ki_base/cache/` (TTL configurable via `context_cache_ttl` in `ki_config.json` or `KI_CONTEXT_CACHE_TTL`). If an agent already fetched context before editing, the `pre-edit` hook allows the first edit without blocking; if not, the first edit receives active invariants once and subsequent retries pass cleanly.

---

## What Goes Into Git?

| Path | Git | Notes |
|------|:---:|-------|
| `.ki-base/knowledge/*.ki.md` | ✅ | Project knowledge |
| `.ki-base/decisions/*.md` | ✅ | Architecture Decision Records |
| `.ki-base/doc_config.json` | ✅ | Module manifest |
| `.ki-base/ki_config.json` | ✅ | Project settings (`auto_git_checkpoint`, `context_cache_ttl`, etc.) |
| `.ki-base/AGENTS.md` | ✅ | Agent instructions (active KIs & ADRs) |
| `.ki-base/DIR_INDEX.md` | ✅ | Directory index |
| `.ki-base/harnesses/*.json` | ✅ | Optional custom harness hook manifests |
| `.ki-base/config.json` | ❌ | Machine-specific paths |
| `.ki-base/doc_state.json` | ❌ | Hash cache |

---

## Security

The MCP server operates in a **sandbox**:
- MCP file write tools are restricted to the `.ki-base/` directory; native `read_file`/`edit_file` may edit `.md` files in `knowledge/` and `decisions/` cleanly (validated by `ki_lint` / `ki_sync`)
- Executable files (`.py`, `.exe`, `.sh`, etc.) cannot be modified via MCP
- Critical config files (`doc_config.json`, `ki_config.json`, `config.json`, `doc_state.json`) are protected from raw overwrite via MCP file tools

---

## Project Structure (this repo)

```
ki-manager/
├── pyproject.toml            ← pip / uv package config
├── src/ki_manager/
│   ├── server.py             ← MCP server entry point
│   ├── tools/
│   │   └── scaffold.py       ← ki_init_project implementation
│   └── scripts/              ← bundled analysis scripts
│       ├── ki_utils.py       ← shared utilities
│       ├── audit_coverage.py
│       ├── sync_agents_md.py
│       ├── generate_dir_index.py
│       ├── ki_dependency_analyzer.py
│       └── ...
├── knowledge/                ← KI documentation of this repo itself
└── decisions/                ← Architecture Decision Records
```

---

## Troubleshooting

### MCP server hangs on initialization (never connects)

Using `uvx` directly in `mcpServers` configuration is known to cause hangs or stdio pipe drops in **ADI Antigravity** and Windows environments due to ephemeral environment creation delays and process wrapping.

**Solution:** Install via `uv tool install ki-manager` and specify `ki-manager` or its absolute executable path in `mcpServers`.

**Step 1 — Check logs:**  
Server logs are written to `~/.ki_base/logs/`. Open the latest file and look for `REQ:` lines. If there are no `REQ:` lines at all, stdin is not being piped correctly by the IDE.

**Step 2 — Specify exact executable path:**  
If your IDE cannot find `ki-manager` in system PATH:
```json
{
  "mcpServers": {
    "ki-manager": {
      "command": "C:\\Users\\<username>\\.local\\bin\\ki-manager.exe"
    }
  }
}
```

**Step 3 — Reinstall / Upgrade tool:**  
To upgrade to the latest PyPI version when using `uv tool`:
```bash
uv tool install --reinstall ki-manager
```

### Server is running but no tools appear

Check that `ki_status` is visible in the IDE. If it shows `No project active for current workspace`, the server is working correctly — it just needs a project to be initialized (`ki_init_project`) or the IDE is not passing `rootUri` in the MCP handshake.

### `[Errno 22] Invalid argument` in logs

This error was present in versions `< 2.0.11` on Windows when wrapping `sys.stdout` with a `codecs` encoder. **Upgrade to `>= 2.0.11`** to fix it:
```bash
uv tool install --reinstall ki-manager
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release notes and detailed history of changes.

---

## License

MIT — free to use, copy, and adapt.
