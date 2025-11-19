# Changelog

All notable changes to BiRRe (BitSight Rating Retriever) will be documented in this file.
See [Changelog Instructions](.github/instructions/edit-changelog.instructions.md) for updating guidelines.

## [4.0.0] - 2025-11-19

### Changed

- **Breaking:** Require Python 3.13+ to unlock simplified async handling, improved asyncio reliability,
  and enhanced type inference
- **TOP:** Reduce CLI and diagnostics codebase by over 3,200 lines through systematic removal of duplicate helpers
  and obsolete delegation layers for faster startup and lower memory usage
- **TOP:** Improve interactive search for risk managers with parent company enrichment, rating color details,
  subscription state, and folder membership to support informed bulk operations
- Standardize test selection flags (`--offline`, `--online-only`) across CLI, docs, and workflows for consistent usage
- Replace mypy with pyright for type checking to simplify CI setup and improve type inference across toolchain
- Consolidate subscription helpers (automatic folder creation, dry-run previews, audit summaries)
  across `manage_subscriptions` and `request_company` for safer workflows
- Enhance async/sync bridge with proper event loop lifecycle management to eliminate race conditions and improve robustness
- Improve Windows/macOS/Linux parity with cross-platform test matrix running under Python 3.13

### Added

- **TOP:** Add bulk company request workflow accepting CSV domain lists (1–255 entries)
  with automatic deduplication via BitSight company search, multipart CSV submission to v2 bulk API,
  and structured reporting of submitted/existing/failed domains
- **TOP:** Add offline selftest replay samples enabling diagnostics to run without network connectivity
  by replaying recorded BitSight responses
- Add automatic folder resolution and creation for subscription management and company request workflows
  with timestamped audit metadata
- Add property-based testing (Hypothesis) to detect edge cases automatically in rating and findings logic
- Add performance benchmarks (pytest-benchmark) for critical paths to track regressions over time
- Add complexity checking (mccabe) to enforce maximum function complexity threshold and surface refactor candidates
- Add dependency review, Scorecard, and Codecov workflows for safer dependencies and coverage transparency
- Add MegaLinter local runner with pre-commit hooks for comprehensive linting before pushing
- Add clear contribution guidelines and code of conduct for community engagement

### Removed

- Remove dry-run shortcuts from diagnostics so production selftests execute real API calls for authentic validation
- Remove thousands of lines of duplicate and obsolete CLI/diagnostic helper code to lower memory usage and improve performance

### Fixed

- Fix configuration validation to use equality comparison instead of identity for reliable parameter source detection
  across enums and choices
- Fix interactive search 403 errors by creating required ephemeral subscriptions before fetching company details
- Fix background task handling to keep tasks alive during sync bridge tests preventing premature cancellation issues
- Fix event loop closed errors during server startup
- Fix Windows path and whitespace normalization in CLI tests to avoid spurious failures across platforms

### Security

- Sign every release artifact with Sigstore, publish SBOMs, and enforce GitHub dependency review throughout release pipeline
- Apply StepSecurity automated best practices to harden GitHub Actions workflows
- Add Dependency Review Action to block introduction of known vulnerable packages before merge
- Add OpenSSF Scorecard supply-chain security analysis for continuous security posture monitoring
- Add Python 3.14 to CI cross-platform matrix to validate forward compatibility
- Maintain reproducible and verifiable CI by pinning critical GitHub Actions versions for stability
- Expand automated code scanning (CodeQL) coverage for earlier vulnerability detection
- Harden release workflow with strict version validation and sanitized tag extraction to prevent command injection

## [3.2.0] - 2025-10-27

### Changed

- Improve server startup reliability with better event loop handling
- Enhance background task cleanup for more predictable behavior
- Strengthen configuration file path resolution and validation

### Added

- Add support for custom configuration file paths via `BIRRE_CONFIG_FILE` environment variable
- Add clear error messages for TLS certificate issues with corporate proxies
- Add guidance for resolving certificate problems

### Fixed

- Fix event loop closed errors during server startup

## [3.1.0] - 2025-10-24

### Added

- **TOP:** Add comprehensive health check command with `birre selftest`
- **TOP:** Add detailed offline and online diagnostic reporting
- **TOP:** Add production API testing with `--production` flag
- Add machine-readable JSON output for automation
- Add automatic TLS error detection with retry logic

## [3.0.0] - 2025-10-23

### Changed

- **Breaking:** Adopt industry-standard Dynaconf for simpler configuration
- **Breaking:** Switch to structured JSON logs for easier parsing
- **Breaking:** Modernize CLI framework with Rich formatting
- Improve configuration validation with clearer error messages
- Enhance environment variable support throughout
- Strengthen type safety with immutable configuration settings

### Fixed

- Fix banner display issues with special characters
- Fix API response normalization edge cases

## [2.3.0] - 2025-10-19

### Changed

- Normalize configuration handling across environment variables, files, and CLI flags
- Improve boolean and integer value parsing
- Enhance handling of blank and empty configuration values

## [2.2.0] - 2025-10-15

### Changed

- Simplify findings assembly and rating workflows for better reliability
- Reduce code complexity throughout for easier maintenance
- Strengthen error handling across all modules

## [2.1.0] - 2025-10-14

### Changed

- Reduce code complexity throughout the codebase
- Improve FastMCP bridge reliability
- Enhance tool output schemas for better clarity
- Strengthen startup validation with thorough connectivity checks

### Added

- Add support for multiple OpenAPI parser libraries for better compatibility
- Add graceful shutdown on Ctrl+C with clean background task termination

## [2.0.0] - 2025-10-07

### Changed

- Filter tools to expose only required BitSight API v1 endpoints
- Migrate subscription management to bulk API endpoints

### Added

- **TOP:** Add risk manager context mode with specialized subscription management
- **TOP:** Add interactive company search tool `company_search_interactive` with folder membership and metadata
- **TOP:** Add bulk subscription management tool `manage_subscriptions` with dry-run support
- **TOP:** Add `request_company` workflow using BitSight API v2
- Add context selection via CLI flag, environment variable, or configuration
- Add comprehensive offline unit test suite
- Add online smoke tests for core workflows
- Add startup diagnostics with structured JSON output

### Fixed

- Fix pytest dependency installation issues

## [1.0.0] - 2025-10-05

### Added

- Add BiRRe MCP server for BitSight integration
- Add company search via BitSight API
- Add company rating with trend analytics and top findings
- Add ephemeral subscription management with automatic cleanup
- Add basic startup diagnostics
- Add configuration via environment variables and config files

[4.0.0]: https://github.com/boecht/birre/compare/v3.2.0...v4.0.0
[3.2.0]: https://github.com/boecht/birre/compare/v3.1.0...v3.2.0
[3.1.0]: https://github.com/boecht/birre/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/boecht/birre/compare/v2.3.0...v3.0.0
[2.3.0]: https://github.com/boecht/birre/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/boecht/birre/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/boecht/birre/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/boecht/birre/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/boecht/birre/releases/tag/v1.0.0
