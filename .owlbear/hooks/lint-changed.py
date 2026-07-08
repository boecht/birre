"""lint-changed.py — PostToolUse hook for the builder agent.

Reads VS Code hooks stdin JSON, runs ruff on edited .py files, reports lint errors.
Usage: invoked automatically by VS Code as a PostToolUse hook.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_EDIT_TOOLS = {
    "create_file",
    "replace_string_in_file",
    "multi_replace_string_in_file",
    "apply_patch",
    "editFiles",
}


def _extract_paths(tool_name: str, tool_input: object) -> list[str]:
    """Extract file paths from tool_input based on tool_name."""
    if not isinstance(tool_input, dict):
        return []

    seen: set[str] = set()
    paths: list[str] = []

    def _add(path: str | None) -> None:
        if path and isinstance(path, str):
            key = path.lower()
            if key not in seen:
                seen.add(key)
                paths.append(path)

    if tool_name == "multi_replace_string_in_file":
        for replacement in tool_input.get("replacements") or []:
            if isinstance(replacement, dict):
                _add(replacement.get("filePath"))
    elif tool_name == "editFiles":
        for entry in tool_input.get("files") or []:
            if isinstance(entry, str):
                _add(entry)
    else:
        _add(tool_input.get("filePath"))

    return paths


def main() -> None:
    raw = sys.stdin.buffer.read()
    # Strip UTF-8 BOM if present
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]

    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, ValueError):
        print("{}")
        return

    if not isinstance(payload, dict):
        print("{}")
        return

    tool_name = payload.get("tool_name", "")
    if not tool_name or tool_name not in _EDIT_TOOLS:
        print("{}")
        return

    tool_input = payload.get("tool_input")
    try:
        candidate_paths = _extract_paths(tool_name, tool_input)
    except Exception:  # noqa: BLE001
        print("{}")
        return

    # Filter: only existing .py files
    existing_py = [
        p for p in candidate_paths if p.endswith(".py") and Path(p).is_file()
    ]
    if not existing_py:
        print("{}")
        return

    try:
        result = subprocess.run(  # noqa: S603
            [
                "uv",
                "run",
                "--quiet",
                "ruff",
                "check",
                "--ignore",
                "INP001",
                *existing_py,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:  # noqa: BLE001
        print("{}")
        return

    if result.returncode == 1:
        ruff_output = (result.stdout + result.stderr).strip()
        response = {
            "systemMessage": ruff_output,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": ruff_output,
            },
        }
        print(json.dumps(response))
    else:
        print("{}")


if __name__ == "__main__":
    main()
