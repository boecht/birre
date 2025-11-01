---
applyTo: 'CHANGELOG.md'
---
# CHANGELOG Standards for BiRRe (Authoring Instructions)

This is the authoritative guidance for creating or editing `CHANGELOG.md`. It consolidates the standards previously documented in `docs/CHANGELOG_STANDARDS.md`.

## Core Principles

1. Changelogs are for humans, not machines — write clearly and concisely.
2. Focus on user benefits, not technical implementation — describe impact, not code changes.
3. Breaking changes are normal — make them highly visible.
4. Quality over backwards compatibility — don’t sugarcoat necessary changes.

## Format Standards

### File Structure

```markdown
# Changelog

All notable changes to BiRRe will be documented in this file.

The format is based on Keep a Changelog, adapted for BiRRe’s quality-first approach.

## [X.Y.Z] - YYYY-MM-DD

### Changed
-

### Added
-

### Deprecated
-

### Removed
-

### Fixed
-

### Security
-
```

### Required Elements

- File name: `CHANGELOG.md` in project root
- Date format: ISO 8601 (YYYY-MM-DD)
- Version headings: H2 (`## [version] - date`)
- Category headings: H3 (exactly the six below)
- Chronological order: newest versions first
- Clean version numbers: no `v` prefix

## Categories (use in this exact order)

1. Changed — Changes to existing functionality
2. Added — New features or capabilities
3. Deprecated — Features scheduled for removal (include timeline)
4. Removed — Deleted features or functionality
5. Fixed — Bug fixes and corrections
6. Security — Security improvements, vulnerability patches, dependency updates

### When to Use Each Category

| Category | Use For | Don’t Use For |
|---|---|---|
| Changed | Modified behavior, improved performance | Internal code changes |
| Added | New tools, commands, options, capabilities | Internal utilities |
| Deprecated | Features marked for removal (with timeline) | Removed features |
| Removed | Deleted features, dropped support, removed APIs | Code cleanup |
| Fixed | Bug fixes, error corrections, improved messages | Quality improvements |
| Security | Vulnerability patches, dependency updates | General improvements |

## Writing Style

### Imperative Mood (Required)

- Correct: “Add health check endpoint” / “Remove deprecated sync mode” / “Fix memory leak in API client”
- Wrong: “Added …”, “Removed …”, “Fixed …”

### User Benefits (Required)

- Good: “Enhance startup reliability and reduce memory usage”
- Bad: “Refactor sync_bridge.py to remove global state”

### Self-Describing (Required)

- Good: “Resolve authentication failures when API key contains special characters”
- Bad: “Fix issue #123” or “Implement TD-003”

### Breaking Changes (Required Format)

Prefix with `**Breaking:**` and place under Changed or Removed.

## Examples

### Good CHANGELOG Entry

```markdown
## [4.0.0] - 2024-01-15

### Changed
- **Breaking:** Simplify configuration format — now uses single TOML file instead of multiple JSON files
- Faster startup time through optimized dependency loading
- More informative error messages for API authentication failures

### Added
- Health check command (`birre health`) for service monitoring
- `--dry-run` flag for testing commands without making changes
- Security: API request signing for enhanced authentication

### Deprecated
- Legacy synchronous mode (use async mode instead; sync removed in 5.0.0)

### Removed
- **Breaking:** Drop support for Python 3.8 and 3.9 (minimum Python 3.10)
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
- Replaced complex reusable event loop with Python 3.xx+ asyncio.run()
- Achieved zero radon complexity violations

### Added
- Implemented health check (see issue #45)

### Removed
- Dropped old Python versions per deprecation policy
```

## Version Numbers

Follow Semantic Versioning: Major (breaking), Minor (features), Patch (fixes).

## Workflow Integration (authoring-relevant)

1. Before release: Update `CHANGELOG.md` with all user-facing changes.
2. On release: Ensure the entry matches the tag/version.
3. After release: No “Unreleased” section.

## Tools and Automation

- Manual only: hand-written for quality and user focus.
- No generators like conventional-changelog or git-cliff.
- Commit messages capture technical detail; changelog captures user impact.
