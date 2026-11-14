# Changelog

All notable changes to the `ki-manager` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- Note: This changelog is intended for end-users and AI agents. It must always be maintained in English and focus on user-facing features, behavior changes, and bug fixes rather than internal implementation details. -->

## [Unreleased]

## [2.4.0.dev0] — 2026-11-14

### Added
- **Just-in-Time Context Delivery (`ki_context_for`)**:
  - Added eager MCP tool `ki_context_for(files, max_chars=2000, include_poc=True, force=False)` across both `full` (40 tools) and `compact` (8 tools) modes.
  - Matches target file paths, directories, and glob patterns (`*`, `**`, `?`) against `doc_config.json` `depends_on` and ADR `Scope & Affected Files` / `Related KI` references.
  - Prioritizes KI `## Invariants`, `## Non-obvious Details`, and `## Common Pitfalls`, and ADR `## Invariants & Rules for AI`, excluding `superseded`/`draft`/`archived`/`deprecated` entries and tagging `stale`/`poc`/`stub`.
- **Smart Session Deduplication Cache**:
  - Caches per-rule content hashes, timestamps (configurable TTL via `context_cache_ttl` in `ki_config.json` or `KI_CONTEXT_CACHE_TTL`), and step counts under `~/.ki_base/cache/`.
  - Replaces repeated unchanged deliveries with compact markers (`Already delivered: ... Pass force=true if context was compacted.`), automatically invalidating on file edits, TTL expiry, or `force=true`.
- **Deterministic Linter (`ki_lint`) & Composite Sync (`ki_sync`)**:
  - Added `ki_lint` MCP tool and `ki-manager lint [--staged] [--fix] [--json]` CLI checking KB directory layout, `_OVERVIEW.ki.md` presence, valid lifecycle statuses, acyclic `superseded_by` chains, `last_verified` tags, unfilled sections, and `depends_on` disk existence.
  - Added `ki_sync` MCP tool combining `ki_lint` → diff → `check_ki_drift` → targeted `update_last_verified` → `DIR_INDEX.md` → `save_state` → `AGENTS.md` into one gated call.
- **Lifecycle Statuses & Bidirectional Superseding**:
  - Standardized normalized statuses: ADR (`draft`, `poc`, `accepted`, `superseded`, `deprecated`, `archived`; `proposed` aliases to `draft`) and KI (`stub`, `draft`, `poc`, `active`, `stale`, `archived`).
  - `create_adr(..., supersedes=[...])` writes `<!-- superseded_by: NNN -->` markers and structured `status` / `superseded_by` fields in `doc_config.json`.
  - Filtered `AGENTS.md` tables (hiding `superseded`/`deprecated`/`archived` ADRs and `archived` KIs behind summary hints) and added `status` / `include_inactive` filtering in `ki_list` and `ki_search`.
- **Optional Git & Declarative Agent Harness Hooks**:
  - Added `ki-manager install-hooks` for universal Git `pre-commit` (`ki-manager lint --staged`), works in any IDE without runtime hook support.
  - Added declarative JSON harness manifests with bundled presets (`antigravity` with aliases `agy`/`antigravity`/`vaib`, and `claude` with aliases `claude`/`claude-code`) plus project/user custom manifests in `.ki-base/harnesses/` or `~/.ki_base/harnesses/`.
  - Added `ki-manager install-hooks --harness <name_or_file>` (non-destructive idempotent merge), `--list-harnesses`, and `ki-manager hook pre-edit|stop-lint` integrating with the shared `ki_context_for` deduplication cache.

### Changed
- **Git Hygiene & Targeted Verification**:
  - `git_checkpoint` now includes `doc_state.json` and no longer auto-commits unless `commit=true` is passed or `auto_git_checkpoint: true` is enabled in `ki_config.json`.
  - `update_last_verified` updates only KIs affected by uncommitted git changes or code diffs (including nested subdirectories in `knowledge/`), or explicit `ki_files`.
- **Native File Tooling Freedom**:
  - Relaxed workflow instructions across `overview`, `agent-rules`, `create-adr`, `expand-knowledge`, `scaffold-knowledge`, and `sync-knowledge` to allow native `read_file` / `edit_file` inside `knowledge/` and `decisions/`, backed by `ki_lint` and `ki_sync`.

## [2.3.3.dev3] — 2026-11-08

### Fixed
- **`check_ki_drift` Dead Symbol False Positives**:
  - Module constants, dictionaries, and configuration mappings (e.g. `DEFAULT_STYLES`, `SPINNERS`) listed in the Key Components table are now recognized as valid defined symbols across all casing conventions.
  - Multi-symbol compound entries separated by delimiters (`/`, `,`, `;`, `|`, `&`, e.g. `cell_len / set_cell_size`) are now individually tokenized and validated without false-positive dead symbol warnings while preserving accurate detection if a single member is missing.
  - Informational and descriptive table markers (such as `*(lookup table)*`, `*(file)*`, `(constants)`, `N/A`, `—`) are automatically filtered and no longer treated as missing code symbols.
