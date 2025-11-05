# Changelog

All notable changes to BiRRe (BitSight Rating Retriever) will be documented in this file.
See [Changelog Instructions](.github/instructions/edit-changelog.instructions.md) for updating guidelines.

## [4.0.0-alpha.2] - 2025-11-05

### Changed

- **Breaking:** Require Python 3.13+ (upgrade from 3.11+ in alpha.1) to improve asyncio reliability
  and error clarity
- Improve startup reliability and remove event loop race conditions by simplifying async/sync bridge (lower memory)
- Enhance interactive search with bulk subscription, rating number + color, and parent hierarchy enrichment
- Improve selftest output by placing machine-readable JSON summary first with compact formatting for quicker
  automation parsing
- Reduce CLI and diagnostics complexity through extensive refactors for more predictable behavior and lower
  maintenance risk
- Improve logging robustness by guarding against writes to closed streams to prevent noisy teardown errors
- Accept expected 400 "already requested" responses as successful diagnostics connectivity checks
- Standardize test selection flags (`--offline`, `--online-only`) across CLI, docs, and workflows for clearer usage
- Prefer local `pyproject.toml` version when displaying CLI version to give accurate development context
- Establish performance baselines with benchmark suite to enable future regression detection
- Increase code clarity and reliability by replacing magic numbers with named constants and
  enforcing low complexity thresholds
- Streamline release workflow with validated version inputs and safer tag extraction for consistent releases
- Improve Windows/macOS/Linux parity with cross-platform test matrix running under Python 3.13
- Consolidate formatting and validation utilities for consistent, cleaner CLI tables and messages
- Improve company rating workflow reliability by handling both sync and async tool results seamlessly
- Improve contributor experience with clearer prompt and agent operation documentation
- Stabilize CI by re-adding pinned action versions after evaluating removal impacts

### Added

- Add property-based testing (Hypothesis) to detect edge cases automatically in rating and findings logic
- Add performance benchmarks (pytest-benchmark) for critical paths to track regressions over time
- Add complexity checking (mccabe) to enforce a maximum function complexity threshold and surface refactor candidates
- Add parent company enrichment and rating color details to interactive search results for richer risk context
- Add dependency review, Scorecard, and Codecov workflows for safer dependencies and coverage transparency
- Add agent operations and prompt documentation to standardize automated contribution workflows

### Removed

- Remove dry-run shortcuts from diagnostics so production selftests execute real API calls for authentic validation
- Remove thousands of lines of duplicate and obsolete CLI/diagnostic helper code to lower memory usage and
  improve performance

### Fixed

- Fix configuration validation to compare enum values with equality instead of identity for
  reliable parameter source detection
- Fix selftest failures by correcting tool parameter names and making mock context methods async
- Fix interactive search 403 errors by creating required ephemeral subscriptions before fetching company details
- Fix logging handler errors during teardown by safely ignoring closed stream writes
- Fix background task handling to keep tasks alive during sync bridge tests preventing premature cancellation issues
- Fix Windows path and whitespace normalization in CLI tests to avoid spurious failures across platforms
- Fix version display fallback logic to show meaningful messages when local version metadata is unavailable
- Fix release workflow to sanitize version inputs and prevent command injection via workflow dispatch values
- Fix subscription tracking type (use set instead of dict) to correct ephemeral subscription handling

### Security

- Harden release workflow with strict version validation and sanitized tag extraction
- Enforce least-privilege GitHub Actions permissions (contents: read) across workflows to reduce token scope
- Add Dependency Review Action to block introduction of known vulnerable packages before merge
- Add OpenSSF Scorecard supply-chain security analysis for continuous security posture monitoring
- Maintain reproducible and verifiable CI by pinning critical GitHub actions versions for stability
- Expand automated code scanning (CodeQL, SonarCloud) coverage for earlier vulnerability and quality issue detection
- Fix residual security-related CI findings from alpha.1 release to strengthen baseline

## [4.0.0-alpha.1] - 2025-10-30

### Changed

- **Breaking:** Require Python 3.11+ for modern features and better performance
- Remove over 3,200 lines of duplicate code to improve response times
- Improve CLI modularity and organization for easier troubleshooting
- Enhance selftest diagnostics with clearer output
- Strengthen error handling throughout for better user experience

### Added

- Add strict type checking to catch potential errors before runtime
- Add better IDE support with improved autocompletion
- Add automatic test coverage tracking with CodeCov integration
- Add coverage reports on pull requests for transparency
- Add clear contribution guidelines and a code of conduct
- Add release pipeline support for PyPI publishing

### Security

- Add automated security scanning on every pull request

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

- Add comprehensive health check command with `birre selftest`
- Add detailed offline and online diagnostic reporting
- Add production API testing with `--production` flag
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

- Add risk manager context mode with specialized subscription management
- Add interactive company search tool `company_search_interactive` with folder membership and metadata
- Add bulk subscription management tool `manage_subscriptions` with dry-run support
- Add `request_company` workflow using BitSight API v2
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

[4.0.0-alpha.2]: https://github.com/boecht/birre/compare/v4.0.0-alpha.1...v4.0.0-alpha.2
[4.0.0-alpha.1]: https://github.com/boecht/birre/compare/v3.2.0...v4.0.0-alpha.1
[3.2.0]: https://github.com/boecht/birre/compare/v3.1.0...v3.2.0
[3.1.0]: https://github.com/boecht/birre/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/boecht/birre/compare/v2.3.0...v3.0.0
[2.3.0]: https://github.com/boecht/birre/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/boecht/birre/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/boecht/birre/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/boecht/birre/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/boecht/birre/releases/tag/v1.0.0
