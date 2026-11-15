# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project uses
[ZeroVer](https://0ver.org/): versions stay `0.x.y`; breaking changes bump the minor
version, features and fixes bump the patch version.

## [Unreleased]

## [0.1.1]

### Fixed

- Stop the `caldav` library from logging event titles and other event content when it repairs
  malformed iCalendar data, and run the server at log level WARNING so response bodies are not
  logged at INFO.

## [0.1.0]

### Added

- MCP server for iCloud Calendar over CalDAV with tools `list_calendars`, `list_events`,
  `get_event`, `create_event`, `update_event` and `delete_event`.
- stdio transport (default) and SSE transport with a required bearer token.
- Read-only mode, `*_FILE` variants for secrets, default timezone setting.
- Container image for `linux/amd64` and `linux/arm64` with provenance and SBOM attestations.

[Unreleased]: https://github.com/hrsather/icloud-calendar-mcp/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/hrsather/icloud-calendar-mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/hrsather/icloud-calendar-mcp/releases/tag/v0.1.0
