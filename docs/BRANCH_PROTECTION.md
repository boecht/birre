# Branch Protection Configuration

**Repository**: boecht/birre
**Last Updated**: 2025-10-31
**Configured By**: Repository Owner

## Overview

This document records the GitHub branch protection ruleset configuration for the `main` branch.
These settings enforce code quality, security, and collaborative review standards before changes
can be merged.

## Ruleset: "default branches protection"

- **Status**: Active
- **Enforcement**: Enabled
- **Target**: `main` branch (default branch)
- **Bypass List**: Empty (no exceptions)

## Branch Rules

### Deletion Protection

✅ **Restrict deletions** - Enabled
Only users with bypass permission can delete matching refs.

### Update Restrictions

⬜ **Restrict updates** - Disabled
⬜ **Restrict creations** - Disabled

### History Requirements

⬜ **Require linear history** - Disabled
Merge commits are allowed.

## Pull Request Requirements

### PR Mandatory

✅ **Require a pull request before merging** - Enabled
All commits must be made to a non-target branch and submitted via PR.

#### Additional PR Settings

- **Required approvals**: 0 (trust-based for personal project)
- ✅ **Dismiss stale approvals when new commits are pushed**
- ⬜ **Require review from Code Owners** - Disabled
- ⬜ **Require approval of most recent reviewable push** - Disabled
- ✅ **Require conversation resolution before merging**
- ✅ **Automatically request Copilot code review**

### Merge Method Restrictions

**Allowed methods**: Merge, Squash, Rebase
All merge strategies permitted.

## Status Check Requirements

✅ **Require status checks to pass** - Enabled
Commits must first be pushed to another ref where the checks pass.

### Additional Status Check Settings

✅ **Require branches to be up to date before merging**
PRs must be tested with latest code before merging.

✅ **Do not require status checks on creation**
Allow repositories and branches to be created even if checks would prohibit it.

### Required Status Checks

The following CI/CD checks must pass before merging:

1. **Code Quality & Tests** (GitHub Actions)
    - Source: `.github/workflows/pr-validation.yml`
    - Validates: Linting, formatting, type checking, offline tests

2. **CodeQL** (GitHub Advanced Security)
    - Automated code scanning for security vulnerabilities

3. **SonarCloud Code Analysis** (SonarQubeCloud)
    - Code quality and security analysis

4. **dependency-review** (GitHub Actions)
    - Dependency vulnerability scanning

5. **Dependabot** (GitHub Actions)
    - Automated dependency updates validation

6. **codecov/patch** (Codecov)
    - Code coverage for changed code

## Additional Protections

### Force Push Protection

✅ **Block force pushes** - Enabled
Prevents users with push access from force pushing to refs.

### Code Scanning Requirements

✅ **Require code scanning results** - Enabled
Code scanning must be enabled and have results for both commit and reference.

#### Required Tools and Thresholds

- **CodeQL** (GitHub Advanced Security)
  - Security alerts: High or higher
  - Alert threshold: Errors

### Code Quality Requirements

✅ **Require code quality results** - Enabled
Code quality analysis must be done on PR before changes can be merged.

#### Quality Standards

- **Severity**: Errors
- Lowest severity level at which code quality reviews must be resolved.

### Copilot Integration

✅ **Automatically request Copilot code review** (2 instances)

- ✅ Review new pushes
- ✅ Review draft pull requests

## Compliance & Certification Value

This configuration supports the following compliance frameworks and best practices:

### OpenSSF Best Practices

- ✅ **Required status checks**: Enforces automated testing and quality gates
- ✅ **Branch protection**: Prevents direct commits to main branch
- ✅ **Code review**: Requires pull requests (though approvals not required for solo maintainer)
- ✅ **Automated security scanning**: CodeQL and dependency reviews

### SLSA Supply Chain Security

- ✅ **No direct commits**: All changes via PR workflow
- ✅ **Automated testing**: CI/CD validates every change
- ✅ **Security scanning**: Multiple automated security tools
- ✅ **Provenance**: PR history provides change provenance

### Security Scanning Coverage

- **Static Analysis**: CodeQL (GitHub), SonarCloud
- **Dependency Security**: Dependabot, dependency-review
- **Code Quality**: SonarCloud, CodeQL
- **Test Coverage**: CodeCov (patch and project coverage)

### Development Best Practices

- ✅ **Conversation resolution**: Ensures all review comments addressed
- ✅ **Up-to-date branches**: Prevents integration issues
- ✅ **Multiple merge strategies**: Flexibility for different scenarios
- ✅ **AI-assisted reviews**: Copilot code review for automated feedback

## Rationale for Configuration Choices

### Why 0 Required Approvals?

This is a personal project with a single maintainer. The value comes from:

- Automated testing (offline suite)
- Automated security scanning (CodeQL, SonarCloud)
- Automated quality checks (code coverage, linting, type checking)
- AI-assisted review (GitHub Copilot)
- Self-review discipline via PR workflow

For team projects, recommend setting to 1+ approvals.

### Why Allow All Merge Methods?

Different merge strategies serve different purposes:

- **Merge commits**: Preserve full history and context
- **Squash**: Clean history for feature branches
- **Rebase**: Linear history when appropriate

Maintainer can choose appropriate strategy per PR.

### Why Multiple Security Scanners?

Defense in depth - different tools catch different issues:

- **CodeQL**: Excellent for security vulnerabilities
- **SonarCloud**: Strong on code quality and maintainability
- **Dependabot**: Automated dependency updates
- **dependency-review**: Prevents introducing vulnerable dependencies

## Maintenance

Review and update this configuration:

- **When adding new workflows**: Add to required status checks
- **When changing security requirements**: Update scanning thresholds
- **When team grows**: Increase required approvals
- **Quarterly**: Review effectiveness of current settings

## References

- [GitHub Branch Protection Documentation](
  https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets)
- [OpenSSF Best Practices Badge Criteria](https://www.bestpractices.dev/en/criteria)
- [SLSA Framework](https://slsa.dev/)
- CI/CD Configuration: `.github/workflows/pr-validation.yml`
- Setup completed: 2025-10-31
