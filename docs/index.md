# ki-manager — Knowledge Item MCP Server

> AI-powered knowledge management for software projects.  
> Install once, use across all your projects.

---

## What is ki-manager?

**ki-manager** is an MCP (Model Context Protocol) server that turns any project into a **self-documenting codebase** for AI agents (Claude, Antigravity, Cursor, Windsurf, etc.).

It provides:
- **Knowledge Items (KI)** — structured Markdown snapshots of each module, stored in `.ki-base/knowledge/`
- **Coverage Audit** — measures how well your KI base covers your actual code
- **Dependency Analysis** — auto-updates "Related KIs" by analyzing imports
- **Git Snapshots** — versioned knowledge state (`git_checkpoint`, `git_restore`)
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
         "command": "ki-manager"
       }
     }
   }
   ```

### Option B: pip / uv pip

```bash
pip install ki-manager
# or
uv pip install ki-manager
```

### Option C: Docker

```bash
docker run -i --rm -v "$(pwd):/workspace" ghcr.io/laeryid/ki-manager
```

---

## Quickstart

### 1. Add the MCP server to your IDE

Pick one of the options above and add it to your MCP config.

### 2. Initialize a project

In your IDE chat, call the `ki_init_project` tool:

```
ki_init_project(project_path="/absolute/path/to/your-project")
```

Custom folder name or root-level configuration can be specified as well:
```
ki_init_project(
  project_path="/absolute/path/to/your-project",
  knowledge_root="docs",          # custom knowledge directory (default: .ki-base)
  config_location="root"          # put ki_config.json in project root or knowledge_dir
)
```

By default, this creates:

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

---

## Flexible Configuration & Custom Knowledge Roots

`ki-manager` automatically locates project configurations without hardcoded path restrictions.

### Config Resolution Order
When searching for project configuration, the server checks:
1. **Explicit CLI argument**: `--config <path>` or `--workspace <path>`
2. **Global registry**: Project entry in `~/.ki_base/registry.json`
3. **Upward filesystem search** in order:
   - `<parent>/.ki-base/ki_config.json`
   - `<parent>/ki_config.json` (project root)
   - `<parent>/.config/ki_config.json`
   - `<parent>/config/ki_config.json`
   - `<parent>/.know/ki_config.json` (legacy fallback)

### Custom Knowledge Root (`paths.knowledge_root`)
To name your knowledge folder something other than `.ki-base` (e.g. `docs` or `kb`), specify it in `ki_config.json`:
```json
{
  "paths": {
    "knowledge_root": "docs"
  }
}
```
All MCP tools, audits, and index generators will dynamically operate inside the configured directory.

### Fileless Project Registration
To link an external repository without committing configuration files to it, register it directly in the global registry using `ki_register_project`:
```
ki_register_project(
  workspace="/path/to/repo",
  inline_config={
    "paths": {"knowledge_root": "docs"},
    "project_name": "MyExternalProject"
  }
)
```

---

## Tool Modes: Full vs. Compact Facade

`ki-manager` supports two exposure modes for MCP tools:
- **Full mode (`--tool-mode full`, default)**: Exposes all 33 granular tools.
- **Compact mode (`--tool-mode compact` or `KI_TOOL_MODE=compact`)**: Exposes only **6 facade tools**, saving thousands of context tokens while keeping full functionality:
  1. `ki_instructions` — workflow guidelines and AI rules.
  2. `ki_search` — BM25 search across Knowledge Items & ADRs with concise Markdown output and pagination (`offset`).
  3. `ki_read` — fast reading of KIs/ADRs with section filtering (`section`), character truncation (`max_chars`), and offset (`offset`).
  4. `ki_tools` — inspect catalog and schemas of specific tools.
  5. `ki_call` — execute read-only tools.
  6. `ki_mutate` — execute state-modifying tools.

---

### 3. Start documenting

Use the available tools or slash commands:

| Tool / Command | Action |
|----------------|--------|
| `ki_search` | BM25 search across KIs and ADRs with concise Markdown results and pagination (`offset`, `limit`) |
| `ki_read` | Read KIs or ADRs with section filtering (`section`), length limit (`max_chars`), and offset (`offset`) |
| `ki_instructions` | Access bundled workflow guides and agent navigation rules |
| `ki_tools` | Inspect tool schemas and catalog (compact facade mode) |
| `ki_call` / `ki_mutate` | Dispatch read-only or mutating operations through compact facade |
| `ki_register_project` | Register project in global registry (supports `config_path` or `workspace` + `inline_config`) |
| `ki_list_projects` | List all registered projects |
| `ki_status` | Check active workspace and resolved paths |
| `audit_coverage` | Find documentation gaps |
| `generate_dir_index` | Build directory index |
| `add_ki_to_config` | Register or update Knowledge Items in `doc_config.json` |
| `edit_doc_config` | Safely modify `doc_config.json` (`tracked_modules`, `artifacts`, `coverage_settings`) |
| `sync_agents_md` | Sync Knowledge Items and ADR tables in `AGENTS.md` (configurable via `sync_agents_md: false` in `ki_config.json`) |
| `create_adr` | Create structured ADR with sequential ID, template, and registration |
| `git_checkpoint` | Save knowledge snapshot to git |
| `/expand-knowledge` | Iteratively fill gaps (Antigravity) |
| `/sync-knowledge` | Full sync workflow (Antigravity) |
| `/create-adr` | Record architectural decision |

---

## What Goes Into Git?

| Path | Git | Notes |
|------|:---:|-------|
| `.ki-base/knowledge/*.ki.md` | ✅ | Project knowledge |
| `.ki-base/doc_config.json` | ✅ | Module manifest |
| `.ki-base/ki_config.json` | ✅ | Project settings |
| `.ki-base/AGENTS.md` | ✅ | Agent instructions |
| `.ki-base/DIR_INDEX.md` | ✅ | Directory index |
| `.ki-base/config.json` | ❌ | Machine-specific paths |
| `.ki-base/doc_state.json` | ❌ | Hash cache |

---

## Security

The MCP server operates in a **sandbox**:
- All file access is restricted to the `.ki-base/` directory
- Executable files (`.py`, `.exe`, `.sh`, etc.) cannot be modified via MCP
- Critical config files are protected from direct overwrite

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

## License

MIT — free to use, copy, and adapt.
