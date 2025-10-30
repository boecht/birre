# Release Process

This document describes how to create a new release of BiRRe.

## Prerequisites

- Maintainer access to the repository
- PyPI trusted publishing configured (see below)
- All tests passing on main branch

## PyPI Trusted Publishing Setup (One-time)

1. Go to <https://pypi.org/manage/account/publishing/>
2. Add a new publisher:
   - **PyPI Project Name**: `BiRRe`
   - **Owner**: `boecht`
   - **Repository name**: `birre`
   - **Workflow name**: `release.yml`
   - **Environment name**: `pypi`

This allows the GitHub Actions workflow to publish to PyPI without storing credentials.

## Release Steps

### 1. Update Version Number

Edit `pyproject.toml` and update the version:

```toml
[project]
name = "BiRRe"
version = "3.0.1"  # Update this
```

### 2. Update CHANGELOG.md

Add a new section for the release:

```markdown
## [3.0.1] - 2025-10-30

### Added
- New feature description

### Fixed
- Bug fix description

### Changed
- Breaking change description
```

### 3. Commit and Push

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "Bump version to 3.0.1"
git push origin main
```

### 4. Create and Push Tag

```bash
git tag v3.0.1
git push origin v3.0.1
```

The release workflow will automatically:
1. Run validation (lint, type check, tests)
2. Build source distribution and wheel
3. Create GitHub release with changelog
4. Publish to PyPI

### 5. Verify Release

Check:
- GitHub Releases: <https://github.com/boecht/birre/releases>
- PyPI: <https://pypi.org/project/birre/>
- Installation: `pip install birre==3.0.1`

## Manual Release (Fallback)

If the automated workflow fails, you can release manually:

```bash
# Build package
uv build

# Upload to PyPI (requires PyPI token)
uv publish

# Or use twine
pip install twine
twine upload dist/*
```

## Workflow Details

The release workflow (`.github/workflows/release.yml`) consists of four jobs:

1. **validate**: Runs linting, type checking, and tests
2. **build**: Creates distribution packages (tar.gz + wheel)
3. **github-release**: Creates GitHub release with changelog and artifacts
4. **pypi-publish**: Publishes to PyPI using trusted publishing

All jobs must pass for the release to complete successfully.

## Version Numbering

BiRRe follows [Semantic Versioning](https://semver.org/):

- **MAJOR.MINOR.PATCH** (e.g., 3.0.1)
- **MAJOR**: Breaking changes
- **MINOR**: New features (backwards compatible)
- **PATCH**: Bug fixes (backwards compatible)

## Troubleshooting

### Release workflow fails on validation

Fix the failing checks (lint/type/test) and push the fixes, then re-tag:

```bash
git tag -d v3.0.1
git push origin :refs/tags/v3.0.1
# Fix issues, commit, push
git tag v3.0.1
git push origin v3.0.1
```

### PyPI publishing fails

Check:
1. Trusted publishing is configured correctly on PyPI
2. Environment name is `pypi` in workflow and PyPI settings
3. Repository and owner match exactly

### Changelog not generated

Ensure `CHANGELOG.md` has a section matching the version:

```markdown
## [3.0.1] - YYYY-MM-DD
```

The workflow extracts this section for the GitHub release notes.
