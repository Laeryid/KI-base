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

### Option A: uvx (recommended — no install needed)

```json
{
  "mcpServers": {
    "ki-manager": {
      "command": "uvx",
      "args": ["ki-manager"]
    }
  }
}
```

> Requires [uv](https://docs.astral.sh/uv/) — install with: `curl -LsSf https://astral.sh/uv/install.sh | sh`

#### Eager vs Lazy Loading (Advanced)

Because `ki-manager` provides a large number of tools, AI IDEs may downgrade it to "lazy" loading to save context window. For maximum performance, you can split the server into two instances using the `--mode` flag. This allows lightweight tools (status, read_know_file) to load natively (`eager`), while heavy operations remain `lazy`:

```json
{
  "mcpServers": {
    "ki-manager-eager": {
      "command": "uvx",
      "args": ["ki-manager", "--mode", "eager"],
      "lifecycle": "eager"
    },
    "ki-manager-lazy": {
      "command": "uvx",
      "args": ["ki-manager", "--mode", "lazy"]
    }
  }
}
```

### Option B: Smithery (Claude Desktop / Cursor / Windsurf GUI)

Search for **ki-manager** in your IDE's MCP marketplace and click Install.

### Option C: pip

```bash
pip install ki-manager
ki-manager  # starts the MCP server
```

### Option D: Docker

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

### 3. Start documenting

Use the available tools or slash commands:

| Tool / Command | Action |
|----------------|--------|
| `audit_coverage` | Find documentation gaps |
| `generate_dir_index` | Build directory index |
| `sync_agents_md` | Sync KI table in AGENTS.md |
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
├── pyproject.toml            ← pip / uvx package config
├── smithery.yaml             ← Smithery MCP marketplace config
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
