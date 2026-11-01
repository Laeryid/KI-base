# Changelog

All notable changes to the `ki-manager` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- Note: This changelog is intended for end-users and AI agents. It must always be maintained in English and focus on user-facing features, behavior changes, and bug fixes rather than internal implementation details. -->

## [Unreleased]

## [2.3.2.dev2] — 2026-11-01

### Added
- **`ki_list` Navigation Tool**:
  - Direct navigation tool to list registered Knowledge Items and Architecture Decision Records (ADRs) with summaries and covered modules without filesystem scans.
  - Supports filtering by type (`scope: "all" | "ki" | "adr"`), output formats (`format: "markdown" | "json"`), and search query (`filter: "<text>"`).
  - Available as a direct top-level tool in both full mode (35 tools) and compact facade mode (7 tools).
- **BM25 Search Pagination (`ki_search`)**:
  - Added 1-based `page` parameter for intuitive result pagination alongside `offset`.
  - Prominent pagination header and next-page action hints (`[Page X/Y]`, `Next page: ki_search(query="...", page=X+1)`) in search outputs to prevent AI models from getting stuck in repeat queries.

## [2.3.2.dev1] — 2026-10-20

### Fixed
- **`find_unmapped_files` Traversal & Scoping**:
  - Automatically loads and enforces `.gitignore` patterns and `doc_config.json` `exclude` rules (in addition to `exclude_patterns`) during repository discovery.
  - When scanning repository root by default, scopes file discovery to root segments of configured `tracked_modules`, avoiding timeouts and runaway directory walks across large external data trees.
  - Made the CLI `path` argument optional, defaulting to root / tracked modules.
- **`check_ki_drift` Markdown Table Header Validation**:
  - Validates Markdown table headers explicitly for file path columns (`File`, `Path`, `Source`, `Location`) before inspecting cells for broken paths.
  - Tables without file columns (e.g. `| Tool | Access | Purpose |`) are cleanly bypassed, eliminating false-positive `Missing file: Access` errors.

## [2.3.1] — 2026-10-18

### Security & Hardening
- **Path Traversal Protection**: Enforced strict directory boundary containment across all file discovery and inspection tools (`find_unmapped_files`, `analyze_module`, `ki_search`, and custom agent paths) to prevent prefix-based sandbox traversal attacks.
- **Secured Git Operations (`git_diff_secured`)**: Added hardened diff inspection tool protecting against flag injection (`--output`, etc.), shell command chaining, and repository boundary escapes.
- **Restricted File Modifications**: Extended write protection to block direct modifications of shell/executable scripts (`.sh`, `.bash`, `.zsh`, `.js`, `.ts`, `.vbs`, `.wsf`) and internal system state files (`doc_config.json`, `ki_config.json`, `config.json`, `doc_state.json`) via direct file editing tools.

### Changed
- **Unified Tool Dispatch Schema**: In compact facade mode, dynamically bind `ki_call` and `ki_mutate` tool validation schemas (`enum` and `description`) directly to tool `readOnlyHint` annotations, eliminating dispatch conflicts and preventing model confusion.
- **Date Format Resilience in `update_last_verified`**: Extended `update_last_verified` to automatically detect and update all supported date notation variants (HTML comment `<!-- last_verified: YYYY-MM-DD -->`, YAML frontmatter `last_verified: "YYYY-MM-DD"`, and Markdown bold `**Last verified**: YYYY-MM-DD`), and automatically insert the verification tag if missing.
- **Workflow Instructions Alignment**: Synchronized tool arguments and signatures across `/expand-knowledge` and `/sync-knowledge` instructions, ensuring seamless execution in both compact facade and full tool modes.
- **Daily MCP Log Rotation**: Server diagnostics now rotate daily (`mcp_YYYY-MM-DD.log`) with payload truncation to prevent runaway disk usage during high-frequency sessions.

## [2.3.0] — 2026-10-11

