# Contributing to BiRRe

Thank you for your interest in contributing to BiRRe! This document provides guidelines and
instructions for contributing.

## Code of Conduct

This project adheres to the Contributor Covenant [Code of Conduct](CODE_OF_CONDUCT.md).
By participating, you are expected to uphold this code.

## Getting Started

### Prerequisites

- Python 3.13 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- Git
- A BitSight API key for integration testing (optional)

### Development Setup

1. **Fork and clone the repository**

   ```bash
   git clone https://github.com/boecht/birre.git
   cd birre
   ```

2. **Install dependencies**

   ```bash
   uv sync --all-extras
   ```

   This will automatically download Python 3.13 if not already installed.

3. **Install pre-commit hooks** (after `uv sync`)

   ```bash
   pre-commit install
   ```

   The hooks use `uv run` to ensure they execute with the correct Python version
   and project dependencies.

4. **Set up environment variables** (optional, for online tests)

   ```bash
   export BITSIGHT_API_KEY="your-api-key"
   ```

5. **Run tests to verify setup**

   ```bash
   uv run pytest --offline
   ```

## Development Workflow

### Branch Strategy

- `main` - Production-ready code
- `dev/*` - Development branches for features/fixes
- `release/*` - Release preparation branches

### Making Changes

1. **Create a feature branch**

   ```bash
   git checkout -b dev/your-feature-name
   ```

2. **Make your changes**

   - Write clear, concise code
   - Follow existing code style
   - Add tests for new functionality
   - Update documentation as needed

3. **Run quality checks**

   ```bash
   # Lint
   uv run ruff check src tests

   # Format
   uv run ruff format src tests

   # Type check
   uv run mypy src

   # Test
   uv run pytest --offline --cov=src/birre
   ```

4. **Commit your changes**

   ```bash
   git add .
   git commit -m "Brief description of changes"
   ```

   Use clear, descriptive commit messages. See [Commit Message Guidelines](#commit-message-guidelines).

5. **Push and create a pull request**

   ```bash
   git push origin dev/your-feature-name
   ```

   Then create a pull request on GitHub.

## Coding Standards

### Style Guide

BiRRe follows these coding standards:

- **PEP 8** for Python code style
- **Type hints** for all functions and methods
- **Docstrings** for all public APIs (Google style)
- **Line length**: Maximum 100 characters
- **Import sorting**: Managed by ruff/isort

Authoring note: LLMs creating or editing Python files in `src/` should also consult the
[Python Style Instructions](.github/instructions/edit-python.instructions.md) for
file-scoped guidance during code changes.

### Code Quality Tools

- **Ruff**: Linting and formatting (replaces black, isort, flake8)
- **mypy**: Static type checking with strict mode
- **pytest**: Testing framework with coverage reporting

### Testing

Project setup (`uv sync`) takes care of dependencies, such as the correct python version, and fastmcp.
A BitSight API key is expected via either `BITSIGHT_API_KEY` or `config.local.toml` under `[bitsight].api_key`.
With either configured, it is safe to run online tests.

- **Write tests** for all new features and bug fixes
- **Offline tests** (pytest marker: `@pytest.mark.offline`) for unit tests
- **Online tests** (pytest marker: `@pytest.mark.online`) for integration tests requiring API access
- **Maintain coverage**: Aim for 70%+ coverage for new code

Run tests:

```bash
# Full suite (recommended; online tests skip automatically if no API key)
uv run pytest

# Specific test file
uv run pytest tests/unit/test_your_feature.py

# Offline only / online only convenience flags
uv run pytest --offline
uv run pytest --online-only

# With coverage (full suite)
uv run pytest --cov=src/birre --cov-branch --cov-report=term

# All online tests (network; assumes API key available)
uv run pytest --online-only
```

## Commit Message Guidelines

Use clear, descriptive commit messages:

```text
Brief summary (50 chars or less)

More detailed explanation if needed (wrap at 72 chars).
- Bullet points are okay
- Use present tense ("Add feature" not "Added feature")
- Reference issues: "Fixes #123" or "Relates to #456"
```

### Commit Scope

**One topic per commit** - Group related changes together, but don't mix unrelated topics:

- ✅ **Good**: "Fix Python 3.13 compatibility across all workflows"
  - Multiple files, one coherent topic (Python 3.13 migration)
- ✅ **Good**: "Refactor config module to reduce complexity (TD-002)"
  - Focused refactoring with clear purpose
- ❌ **Bad**: "Fix tests, update docs, refactor config, add caching"
  - Multiple unrelated topics that should be separate commits

**Guideline**: Changes should be cohesive enough to describe in a single commit message,
but comprehensive enough to be meaningful. Avoid both:

- Over-atomization (100 tiny commits for one feature)
- Kitchen-sink commits (unrelated changes bundled together)

## Pull Request Process

1. **Ensure all checks pass**
   - Linting (ruff)
   - Type checking (mypy)
   - Tests (pytest)
   - Coverage (70%+ minimum)

2. **Update documentation**
   - README.md if user-facing changes
   - Docstrings for new APIs
   - CHANGELOG.md with your changes

3. **Fill out the PR template**
   - Describe what changed and why
   - Reference related issues
   - Note any breaking changes

4. **Request review**
   - Wait for maintainer feedback
   - Address review comments
   - Keep the PR focused and atomic

5. **Squash commits** (if requested)
   - Maintainers may squash commits on merge
   - Or you can squash locally before merging

## Project Structure

```text
birre/
├── src/birre/           # Source code
│   ├── application/     # MCP server application layer
│   ├── cli/             # Command-line interface
│   ├── config/          # Configuration management
│   ├── domain/          # Business logic (rating, search, risk manager)
│   ├── infrastructure/  # Cross-cutting concerns (logging, errors)
│   ├── integrations/    # External API clients (BitSight)
│   └── resources/       # Static resources (API specs)
├── tests/               # Test suite
│   ├── unit/            # Unit tests (offline)
│   └── integration/     # Integration tests (online)
├── docs/                # Documentation
└── .github/             # GitHub Actions workflows
```

## Architecture

BiRRe follows a layered architecture:

1. **CLI Layer** (`cli/`) - User interface and command handling
2. **Application Layer** (`application/`) - MCP server and startup logic
3. **Domain Layer** (`domain/`) - Business logic and services
4. **Infrastructure Layer** (`infrastructure/`, `integrations/`) - External dependencies

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

## Areas for Contribution

We welcome contributions in these areas:

- **Bug fixes**: Check [issues labeled "bug"](https://github.com/boecht/birre/labels/bug)
- **Documentation**: Improve guides, fix typos, add examples
- **Tests**: Expand test coverage, add edge cases
- **Features**: Check [issues labeled "enhancement"](https://github.com/boecht/birre/labels/enhancement)
- **Performance**: Optimize slow operations
- **Security**: Report vulnerabilities responsibly

## Reporting Issues

### Bug Reports

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md):

- Clear title describing the problem
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version)
- Error messages and logs

### Feature Requests

Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md):

- Clear description of the feature
- Use case and motivation
- Proposed implementation (if any)
- Alternatives considered

### Security Issues

See [SECURITY.md](SECURITY.md) for responsible disclosure.

## Getting Help

- **Documentation**: Check [docs/](docs/) and README.md
- **Issues**: Search existing issues or create a new one
- **Discussions**: Use GitHub Discussions for questions

## License

By contributing to BiRRe, you agree that your contributions will be licensed under
the [Unlicense](LICENSE) (public domain).

## Recognition

Contributors will be recognized in:

- Git commit history
- GitHub contributors page
- Release notes (for significant contributions)

Thank you for making BiRRe better! 🎉
