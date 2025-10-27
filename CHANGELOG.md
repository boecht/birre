# Changelog

All notable changes to BiRRe (BitSight Rating Retriever) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.1.0] - 2025-10-27

### Added

- Consolidated `selftest` CLI command for comprehensive health checks (#67)
  - Offline and online diagnostics with detailed reporting
  - Support for `--production` flag to test against production API
  - Structured JSON output for machine-readable results
  - TLS error detection and fallback retry logic
  - Enhanced diagnostics coverage for all tool contexts (#68, #69)
- `BIRRE_CONFIG_FILE` environment variable support for specifying config file path (#73)
- CLI commands: `version`, `readme`, and improved `main()` entrypoint
- Helpful user guidance for HTTP 403 errors in testing environment
- Comprehensive test suite for sync bridge functionality

### Changed

- **BREAKING**: Refactored CLI to Typer-based subcommand structure (#65)
  - Commands now use explicit subcommands: `run`, `selftest`, `healthcheck`, `check-conf`, `logs`
  - Improved parameter grouping and help text organization
  - Removed deprecated flag-style parameters (#71)
- Migrated from custom logging to `structlog` for structured logging (#48)
  - JSON and text formatters with configurable output
  - Bound loggers with request context
  - Improved log file rotation and configuration
- Replaced custom config layering with Dynaconf (#43)
  - Simplified configuration resolution and validation
  - Better environment variable handling
  - Centralized config literals into constants (#40, #50)
- Refactored configuration handling to use frozen dataclasses (#61)
  - Improved type safety and immutability
  - Better CLI override application (#51, #62)
  - Cleaner separation of concerns
- Moved live tests to `integration/` directory with updated fixtures (#74)
  - Better test organization and markers
  - Separate offline and online test suites
- Use `prance` for loading API schemas (#42)
  - More robust OpenAPI schema handling
  - Better error reporting for schema issues

### Fixed

- Event loop closed errors during server startup (#76)
  - Introduced reusable sync bridge loop for synchronous operations
  - Disposable API bridges for startup checks
  - Proper cleanup with atexit handlers
- TLS handshake errors with structured logging and user guidance (#72)
  - Detect intercepted certificate chains
  - Provide actionable error messages
  - Support for custom CA bundles
- ANSI banners rendering using Rich markup (#66)
- Sentinel log file disable values (`-`, `none`, `stderr`, `stdout`) (#64)
- Keyboard interrupt handling during server operation (#20)
- Multiple SonarQube reliability and code quality findings (#3, #4)
  - Reduced cognitive complexity in multiple modules
  - Fixed unused parameters and variables
  - Improved error handling patterns

### Improved

- CLI documentation with comprehensive usage examples (#70)
- Configuration file path handling and normalization
- README configuration and CLI options documentation
- Test coverage for CLI commands, settings, and startup checks
- Code organization and module structure
  - Refactored business tool schemas to Pydantic models (#44)
  - Reduced complexity in risk manager and rating modules (#23-#30)
    - Better separation of API client concerns

### Technical

- Ensured FastMCP new OpenAPI parser is always enabled (#19)
- Improved FastMCP bridge result handling (#11)
- Refined async call tracking in tests (#17)
- Normalized schema-only OpenAPI responses (#5)
- Updated test compatibility for function signature changes

## [3.0.0] - 2025-10-06

### Features

- Risk manager context mode with specialized tooling
  - `company_search_interactive`: Enhanced search with folder membership and subscription metadata
  - `manage_subscriptions`: Bulk subscription management with dry-run support
  - `request_company`: Company request workflow with v2 API integration
- Context selection via `--context` CLI flag, `BIRRE_CONTEXT` environment variable, or config
- BitSight API v2 integration for company requests
- Comprehensive offline unit test suite
  - Configuration layering tests
  - Logging formatter tests
  - Startup checks validation
  - Tool behavior verification
- Online smoke tests for company search and rating workflows
- Startup diagnostics with structured JSON output
  - Offline checks for schemas, configuration, and credentials
  - Online checks for API connectivity, folders, and quotas
  - Configurable via `--skip-startup-checks`

### Improvements

- Tool filtering to expose only required v1 API endpoints
- Subscription management now uses bulk API endpoints
- Improved error handling and logging throughout

### Fixes

- FastMCP instructions type compatibility (#18)
- Schema response normalization for edge cases

## [2.0.0] - 2025-10-05

### New Features

- Top vulnerability insights in company rating response
  - `top_findings` block with relaxed filtering
  - Web application security findings padding
  - Severity-based sorting with importance and recency metrics
- Enhanced findings analysis and presentation

### Changes

- Rating payload now includes enriched vulnerability data
- Improved findings sorting logic

## [1.0.0] - 2025-10-04

### Initial Release

- Initial release with core functionality
- Company search via BitSight `companySearch` API
- Company rating with trend analytics
- Ephemeral subscription management and cleanup
- Basic startup diagnostics
- Configuration via environment variables and config files
- FastMCP integration for MCP server protocol

### Dependencies

- FastMCP pinned at version 2.12.4
- Python 3.10+ requirement
- Dependencies: fastmcp, dynaconf, pydantic, httpx, typer, rich, structlog

[Unreleased]: https://github.com/boecht/birre/compare/v3.1.0...HEAD
[3.1.0]: https://github.com/boecht/birre/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/boecht/birre/compare/v2.0.0...v3.0.0
[2.0.0]: https://github.com/boecht/birre/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/boecht/birre/releases/tag/v1.0.0