### Added
- **Unified Cascade Path Resolution (`resolve_know_path`)**: `read_know_file`, `write_know_file`, and `edit_know_file` now share `ki_read`'s smart cascade resolver. AI agents can access and edit Knowledge Items using flat basenames (e.g. `KI_data_persistence.md`) without requiring explicit `knowledge/` directory prefixes.
- **Smart Directory Placement for New KIs**: `write_know_file` now updates existing files in place across `knowledge/` rather than creating duplicates in the sandbox root, and automatically routes newly created flat KI files (`KI_*.md`, `*.ki.md`) into `<jail>/knowledge/`.
- **ADR Name & Prefix Tolerance**: `resolve_know_path` and `ki_read` gracefully handle variations with or without `ADR_`/`adr_`/`ADR-` prefixes (e.g., resolving `ADR_002_node_status_queue_and_ui_feedback.md` to `002_node_status_queue_and_ui_feedback.md`) as well as numeric ADR IDs.
- **Accurate Document Listings**: `get_ki_list_table()` dynamically reconciles registered entries in `doc_config.json` against filesystem reality, outputting exact on-disk filenames in document overviews.
- **Comprehensive Project Overview**: `ki_instructions(document="knowledge-items")`, prompts, and `ki://knowledge-items.md` now present both Knowledge Items and Architecture Decision Records (ADRs) tables together when ADRs exist.

### Highlights from 2.3.0 Development Cycle
- Compact Facade Mode (`--tool-mode compact`) reducing MCP tools footprint from 34 schemas to 6 tools (`ki_instructions`, `ki_search`, `ki_read`, `ki_tools`, `ki_call`, `ki_mutate`), saving thousands of context tokens.
- Native BM25 search engine (`ki_search`) with bilingual EN/RU stemming and field-weighted ranking.
- Token-efficient reader with section filtering and character offset pagination (`ki_read`, `read_know_file`).
- Batch ADR superseding (`create_adr`) with automatic status transitions, warning banners, git/environment snapshots, and quality sections (`rejected_alternatives`, `invariants`, `verification`).
- Automated drift analysis (`check_ki_drift`) and Python AST pre-enrichment during scaffolding.

### Added
- `create_adr` batch `supersedes` support: accept a list of previous ADR IDs (`supersedes: ["001", "002"]`) to supersede multiple older records simultaneously; automatically updates deprecated ADR files with warning banners and `Superseded by ADR XXX` statuses, updates `doc_config.json`, and embeds bi-directional cross-links in the generated ADR.
- Automated contextual provenance in `create_adr`: deterministically captures Git HEAD commit hash, current branch, and author, as well as an environment snapshot (operating system, Python runtime, and `ki-manager` version) without LLM overhead or prompt tokens.
- Automated Scope & Knowledge Graph linking in `create_adr`: automatically discovers modified project files from Git or accepts explicit `affected_files`, correlates them with Knowledge Items in `doc_config.json`, and records them in the ADR's `depends_on` dependencies list.
- Structured ADR quality sections: added support for `rejected_alternatives` (documenting abandoned paths and failed attempts to prevent regression loops), `invariants` (enforceable MUST / MUST NOT rules for future AI sessions), and `verification` (automated test commands or validation checklists).
- `check_ki_drift` MCP tool & CLI script: automated discrepancy detection between Knowledge Items and the codebase, flagging dead symbols, unmapped public symbols, missing `depends_on` files, broken `[[KI_*.md]]` wiki-links, and Git date discrepancies against `last_verified`.
- AST pre-enrichment in `generate_ki_scaffolds`: parses Python AST to pre-populate module docstrings into `## Overview`, class/function docstrings into the `Key Components` table, signatures, detected environment variables, and discovered test commands from `tests/`.
- Canonical KI template featuring `## Entry Points & Public API` and `## Testing & Verification` sections, along with an updated canonical ADR template.
- Integrated `check_ki_drift` into the `/sync-knowledge` workflow and the `coverage_analysis` tool group in facade mode.

### Changed
- Updated `/create-adr` workflow instructions and tool schemas with the new ADR parameters across both full and compact tool modes.
- Aligned KI structures across `scaffold-knowledge.md`, `expand-knowledge.md`, `sync-knowledge.md`, and scaffold generators to the canonical template.
- Made `finalize_ki_scaffolds` summary extraction resilient and backwards-compatible with legacy `## Purpose` and `## What it Does` headers.
- Cleaned up duplicate local `knowledge/KI_template.md` in favor of package template.

## [2.3.0.dev2] — 2026-10-06

### Added
- `ki_search` output summarization & pagination: compact Markdown list formatting by default (saving up to 60% of context tokens and preventing MCP client disk dumping), reduced default result limit from 10 to 5, and added `offset` parameter for seamless result pagination.
- `ki_search` format option: added `format: "markdown"|"json"` allowing clients to choose between compact human/LLM-readable lists or raw JSON.
- `ki_read` and `read_know_file` character offset: added optional `offset` parameter enabling targeted reading from specific character positions without requiring repeated full reads.

