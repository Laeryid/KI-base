# ki-manager — Knowledge Item MCP Server

> AI-powered knowledge management for software projects.  
> Install once, use across all your projects.

[![smithery badge](https://smithery.ai/badge/bulyakovbr/ki-manager)](https://smithery.ai/servers/bulyakovbr/ki-manager)

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
   > **Note for Windows / ADI Antigravity:** If `ki-manager` is not found in PATH by your IDE, specify the full path to the executable:
   > - **Windows:** `"C:\\Users\\<username>\\.local\\bin\\ki-manager.exe"`
   > - **Linux/macOS:** `"/home/<username>/.local/bin/ki-manager"`

### Option B: pip / uv pip

```bash
pip install ki-manager
# or
uv pip install ki-manager
```

### Option C: Smithery (Claude Desktop / Cursor / Windsurf GUI)

Search for **ki-manager** in your IDE's MCP marketplace and click Install.

### Option D: Local development

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

## Agent Skills

`ki-manager` distributes workflow instructions using the [Agent Skills](https://agentskills.io) standard format.

### Installing Skills

You can install the bundled workflow skills to your IDE's skills folder (e.g., for Google Antigravity):

```bash
# CD into your skills directory and run:
ki-manager-skills install-skills

# Or run via uvx specifying the target path explicitly:
uvx ki-manager-skills install-skills --path ~/.gemini/config/skills/
```

This will copy all workflow instructions (like `create-adr`, `expand-knowledge`) as standard `.md` skill files. It skips existing ones, so it's safe to run multiple times.

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

## License

MIT — free to use, copy, and adapt.
