# Changelog

All notable changes to the `ki-manager` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- Note: This changelog is intended for end-users and AI agents. It must always be maintained in English and focus on user-facing features, behavior changes, and bug fixes rather than internal implementation details. -->

## [Unreleased]

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

[Unreleased]: https://github.com/Laeryid/KI-base/compare/v2.1.4...HEAD
[2.1.4]: https://github.com/Laeryid/KI-base/compare/v2.1.3...v2.1.4
[2.1.3]: https://github.com/Laeryid/KI-base/compare/v2.1.2...v2.1.3
[2.1.2]: https://github.com/Laeryid/KI-base/compare/v2.1.1...v2.1.2
[2.1.1]: https://github.com/Laeryid/KI-base/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/Laeryid/KI-base/compare/v2.0.37...v2.1.0
[2.0.0]: https://github.com/Laeryid/KI-base/releases/tag/v2.0.0