### Changed
- `ki_read` path resolution: resilient cascade resolving paths relative to knowledge root (`.ki-base` by default), project root, subfolder prefixes, or filename basenames across KI and ADR documents.
- `ki_instructions` tool schema: aligned document list with active workflows (`scaffold-knowledge`, `expand-knowledge`, `sync-knowledge`, `create-adr`), removing deprecated `update-knowledge`.

### Fixed
- Fixed `KeyError: 'know_root'` in `ki_status` tool when checking active project status.

## [2.3.0.dev1] — 2026-10-05

### Added
- `--tool-mode full|compact` CLI option and `KI_TOOL_MODE` environment variable: compact facade mode reducing `tools/list` from 33 schemas to 6 essential tools (`ki_instructions`, `ki_search`, `ki_read`, `ki_tools`, `ki_call`, `ki_mutate`), drastically reducing context token usage for MCP clients.
- `ki_search` MCP tool & search engine: BM25 ranking across Knowledge Items and ADRs without external embedding dependencies, featuring bilingual RU/EN stemming, weighted fields (Title x5, Headers x3, Path x2, Body x1), and contextual snippets.
- `ki_read` MCP tool: token-efficient reader for KI and ADR markdown files with section filtering and character limit truncation.
- `ki_tools` MCP tool: grouped catalog of all available tools and on-demand JSON schema inspector.
- `ki_call` and `ki_mutate` facade dispatchers: safe routing with schema validation and enforcement of `readOnlyHint` (read-only queries in `ki_call`, mutations in `ki_mutate`).
- Dynamic instructions & template directives: workflows and server rules dynamically adapt tool call examples and `allowed-tools` frontmatter to active `--tool-mode` (`full` vs `compact`) via HTML comment directives (`<!-- if-compact -->`), maintaining a single source of truth without content divergence.
- Dedicated Agent Skill `ki-manager-workflows`: guide in `.agent/skills/ki-manager-workflows/` for authoring and maintaining dual-mode workflow instructions.
- CLI `install-skills` mode option: `ki-manager install-skills` supports `--tool-mode full|compact` to render installed skill markdown for the intended client environment.
- `add_ki_to_config` MCP tool and CLI helper: safely register or update Knowledge Items in `doc_config.json` with sandbox checks and atomic file updates.
- `edit_doc_config` MCP tool: granular and safe modifications (`set`, `append`, `delete`) to service sections (`tracked_modules`, `artifacts`, `coverage_settings`) of `doc_config.json`.
- `sync_agents_md` MCP tool and script: synchronize Knowledge Items and ADR tables in `AGENTS.md` using the single source of truth from `doc_config.json` and `decisions/`.
- Per-project configurable agent instructions sync: `sync_agents_md` can be disabled via `"sync_agents_md": false` in `ki_config.json` to prevent context pollution in large projects.
- `create_adr` MCP tool: create new Architecture Decision Records (ADR) with auto-incremented sequential ID prefix (`XXX`), standardized metadata, registration in `doc_config.json`, and automatic `AGENTS.md` sync.
- Structured ADR table parser and enhanced `ki://adr-list.md` virtual resource displaying ID, Title, Status, Date, and File links.
- Automatic IDE MCP tool schema generation (`<tool>.json`) for Antigravity, Cursor, and Windsurf on startup.
- Comprehensive positive and negative test suite for configuration tools, ADR creation, synchronization rules, and sandbox enforcement.
- Flexible configuration discovery: `ki_config.json` can now reside in project root, `.config/`, `config/`, `.ki-base/`, or `.know/`.
- Fileless project registration: `ki_register_project` now supports registering projects directly via `workspace` and `inline_config` in `~/.ki_base/registry.json` without requiring configuration files on disk.
- First-class custom knowledge root support: `paths.knowledge_root` is dynamically resolved and respected across all tools, engines, and scripts without chicken-and-egg discovery issues.
- Configurable scaffolding: `ki_init_project` now accepts `knowledge_root` and `config_location` (`root` or `knowledge_dir`) parameters.
- Dynamic workflow paths: workflow instructions dynamically substitute `{{KI_DIR}}` with the active project's knowledge folder name.
- Unit and negative test coverage for flexible discovery, custom roots, and registry validation errors.

