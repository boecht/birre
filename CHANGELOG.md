# Changelog

All notable changes to BiRRe (BitSight Rating Retriever) will be documented in this file.
See [Changelog Instructions](.github/instructions/edit-changelog.instructions.md) for updating guidelines.

## [4.0.0-beta.2] - 2025-11-17

### Changed

- **Breaking:** Replace mypy with pyright for type checking to simplify CI setup and improve type inference
- Refine workflow permissions and branch filters across CI pipelines to tighten security and reduce token scope
- Improve type safety across diagnostics and server modules with explicit casts and Protocol definitions for pyright
  compatibility
- Enhance async/sync bridge handling with proper event loop lifecycle management for more robust diagnostic operations
- Improve CLI version display to prefer local `pyproject.toml` version during development over installed package
  metadata

### Added

- Add Dependabot configuration for automated dependency updates (daily GitHub Actions, weekly pip packages)
- Add comprehensive type annotations to functions across CLI and application layers
- Add explicit Protocol definitions for better type checker compatibility

### Fixed

- Fix diagnostic tool invocations to use correct parameter names (action instead of name for subscriptions)
- Fix import ordering and formatting across test files for consistency
- Fix configuration validation to use equality comparison instead of identity for reliable parameter source detection
- Fix closed stream handling in logging to avoid exceptions during teardown

### Security

- Grant least-privilege permissions to CI workflows (contents: read where appropriate)

## [4.0.0-beta.1] - 2025-11-10

### Changed

- Streamline selftest invocation with typed CLI input dataclasses for
  clearer parameter handling and more predictable diagnostics
- Refactor risk-manager tools by extracting subscription and request
  helpers (folder resolution, domain parsing/deduplication, bulk payload
  construction, CSV serialization) to reduce duplication and improve
  maintainability
- Propagate folder GUIDs in runtime settings to enable automatic folder
  placement during manage/request operations without repeated lookups
- Enable MegaLinter local runner for developers to run comprehensive
  linting locally before pushing
- Refine pre-commit hook documentation with usage examples and local
  auto-fix guidance

### Added

- **TOP:** Add bulk company request workflow accepting CSV domain lists (1–255
  entries) with automatic deduplication via BitSight company search,
  multipart CSV submission to v2 bulk API, and structured reporting of
  submitted/existing/failed domains
- **TOP:** Document risk-manager tools: add docstrings and output
  semantics for `company_search_interactive`, `request_company`, and
  `manage_subscriptions` to clarify payloads, dry-run behavior, and
  example return shapes for better discoverability and QA
- Add automatic folder resolution and creation for subscription
  management and company request workflows, with timestamped audit
  metadata when creating new folders
- Add offline selftest replay samples enabling diagnostics to run without
  network connectivity by replaying recorded BitSight responses
- Add SonarQube remediation playbook prompt for structured,
  agent-assisted code quality fixes
- Add optional ruff auto-fix configuration guidance in local MegaLinter
  config for contributors

### Fixed

- Fix CI workflow permissions for release and lint workflows to properly
  allow SARIF uploads
- Fix SBOM artifact handling in PyPI publish workflow to prevent
  packaging errors
- Fix changelog extraction logic in release workflow for more robust
  version parsing

### Security

- **TOP:** Add Python 3.14 to CI cross-platform matrix to validate support on
  both Python 3.13 and 3.14
- Apply StepSecurity automated best-practices to harden GitHub Actions
  workflows
- Grant least-privilege permissions (contents: read) to CI workflows
  following security best practices

## [4.0.0-alpha.2] - 2025-11-05

### Changed

- **Breaking:** Require Python 3.13+ (upgrade from 3.11+ in alpha.1) to improve asyncio reliability
  and error clarity
- **TOP:** Enhance interactive search with bulk subscription, rating number + color, and parent hierarchy enrichment
- Improve startup reliability and remove event loop race conditions by simplifying async/sync bridge (lower memory)
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

- **TOP:** Add parent company enrichment and rating color details to interactive search results for richer risk context
- Add property-based testing (Hypothesis) to detect edge cases automatically in rating and findings logic
- Add performance benchmarks (pytest-benchmark) for critical paths to track regressions over time
- Add complexity checking (mccabe) to enforce a maximum function complexity threshold and surface refactor candidates
- Add dependency review, Scorecard, and Codecov workflows for safer dependencies and coverage transparency
- Add agent operations and prompt documentation to standardize automated contribution workflows

### Removed

- **TOP:** Remove dry-run shortcuts from diagnostics so production selftests execute real API calls for authentic validation
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
- **TOP:** Enhance selftest diagnostics with clearer output
- Remove over 3,200 lines of duplicate code to improve response times
- Improve CLI modularity and organization for easier troubleshooting
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

[4.0.0-alpha.2]: https://github.com/boecht/birre/compare/v4.0.0-alpha.1...v4.0.0-alpha.2
[4.0.0-beta.1]: https://github.com/boecht/birre/compare/v4.0.0-alpha.2...v4.0.0-beta.1
[4.0.0-alpha.1]: https://github.com/boecht/birre/compare/v3.2.0...v4.0.0-alpha.1
[3.2.0]: https://github.com/boecht/birre/compare/v3.1.0...v3.2.0
[3.1.0]: https://github.com/boecht/birre/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/boecht/birre/compare/v2.3.0...v3.0.0
[2.3.0]: https://github.com/boecht/birre/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/boecht/birre/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/boecht/birre/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/boecht/birre/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/boecht/birre/releases/tag/v1.0.0
