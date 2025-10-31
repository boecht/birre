# CHANGELOG Standards for BiRRe

This document defines the CHANGELOG format and writing standards for BiRRe, based on industry
best practices from Keep a Changelog and Common Changelog, adapted to BiRRe's principles.

## Core Principles

1. **Changelogs are for humans, not machines** - Write clearly and concisely
2. **Focus on user benefits, not technical implementation** - Describe impact, not code changes
3. **Breaking changes are normal** - Make them highly visible
4. **Quality over backwards compatibility** - Don't sugarcoat necessary changes

## Format Standards

### File Structure

```markdown
# Changelog

All notable changes to BiRRe will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
adapted for BiRRe's quality-first approach.

## [4.0.0] - 2024-01-15

### Changed
- **Breaking:** Simplified configuration format for better clarity
- Enhanced startup reliability through optimized initialization

### Added
- New health check capabilities for service monitoring

### Deprecated
- Legacy sync mode (use async mode instead, will be removed in 5.0.0)

### Removed
- **Breaking:** Dropped support for Node.js 14 and 16

### Fixed
- Resolved memory leak in long-running processes
- Corrected error messages for invalid API keys

### Security
- Updated dependencies to patch CVE-2024-XXXXX

## [3.2.0] - 2023-12-10

...
```

### Required Elements

- **File name**: `CHANGELOG.md` in project root
- **Date format**: ISO 8601 (YYYY-MM-DD)
- **Version headings**: H2 (`## [version] - date`)
- **Category headings**: H3 (`### Added`, `### Changed`, etc.)
- **Chronological order**: Newest versions first
- **Clean version numbers**: No "v" prefix in headings

## Categories

Use exactly these six categories, in this order:

1. **Changed** - Changes to existing functionality
2. **Added** - New features or capabilities
3. **Deprecated** - Features scheduled for removal (with timeline)
4. **Removed** - Deleted features or functionality
5. **Fixed** - Bug fixes and corrections
6. **Security** - Security improvements, vulnerability patches, dependency updates

### When to Use Each Category

| Category | Use For | Don't Use For |
|----------|---------|---------------|
| **Changed** | Modified behavior, improved performance | Internal code changes |
| **Added** | New tools, commands, options, capabilities | Internal utilities |
| **Deprecated** | Features marked for removal (include timeline) | Removed features |
| **Removed** | Deleted features, dropped support, removed APIs | Code cleanup |
| **Fixed** | Bug fixes, error corrections, improved messages | Quality improvements |
| **Security** | Vulnerability patches, dependency updates | General improvements |

## Writing Style

### Imperative Mood (Required)

Write entries in imperative mood, as if giving a command:

- ✅ **Correct**: "Add health check endpoint"
- ✅ **Correct**: "Remove deprecated sync mode"
- ✅ **Correct**: "Fix memory leak in API client"
- ❌ **Wrong**: "Added health check endpoint"
- ❌ **Wrong**: "Removed deprecated sync mode"
- ❌ **Wrong**: "Fixed memory leak in API client"

### User Benefits (Required)

Describe WHAT users experience, not HOW it was implemented:

- ✅ **Good**: "Enhanced startup reliability and reduced memory usage"
- ✅ **Good**: "Catch potential errors before runtime with strict type checking"
- ✅ **Good**: "Faster command execution through optimized dependency loading"
- ❌ **Bad**: "Refactored sync_bridge.py to remove global state"
- ❌ **Bad**: "Achieved 100% strict mypy compliance across 47 source files"
- ❌ **Bad**: "Reduced cyclomatic complexity from 15 to 8 in 7 functions"

### Self-Describing (Required)

Each entry should be understandable without external context:

- ✅ **Good**: "Resolve authentication failures when API key contains special characters"
- ✅ **Good**: "Add `--verbose` flag to display detailed diagnostic information"
- ❌ **Bad**: "Fix issue #123" (requires looking up the issue)
- ❌ **Bad**: "Implement TD-003" (internal tracking code)

### Breaking Changes (Required Format)

Prefix breaking changes with `**Breaking:**` in bold:

```markdown
### Changed
- **Breaking:** Configuration now uses TOML format instead of JSON
- **Breaking:** Rename `--api-key` flag to `--token` for consistency

### Removed
- **Breaking:** Drop support for Python 3.8 and 3.9
```

## What to Include