### Changed
- `scaffold.migrate_project` now preserves existing `AGENTS.md` files instead of forcibly deleting them.
- Neutralized MCP tool descriptions and server prompt schemas, replacing hardcoded `.ki-base/` with dynamic references.


### Fixed
- Fixed an issue where `write_know_file` could permanently delete the contents of a file (leaving 0 bytes) if an encoding error occurred during saving.
- Fixed server crashes and communication failures on Windows when handling text with emojis or special Unicode characters.
- Fixed `edit_know_file` frequently failing to find and replace text blocks on Windows due to invisible line-ending mismatches (CRLF vs LF).
- Fixed the `update_last_verified` tool being completely unusable due to a "missing script" error.
- Fixed `git_checkpoint` failing to create backups when the project contained `.gitignore`'d files.
- Fixed incorrect schema definitions that prevented AI agents from successfully calling parameterless tools.
- Fixed outdated workflow instructions that were causing AI agents to fail by using the deprecated `ki_call` syntax.

## [2.2.0] — 2026-09-24

### Added
- `ki_graph_visualize` MCP tool: on-the-fly Mermaid architecture diagrams visualizing dependencies and file clusters across Knowledge Items.
- Cross-platform CI matrix workflow testing both Ubuntu and Windows environments on Python 3.10, 3.11, and 3.12.
- End-to-end MCP integration test suite validating real JSON-RPC stdio subprocess communication, handshake, and tool execution.
- Automated pre-flight release verification gate ensuring zero broken packages before release tagging.

### Fixed
- Proper exit codes and help formatting for `ki-manager-skills` CLI flags (`--help`, `-h`, `--version`).

## [2.1.4] — 2026-09-22

### Added
- Unified file and directory exclusion engine supporting glob patterns (`*`, `?`) across configuration files (`config.json`, `doc_config.json`, `ki_config.json`).
- Official project changelog following the Keep a Changelog standard.

### Changed
- Knowledge audit tools (`audit_coverage`, `find_unmapped_files`, `generate_dir_index`, `analyze_dependencies`) now consistently respect all configured exclusion rules.

### Fixed
- UTF-8 encoding crashes when running MCP tool scripts in Windows environments.

## [2.1.3] — 2026-08-12

### Added
- `ki_finalize_scaffolds` MCP tool for bulk finalizing generated Knowledge Item drafts.
- Bundled `scaffold-knowledge` workflow for AI coding assistants.
- Installation hint for `ki-manager-skills install-skills` displayed during server startup.

### Changed
- Synchronized Smithery catalog manifest with updated schemas for all 25 MCP tools.

## [2.1.2] — 2026-08-11

### Fixed
- Test suite verification during automated package build and release.

## [2.1.1] — 2026-08-11

### Fixed
- Workspace path resolution compliance with the updated MCP protocol specification.

## [2.1.0] — 2026-08-11

### Added
- Support for `server/discover` handshake and workspace folder detection under MCP 2026-07-28 protocol.
- `ki-manager-skills` CLI command to easily install bundled workflows into IDE skill directories.
- Automated release workflow for publishing packages to PyPI and Smithery Registry.

## [2.0.0] — 2026-07-24

### Added
- Initial 2.0 release of the `ki-manager` MCP server for project knowledge base management.

[Unreleased]: https://github.com/Laeryid/KI-base/compare/v2.3.0.dev1...HEAD
[2.3.0.dev1]: https://github.com/Laeryid/KI-base/compare/v2.2.1...v2.3.0.dev1
[2.2.1]: https://github.com/Laeryid/KI-base/compare/v2.2.0...v2.2.1
[2.2.0]: https://github.com/Laeryid/KI-base/compare/v2.1.4...v2.2.0
[2.1.4]: https://github.com/Laeryid/KI-base/compare/v2.1.3...v2.1.4
[2.1.3]: https://github.com/Laeryid/KI-base/compare/v2.1.2...v2.1.3
[2.1.2]: https://github.com/Laeryid/KI-base/compare/v2.1.1...v2.1.2
[2.1.1]: https://github.com/Laeryid/KI-base/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/Laeryid/KI-base/compare/v2.0.37...v2.1.0
[2.0.0]: https://github.com/Laeryid/KI-base/releases/tag/v2.0.0
