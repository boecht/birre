"""Developer command shortcuts for local quality checks."""

from __future__ import annotations

import subprocess
import sys

LINT_HINT = """
Dev commands:
  uv run lint       default pre-commit hooks, staged files only
  uv run lint-all   default pre-commit hooks, all files
  uv run megalint   manual MegaLinter hook, all files
  uv run pytest     Python tests
""".strip()


def _run_pre_commit(args: list[str]) -> None:
    try:
        return_code = subprocess.call(["pre-commit", *args])
    except FileNotFoundError:
        sys.stderr.write("pre-commit is not installed. Run `uv sync --group dev` and retry.\n")
        return_code = 127

    sys.stderr.write(f"\n{LINT_HINT}\n")
    raise SystemExit(return_code)


def lint() -> None:
    """Run default pre-commit hooks against staged files."""
    _run_pre_commit(["run"])


def lint_all() -> None:
    """Run default pre-commit hooks against all files."""
    _run_pre_commit(["run", "--all-files"])


def megalint() -> None:
    """Run the manual MegaLinter hook against all files."""
    _run_pre_commit(["run", "megalinter", "--all-files", "--hook-stage", "manual"])
