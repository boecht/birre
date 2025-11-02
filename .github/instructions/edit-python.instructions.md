---
applyTo: 'src/**/*.py'
---
When creating or editing Python code in `src/`:

- Style and versions
  - Target Python 3.13 features and syntax.
  - Max line length: 100.

- Types and docs
  - Add type hints for all functions and public methods.
  - Use Google-style docstrings for public APIs; keep private helpers concise.

- Imports and linting
  - Keep imports sorted and grouped (ruff/isort rules).
  - Keep the code ruff-clean; prefer `pyupgrade` idioms.

- Comments
  - Explain the "why" for non-obvious behavior and edge cases.
  - Avoid commented-out code and narrating the obvious.

- Cohesion
  - One responsibility per function; prefer small, testable units.
  - Keep business logic in the appropriate layer/module.

Reference: [CONTRIBUTING.md](../../CONTRIBUTING.md) (Coding Standards) and [copilot-instructions.md](../copilot-instructions.md) (Documentation Principles)
