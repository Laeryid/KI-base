# KI_base — Knowledge Infrastructure for AI-Assisted Projects

> A portable, drop-in knowledge management system.  
> Copy the contents of this repo into your project's `.know/` folder (or any name you prefer) and run the init script.

---

## What is KI_base?

**KI_base** is a lightweight infrastructure layer that turns your project into a **self-documenting codebase** for AI agents (Claude, Windsurf, Cursor, etc.).

It provides:
- **Knowledge Items (KI)** — structured Markdown snapshots of each module's purpose, key components, and pitfalls, stored in `knowledge/`
- **Architectural Decision Records (ADR)** — an immutable log of key design decisions in `decisions/`
- **Coverage Audit** — a script that measures how well your KI base covers your actual code
- **MCP Server** — an isolated JSON-RPC interface that lets AI agents read/write KI safely, without accessing the rest of your project
- **Workflows** — step-by-step guides that agents follow to keep everything in sync

---

## Repository Structure

```
KI_base/  ←  copy this INTO your .know/ folder
├── README.md               ← this file (replace with your project README after copying)
├── doc_config.json         ← manifest: tracked modules + KI registry
├── knowledge/
│   └── KI_template.md      ← blank KI template to copy when creating new KIs
├── decisions/
│   └── 000_adr_template.md ← blank ADR template
├── workflows/
│   ├── sync-knowledge.md   ← /sync-knowledge workflow
│   ├── expand-knowledge.md ← /expand-knowledge workflow
│   └── create-adr.md       ← /create-adr workflow
├── scripts/
│   ├── init_ki_system.py   ← run once after copying to initialize
│   ├── ki_utils.py         ← shared config loader (used by all scripts)
│   ├── knowledge_engine.py ← file hashing & change detection core
│   ├── knowledge_mcp.py    ← MCP JSON-RPC server
│   ├── audit_coverage.py   ← coverage matrix generator
│   ├── generate_dir_index.py ← DIR_INDEX.md builder
│   ├── sync_agents_md.py   ← AGENTS.md synchronizer
│   └── add_ki_to_config.py ← CLI helper to register new KIs
└── tests/
    ├── conftest.py
    ├── test_knowledge_engine.py
    ├── test_ki_utils.py
    ├── test_mcp_security.py
    ├── test_audit_coverage.py
    ├── test_generate_dir_index.py
    └── test_sync_and_add_ki.py
```

---

## Quickstart

### 1. Copy into your project

```powershell
# Windows — copy all contents of KI_base into your project's .know folder
Copy-Item -Recurse "path\to\KI_base\*" "your-project\.know\"

# Linux / macOS
cp -r path/to/KI_base/* your-project/.know/
```

### 2. Initialize

```powershell
# Windows
.venv\Scripts\python.exe .know\scripts\init_ki_system.py

# Linux / macOS
.venv/bin/python .know/scripts/init_ki_system.py
```

Options:
```
--root     .know              # name of the knowledge folder (default: .know)
--agents   AGENTS.md          # path to AI agent instructions file
--workflows .agent/workflows  # where to look for/copy workflow files
```

The script will:
- Detect your virtual environment automatically
- Write `.know/ki_config.json` with resolved paths
- Add required sections to `AGENTS.md` (or your custom instructions file)
- Add selective `.gitignore` rules (keeps KI data, ignores service files)
- **Automatically setup Hard Links** for workflow files in `.agent/workflows/` (with collision handling and automatic suffixes)

### 3. Pre-configuration (Optional)

If you need specific paths (e.g., using `CLAUDE.md` instead of `AGENTS.md`), you can create `.know/ki_config.json` **before** running the init script:

```json
{
    "paths": {
        "knowledge_root": ".know",
        "project_root": "..",
        "agent_instructions": "CLAUDE.md",
        "workflows_dir": ".agent/workflows",
        "venv_python": ".venv/Scripts/python.exe"
    },
    "auto_resolve": true
}
```

### 4. Connect the MCP Server
 
Add to your IDE's MCP config (e.g., `mcp_config.json`):
```json
{
  "mcpServers": {
    "KnowledgeManager": {
      "command": ".venv/Scripts/python.exe",
      "args": [".know/scripts/knowledge_mcp.py", "--config", ".know/ki_config.json"]
    }
  }
}
```
 
> [!IMPORTANT]
> **Restart your IDE** after this step to enable the MCP server and refresh the hard-linked workflows.
 
### 5. Start using Workflows
 
Workflows are now linked to your IDE's workflows directory (default: `.agent/workflows/`).
 
**To begin your work, use the command:**  
`/expand-knowledge` (from `.agent/workflows/expand-knowledge.md`)  
This will run a coverage audit and help you identify the first module to document.

---

## Workflows (slash commands)

| Command | What it does |
|---|---|
| `/sync-knowledge` | Detect changed files → update KIs → regenerate DIR_INDEX → sync AGENTS.md → save state |
| `/expand-knowledge` | Run coverage audit → pick the worst gap → write or improve a KI |
| `/create-adr` | Discover recent decisions from git log → write a new ADR |

---

## What Gets Committed to Git?

| Path | Git | Notes |
|---|:---:|---|
| `knowledge/*.md` | ✅ | Your intellectual data |
| `decisions/*.md` | ✅ | Architecture history |
| `doc_config.json` | ✅ | Module manifest |
| `scripts/*.py` | ❌ | Service scripts (restored from repo) |
| `workflows/*.md" | ❌ | Workflow guides (restored from repo) |
| `tests/` | ❌ | Service tests |
| `README.md` | ❌ | Service description |
| `ki_config.json` | ❌ | Local paths (machine-specific) |
| `doc_state.json` | ❌ | File hashes (regenerated) |
| `coverage_matrix.md` | ❌ | Auto-generated report |
| `__pycache__/` | ❌ | Python cache |

*(`.gitignore` rules are added automatically by `init_ki_system.py`)*

---

## Running Tests

```powershell
.venv\Scripts\python.exe -m pytest .know\tests\ -v
```

---

## Security

The MCP server operates in a **sandbox (jail)**: all file access is restricted to the `.know/` folder. Attempts to escape via `../` paths or write to `.py` / `.ps1` / `.bat` files are blocked with `PermissionError`.

---

## License

MIT — free to use, copy, and adapt.