### ✅ Always Include

- **User-facing changes**: New features, changed behavior, removed functionality
- **Breaking changes**: Anything requiring user action (migrations, config changes, etc.)
- **Bug fixes**: Especially those affecting user experience
- **Security updates**: Vulnerability patches, dependency updates with CVEs
- **Deprecation notices**: Features scheduled for removal (with timeline and alternative)
- **Performance improvements**: When noticeable to users (startup time, memory usage)

### ❌ Never Include

- **Internal refactoring**: Code quality improvements users won't notice
- **Work package codes**: TD-XXX, QA-XXX, or similar internal tracking
- **Implementation details**: Function names, file paths, complexity scores
- **Dependency version bumps**: Unless fixing security issues or adding features
- **Test improvements**: Unless exposing new testing capabilities to users
- **Documentation fixes**: Minor typo corrections (group these if many)

## Anti-Patterns to Avoid

### ❌ Git Log Dumps

Don't paste commit messages verbatim:

```markdown
❌ BAD:
- chore: bump dependencies
- fix: typo in error message
- refactor: simplify config loading
- docs: update readme
```

Group and describe user impact:

```markdown
✅ GOOD:
### Fixed
- Improve error messages for invalid configuration files
```

### ❌ Internal Tracking Codes

Don't reference internal work items:

```markdown
❌ BAD:
- Implement TD-003: Async/sync bridge simplification
- Complete QA-012: Code complexity analysis
```

Describe user-facing benefits:

```markdown
✅ GOOD:
### Changed
- Enhanced code reliability and reduced startup time
```

### ❌ Technical Implementation Details

Don't describe HOW, describe WHAT:

```markdown
❌ BAD:
- Refactor 7 complex functions across 5 modules to reduce cyclomatic complexity

✅ GOOD:
- Improve code reliability and maintainability
```

## Examples

### Good CHANGELOG Entry

```markdown
## [4.0.0] - 2024-01-15

### Changed
- **Breaking:** Simplify configuration format - now uses single TOML file instead of multiple JSON files
- Faster startup time through optimized dependency loading
- More informative error messages for API authentication failures

### Added
- Health check command (`birre health`) for service monitoring
- `--dry-run` flag for testing commands without making changes
- Security: API request signing for enhanced authentication

### Deprecated
- Legacy synchronous mode (use async mode instead, sync will be removed in 5.0.0)

### Removed
- **Breaking:** Drop support for Python 3.8 and 3.9 (minimum Python 3.10 required)
- **Breaking:** Remove `--legacy-api` flag (API v2 is now default)

### Fixed
- Resolve memory leak in long-running API polling
- Correct timeout handling for slow network connections
- Fix crash when API key contains special characters

### Security
- Update dependencies to patch CVE-2024-XXXXX in httpx
```

### Bad CHANGELOG Entry

```markdown
## [4.0.0] - 2024-01-15

### Changed

- Completed TD-003: Async/sync bridge simplification
- Refactored sync_bridge.py from ~100 to ~50 lines
- Improved event loop management for Python 3.13+ compatibility
- Achieved zero radon complexity violations

### Added

- Implemented health check (see issue #45)

### Removed

- Dropped old Python versions per deprecation policy
```

## Version Numbers

Follow [Semantic Versioning](https://semver.org/):

- **Major** (X.0.0): Breaking changes, API changes, dropped support
- **Minor** (x.Y.0): New features, deprecations, backwards-compatible changes
- **Patch** (x.y.Z): Bug fixes, security patches, minor improvements

## Workflow Integration

1. **During Development**: Track notable changes mentally or in draft notes
2. **Before Release**: Update CHANGELOG.md with all user-facing changes
3. **On Release**: Ensure CHANGELOG entry matches git tag and version
4. **After Release**: Move on - no "Unreleased" section

## Tools and Automation

- **Manual only**: BiRRe CHANGELOG is hand-written for quality and user focus
- **No automation**: Tools like conventional-changelog or git-cliff are NOT used
- **Commit messages**: Technical details go here, not in CHANGELOG
- **Git history**: Full audit trail exists in commits, not CHANGELOG

## References

This standard is based on:

- [Keep a Changelog](https://keepachangelog.com/) - Format and categories
- [Common Changelog](https://common-changelog.org/) - Writing style and strictness
- BiRRe Project Principles - User focus and quality over compatibility
