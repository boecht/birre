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