- **`check_ki_drift` Unmapped Symbols Noise Reduction**:
  - `unmapped_symbols` are excluded from the primary `drift_count`, preventing false-alarm drift warnings on curated architectural KIs.
  - Files tracked in git that have not been modified since their `last_verified` date suppress unmapped symbol warnings, respecting the selective nature of Key Components tables.
  - When code has changed after verification, unmapped symbols are presented cleanly with an informational `[i]` marker as advisory coverage hints rather than errors.


## [2.3.3.dev2] — 2026-11-08

### Added
- **`ki_split_analyze` & `ki_split` Tools for B-Tree KI Decomposition**:
  - `ki_split_analyze`: Computes static import graph bisection for overloaded KIs (>10 files), identifying internal dependencies and suggesting balanced Group A (Core / Foundation) and Group B (Components / High-level) splits.
  - `ki_split`: Atomically executes KI bisection into two balanced KIs, verifying that no files are lost or duplicated, updating `doc_config.json`, and cleaning up the renamed original KI.
  - Exposed in full mode (37 tools) and registered under `scaffold` tool group for compact facade mode (`ki_call` for analyze, `ki_mutate` for apply).
- **Direct `ignore_dirs` Management in `edit_doc_config`**:
  - Added `section="ignore_dirs"` in `edit_doc_config` for quickly excluding directories (such as benchmarks or assets) from coverage audits.

### Fixed
- **`audit_coverage` Untracked Blind Spots & Density Saturation**:
  - `find_untracked_dirs` now filters candidates strictly by recognized source code extensions (`.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.go`, `.rs`, `.java`, etc.), eliminating false-positive `⚠️ UNTRACKED AREAS` on assets, images, and non-code documentation folders.
  - Introduced saturation threshold (`min_ki_bytes`, default 3,500 bytes) and configurable `coverage_settings` (`density_threshold`, `min_ki_bytes`, `complexity_threshold`) in `doc_config.json`. Comprehensive KIs covering large codebases no longer trigger false-positive `❄️ LOW DENSITY` warnings.
- **Support for `ignore_dirs` and `exclude_dirs` in Configs**:
  - `ki_utils.get_exclude_patterns` now automatically loads `ignore_dirs` and `exclude_dirs` across all config files (`doc_config.json`, `config.json`, `ki_config.json`).
- **`ki_scaffold` File-Level Tracking & Auto-Clustering**:
  - Removed insertion of top-level directory paths into `depends_on`, enabling accurate multi-KI coverage for single tracked modules.
  - Automatically clusters flat modules with >10 files into cohesive sub-KIs (each $\le 10$ files) by subdirectories or name prefixes, avoiding single monolithic scaffold KIs.
- **`find_unmapped_files` Architectural Weight Sorting**:
  - Sorts unmapped files by architectural weight (internal incoming import count + file size), guiding agents to document core module hubs before peripheral utilities.
  - Displays existing KIs and their file counts for the queried module to simplify semantic merge decisions.
- **`expand-knowledge` Workflow**:
  - Enriched workflow with B-Tree semantics: prioritizes semantic merging of unmapped files into existing KIs, followed by atomic bisection on overflow (>10 files) via `ki_split`.

## [2.3.3.dev1] — 2026-11-08

### Fixed
- **`scaffold-knowledge` Cold Start & Initial Coverage**:
  - `audit_coverage` now detects and displays candidate code directories when `tracked_modules` in `doc_config.json` is unconfigured, providing actionable commands to register modules instead of silently exiting.
  - `ki_scaffold` no longer outputs a false-positive "No uncovered modules found" message on empty configurations; clearly indicates missing tracked modules and guides configuration.
  - `ki_scaffold(modules="<path>")` now scaffolds specified modules even when `tracked_modules` is currently empty and automatically registers them into `doc_config.json`.
- **Tolerant Schema Parsing for `tracked_modules`**:
  - Transparently normalizes diverse module entry formats (simple string `"module"`, partial tuples `["module"]`, or dictionary `{ "path": "module" }`) into standard `[module_path, label, importance]` triples across all analysis and scaffolding tools.
  - Fixed crashes (`ValueError` / `IndexError`) when appending raw module strings via `edit_doc_config`.
- **`edit_doc_config` Validation & Deduplication**:
  - Documented canonical `[module_path, label, importance]` format in tool schema and description.
  - Automatically normalizes string module paths and prevents duplicate module entries on `append`.

## [2.3.2] — 2026-11-07

### Added
- **`ki_list` Navigation Tool**:
  - Direct navigation tool to list registered Knowledge Items and Architecture Decision Records (ADRs) with summaries and covered modules without filesystem scans.
  - Supports filtering by type (`scope: "all" | "ki" | "adr"`), output formats (`format: "markdown" | "json"`), and search query (`filter: "<text>"`).
  - Available as a direct top-level tool in both full mode (35 tools) and compact facade mode (7 tools).
- **BM25 Search Pagination (`ki_search`)**:
  - Added 1-based `page` parameter for intuitive result pagination alongside `offset`.
  - Prominent pagination header and next-page action hints (`[Page X/Y]`, `Next page: ki_search(query="...", page=X+1)`) in search outputs to prevent AI models from getting stuck in repeat queries.

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
