# Changelog

All notable changes to the `ki-manager` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- Note: This changelog is intended for end-users and AI agents. It must always be maintained in English and focus on user-facing features, behavior changes, and bug fixes rather than internal implementation details. -->

## [Unreleased]

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
