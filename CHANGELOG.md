# Changelog

All notable changes to BiRRe (BitSight Rating Retriever)
will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),

## [Unreleased]

### Changed

- Reorganized project structure into clean architecture layers
  - All source code now under `src/birre/` package
  - Organized into `application/`, `domain/`, `infrastructure/`, `integrations/` layers
  - API schemas moved to `resources/` directory
  - API documentation moved to `docs/apis/`

## [3.2.0] - 2025-10-27

### Added

- BIRRE_CONFIG_FILE environment variable support for specifying config file path (#73)
- Helpful user guidance for TLS handshake errors with structured logging (#72)
  - Detect intercepted certificate chains
  - Provide actionable error messages
  - Support for custom CA bundles

### Changed

- Moved live tests to `integration/` directory with updated fixtures (#74)
  - Better test organization and markers
  - Separate offline and online test suites

### Fixed

- Event loop closed errors during server startup (#76)
  - Introduced reusable sync bridge loop for synchronous operations
  - Disposable API bridges for startup checks
  - Proper cleanup with atexit handlers

### Improved

- Configuration file path handling and normalization (#75)
- CLI documentation with comprehensive usage examples
- Enhanced settings validation and tests

## [3.1.0] - 2025-10-24

### Added

- Consolidated `healthcheck` CLI command for comprehensive health checks (#67)
  - Offline and online diagnostics with detailed reporting
  - Support for `--production` flag to test against production API
  - Structured JSON output for machine-readable results
  - TLS error detection and fallback retry logic
  - Enhanced diagnostics coverage for all tool contexts (#68, #69)

### Changed

- Refactored CLI to Typer-based subcommand structure (#65)
  - Improved parameter grouping and help text organization
  - Better CLI command documentation (#70)

### Removed

- Deprecated Typer flag parameters (#71)

### Improved

- Healthcheck runner with updated diagnostics tests (#69)
- Test coverage for CLI commands and healthcheck functionality

## [3.0.0] - 2025-10-23

### Changed

- **BREAKING**: Migrated from custom config to Dynaconf (#43)
  - Simplified configuration resolution and validation
  - Better environment variable handling
  - Support for roles section for runtime config values (#41)
- **BREAKING**: Migrated from standard logging to structlog (#48)
  - JSON and text formatters with configurable output
  - Bound loggers with request context
  - Improved log file rotation and configuration
  - Support for sentinel log file disable values (#64)
- **BREAKING**: Migrated CLI from Click to Typer (#46, #65)
  - Rich formatting and improved help text
  - Better parameter grouping (#52)
  - Cleaner separation of concerns
- Replaced custom config.py with frozen dataclasses (#61)
  - Improved type safety and immutability
  - Better CLI override application (#51, #62)
- Use `prance` for loading API schemas (#42)
  - More robust OpenAPI schema handling
  - Better error reporting for schema issues
- Refactored business tool schemas to Pydantic models (#44)

### Fixed

- ANSI banners rendering using Rich markup (#66)
- API schema response normalization (#49)

### Improved

- README configuration and CLI options documentation
- Configuration file path handling (#50, #57, #60)

## [2.3.0] - 2025-10-19

### Changed

- Normalized configuration inputs across sources (#36)
- Centralized config literals into constants (#40)

### Improved

- Configuration layering and override reporting (#37)
- Boolean and integer config coercion (#38)
- Blank value handling in config resolution (#39)
- Logging override handling in application settings (#29)
- Configuration handling to avoid environment side effects (#32)

## [2.2.0] - 2025-10-15

### Improved

- Top findings assembly to reduce complexity (#27, #28)
- Risk manager interactive search complexity (#26)
- Company request flow complexity (#30)
- Severity score helper (#23)
- Folder membership helper (#24)
- Settings resolution for clarity (#25)

## [2.1.0] - 2025-10-14

### Added

- New OpenAPI parser support (#19)
- Keyboard interrupt handling during server operation (#20)

### Changed

- Adopted reverse-DNS identifier for MCP server (#2)
- Published tool output schemas (#2)

### Fixed

- Multiple SonarQube reliability findings (#3, #4)
  - Reduced cognitive complexity in config and risk manager
  - Fixed unused parameters and variables
  - Improved error handling patterns
- Schema-only OpenAPI responses normalization (#5)
- FastMCP instructions type compatibility (#18)

### Improved

- FastMCP bridge result handling (#11)
- Online startup checks validation (#10)
- BiRRe server factory (#7)
- Subscription helper complexity (#8)
- Request ID extraction helper (#9)
- Schema response normalization (#6)
- Server tests with async call tracking (#17)
- JSON formatter cognitive complexity (#21)
- Subscription quota check (#22)

## [2.0.0] - 2025-10-07

### Added

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

### Changed

- Tool filtering to expose only required v1 API endpoints
- Subscription management now uses bulk API endpoints

### Fixed

- pytest dependencies installation (#1)

### Improved

- Error handling and logging throughout

## [1.0.0] - 2025-10-05

### Added

- Initial BiRRe MCP server implementation
- Company search via BitSight `companySearch` API
- Company rating with trend analytics and top findings
  - Comprehensive rating details with trend information
  - Top vulnerability insights with severity-based sorting
  - Web application security findings
- Ephemeral subscription management and cleanup
- Basic startup diagnostics
- Configuration via environment variables and config files
- FastMCP integration for MCP server protocol

### Technical

- FastMCP pinned at version 2.12.4
- Python 3.10+ requirement
- Dependencies: fastmcp, python-dotenv, httpx

[Unreleased]: https://github.com/boecht/birre/compare/v3.2.0...HEAD
[3.2.0]: https://github.com/boecht/birre/compare/v3.1.0...v3.2.0
[3.1.0]: https://github.com/boecht/birre/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/boecht/birre/compare/v2.3.0...v3.0.0
[2.3.0]: https://github.com/boecht/birre/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/boecht/birre/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/boecht/birre/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/boecht/birre/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/boecht/birre/releases/tag/v1.0.0
