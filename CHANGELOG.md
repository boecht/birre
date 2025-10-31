# Changelog

All notable changes to BiRRe (BitSight Rating Retriever) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
adapted for BiRRe's quality-first approach.

## [4.0.0-alpha.2] - 2025-10-30

### Security

- Sign all releases cryptographically with Sigstore transparency log
- Verify release authenticity through keyless signature verification
- Ensure supply chain integrity with non-repudiable transparency entries
- Generate Software Bill of Materials (SBOM) for all releases
- Enforce code scanning on all pull requests (CodeQL, SonarCloud)
- Require security reviews before merging (High or higher alerts)

### Changed

- Enhance code reliability and maintainability through simplified error handling
- Improve diagnostic clarity with better error messages
- Reduce memory footprint and improve performance through code optimization
- Strengthen async operation handling during server startup
- Eliminate potential race conditions in event loop management
- Improve test coverage with property-based testing for edge cases
- Establish performance baselines for regression tracking
- Enforce strict quality gates on all code changes
- Verify compatibility across all major platforms (Windows, macOS, Linux)
- Replace magic numbers with named constants for better code clarity

### Fixed

- Correct type annotation for ephemeral subscription tracking (was dict, should be set)

### Added

- Provide release signature verification guide for users and developers
- Include comprehensive dependency inventory in all release artifacts
- Test data processing logic automatically with thousands of random inputs
- Detect edge cases in severity scoring and finding normalization
- Track performance metrics for critical code paths
- Monitor for performance regressions in search and findings processing
- Require all changes via pull requests with automated validation
- Integrate AI-assisted code review with GitHub Copilot
- Enforce conversation resolution before merging
- Block force pushes and direct commits to main branch
- Validate code on Windows, macOS, and Linux before merging
- Test with Python 3.11 and 3.12 for broad compatibility

## [4.0.0-alpha.1] - 2025-10-30

### Changed

- **Breaking:** Require Python 3.11+ for modern features and better performance
- Remove over 3,200 lines of duplicate code for faster response times
- Improve CLI modularity and organization for easier troubleshooting
- Enhance selftest diagnostics with clearer output
- Strengthen error handling throughout for better user experience

### Added

- Catch potential errors before runtime with strict type checking
- Provide better IDE support with improved autocompletion
- Track test coverage automatically with CodeCov integration
- Include coverage reports on pull requests for transparency
- Establish clear contribution guidelines and code of conduct
- Automate testing and security scanning on every pull request
- Support PyPI publishing in release pipeline

## [3.2.0] - 2025-10-27

### Added

- Support custom configuration file paths via `BIRRE_CONFIG_FILE` environment variable
- Provide clear error messages for TLS certificate issues with corporate proxies
- Include helpful guidance for resolving certificate problems

### Changed

- Improve server startup reliability with better event loop handling
- Enhance background task cleanup for more predictable behavior
- Strengthen configuration file path resolution and validation

### Fixed

- Resolve event loop errors that could prevent server startup

## [3.1.0] - 2025-10-24

### Added

- Provide comprehensive health check command with `birre selftest`
- Include detailed offline and online diagnostic reporting
- Test against production API with `--production` flag
- Support machine-readable JSON output for automation
- Detect TLS errors automatically with retry logic

## [3.0.0] - 2025-10-23

### Changed

- **Breaking:** Adopt industry-standard Dynaconf for simpler configuration
- **Breaking:** Switch to structured JSON logs for easier parsing
- **Breaking:** Modernize CLI framework with Rich formatting
- Improve configuration validation with clearer error messages
- Enhance environment variable support throughout
- Strengthen type safety with immutable configuration settings

### Fixed

- Resolve banner display issues with special characters
- Correct API response normalization edge cases

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

### Added

- Support multiple OpenAPI parser libraries for better compatibility
- Provide graceful shutdown on Ctrl+C with clean background task termination

### Changed

- Reduce code complexity throughout the codebase
- Improve FastMCP bridge reliability
- Enhance tool output schemas for better clarity
- Strengthen startup validation with thorough connectivity checks

## [2.0.0] - 2025-10-07

### Added

- Add risk manager context mode with specialized subscription management
- Provide `company_search_interactive` with folder membership and metadata
- Include `manage_subscriptions` with bulk operations and dry-run support
- Integrate `request_company` workflow with BitSight API v2
- Support context selection via CLI flag, environment variable, or configuration
- Establish comprehensive offline unit test suite
- Include online smoke tests for core workflows
- Provide startup diagnostics with structured JSON output

### Changed

- Filter tools to expose only required BitSight API v1 endpoints
- Migrate subscription management to bulk API endpoints

### Fixed

- Resolve pytest dependency installation issues

## [1.0.0] - 2025-10-05

### Added

- Implement BiRRe MCP server for BitSight integration
- Provide company search via BitSight API
- Include company rating with trend analytics and top findings
- Support ephemeral subscription management with automatic cleanup
- Establish basic startup diagnostics
- Enable configuration via environment variables and config files

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
