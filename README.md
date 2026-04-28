# KI_base — Knowledge Infrastructure for AI-Assisted Projects


> A portable, drop-in knowledge management system.  
> Copy the contents of this repo into your project's `.know/` folder and run the init script.

---

## What is KI_base?

**KI_base** is a lightweight infrastructure layer that turns your project into a **self-documenting codebase** for AI agents (Claude, Windsurf, Cursor, etc.).

It provides:
- **Knowledge Items (KI)** — structured Markdown snapshots of each module's purpose, key components, and pitfalls, stored in `knowledge/`
- **Architectural Decision Records (ADR)** — an immutable log of key design decisions in `decisions/`
- **Coverage Audit** — a script that measures how well your KI base covers your actual code
- **MCP Server** — an isolated JSON-RPC interface that lets AI agents read/write KI safely, without accessing the rest of your project
- **Workflows** — step-by-step guides that agents follow to keep everything in sync
- **Git Snapshots** — versioning system for knowledge state (`git_checkpoint`, `git_restore`)

---

## Repository Structure

```
.know/                      ←  copy KI_base contents here
├── README.md               ← this file
├── doc_config.json         ← manifest: tracked modules + KI registry
├── knowledge/
│   └── KI_template.md      ← blank KI template
├── decisions/
│   └── 000_adr_template.md ← blank ADR template
├── workflows/
│   ├── sync-knowledge.md   ← /sync-knowledge workflow
│   ├── expand-knowledge.md ← /expand-knowledge workflow
│   └── create-adr.md       ← /create-adr workflow
├── scripts/
│   ├── init_ki_system.py   ← run once after copying to initialize
│   ├── ki_utils.py         ← shared utility module
│   ├── knowledge_engine.py ← file hashing core
│   ├── knowledge_mcp.py    ← MCP server
│   ├── audit_coverage.py   ← coverage generator
│   └── ...
└── tests/                  ← core infrastructure tests
```

---

## Quickstart

### 1. Copy into your project

```powershell
# Windows — copy all contents into your project's .know folder
Copy-Item -Recurse "path\to\KI_base\*" "your-project\.know\"
```

### 2. Initialize

```powershell
# Run the init script (automatically detects .venv)
.venv\Scripts\python.exe .know\scripts\init_ki_system.py
```

The script will:
- Detect your virtual environment automatically.
- Write `.know/ki_config.json` with resolved paths.
- Setup **Hard Links** for workflows in `.agent/workflows/`.
- Generate a selective **.gitignore** (keeps your data, ignores the engine).

### 3. Connect the MCP Server
 
Add to your IDE's MCP config:
```json
{
  "mcpServers": {
    "knowledge-manager": {
      "command": ".venv/Scripts/python.exe",
      "args": [".know/scripts/knowledge_mcp.py", "--config", ".know/ki_config.json"],
      "cwd": "."
    }
  }
}
```
 
### 4. Start using Workflows
 
Use slash commands from your IDE (currently supported in **Antigravity**):
- `/expand-knowledge` — identify and fill documentation gaps.
- `/sync-knowledge` — keep documentation in sync with code changes.
- `/create-adr` — record architectural decisions.

> [!NOTE]
> **Slash commands** are a feature of the Antigravity agent. In other IDEs (like Windsurf or Cursor), you should trigger these workflows by **dragging the workflow file** (e.g., `.know/workflows/sync-knowledge.md`) into the chat or mentioning it as a context file.

---

## What Gets Committed to Git?

The initialization script sets up `.know/.gitignore` to ensure your repository stays clean:

| Path | Git | Description |
|---|:---:|---|
| `knowledge/*.md` | ✅ | Project-specific knowledge |
| `decisions/*.md` | ✅ | Architecture history |
| `doc_config.json` | ✅ | Module manifest |
| `scripts/` | ❌ | Engine scripts (ignored) |
| `tests/` | ❌ | Engine tests (ignored) |
| `DIR_INDEX.md` | ❌ | **Auto-generated index (ignored)** |
| `ki_config.json` | ❌ | Local machine-specific paths |
| `doc_state.json` | ❌ | File hash cache |
| `README.md` | ❌ | Infrastructure description |

---

## Security

The MCP server operates in a **sandbox**:
- File access is restricted to the `.know/` folder.
- Executable files (`.py`, `.exe`, etc.) are protected from modification.
- Critical files like `doc_config.json` can only be modified via specific tools.

---

## License

MIT — free to use, copy, and adapt.
