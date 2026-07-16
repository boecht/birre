"""session-context.py — SessionStart hook for pipeline agents.

Reads stdin JSON, runs git branch/log, outputs SessionStart additionalContext.
Returns {} on any failure (non-blocking, fail-open).
Usage: invoked automatically by VS Code as a SessionStart hook.
"""

from __future__ import annotations

import json
import subprocess
import sys


def main() -> None:  # noqa: PLR0911
    """Inject git branch and recent commits into the session context."""
    # Read stdin as bytes — handles binary/non-UTF-8 input gracefully
    try:
        raw = sys.stdin.buffer.read()
        stdin_text = raw.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        print("{}")
        return

    # Return {} on empty stdin
    if not stdin_text.strip():
        print("{}")
        return

    # Return {} on malformed JSON (includes BOM-prefixed input)
    try:
        json.loads(stdin_text)
    except (json.JSONDecodeError, ValueError):
        print("{}")
        return

    # Get current branch — return {} if git unavailable or not in a repo
    try:
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print("{}")
        return

    if branch_result.returncode != 0:
        print("{}")
        return

    branch = branch_result.stdout.strip() or "HEAD"

    # Get recent commits — return {} on git failure
    try:
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-3", "--no-decorate"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print("{}")
        return

    if log_result.returncode != 0:
        print("{}")
        return

    commit_lines = [line.strip() for line in log_result.stdout.splitlines() if line.strip()]
    commits_str = " | ".join(commit_lines)

    additional_context = f"Branch: {branch} | Commits: {commits_str}"

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": additional_context,
        }
    }

    print(json.dumps(output))


if __name__ == "__main__":
    main()
