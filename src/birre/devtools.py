"""Developer command shortcuts for local quality checks."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

LINT_HINT = (
    "\n"
    "\033[1;34mDev commands:\033[0m\n"
    "  \033[32muv run lint\033[0m       default pre-commit hooks, staged files only\n"
    "  \033[32muv run lint-all\033[0m   same as \033[32mlint\033[0m, all files\n"
    "  \033[32muv run megalint\033[0m   same as \033[32mlint-all\033[0m + MegaLinter\n"
    "  \033[32muv run todo\033[0m       scan for TODO markers (warning only)\n"
    "  \033[32muv run pytest\033[0m     Python tests\n"
)

_TODO_RE = re.compile(r"^> \*\*TODO:\*\*", re.MULTILINE)
_TODO_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "megalinter-reports",
        "node_modules",
    }
)


def _run_pre_commit(args: list[str]) -> int:
    try:
        return subprocess.call(["pre-commit", *args])
    except FileNotFoundError:
        sys.stderr.write("pre-commit is not installed. Run `uv sync --group dev` and retry.\n")

        return 127


def _exit_with_hint(return_code: int) -> None:
    sys.stderr.write(f"\n{LINT_HINT}\n")
    raise SystemExit(return_code)


def lint() -> None:
    """Run default pre-commit hooks against staged files."""
    _exit_with_hint(_run_pre_commit(["run"]))


def lint_all() -> None:
    """Run default pre-commit hooks against all files."""
    _exit_with_hint(_run_pre_commit(["run", "--all-files"]))


def megalint() -> None:
    """Run full default linting followed by the manual MegaLinter hook."""
    return_code = _run_pre_commit(["run", "--all-files"])
    if return_code:
        _exit_with_hint(return_code)
    _exit_with_hint(_run_pre_commit(["run", "megalinter", "--all-files", "--hook-stage", "manual"]))


def todo_check() -> None:
    """Report TODO markers without failing the command."""
    hits: list[str] = []
    _walk_todo(Path("."), hits)
    if hits:
        print(f"\033[1;33m{len(hits)} TODO marker(s):\033[0m")  # noqa: T201
        for hit in hits:
            print(f"  {hit}")  # noqa: T201
    else:
        print("\033[32mNo TODO markers found\033[0m")  # noqa: T201
    if not os.environ.get("PRE_COMMIT"):
        sys.stderr.write(f"{LINT_HINT}\n")


def _walk_todo(root: Path, hits: list[str]) -> None:
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in _TODO_SKIP_DIRS]
        for filename in filenames:
            _scan_todo(Path(directory) / filename, hits)


def _scan_todo(path: Path, hits: list[str]) -> None:
    try:
        with path.open(encoding="utf-8", errors="replace") as file:
            for line_number, line in enumerate(file, start=1):
                if _TODO_RE.search(line):
                    hits.append(f"{path}:{line_number}: {line.rstrip()}")
    except OSError:
        pass
