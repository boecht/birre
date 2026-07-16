"""allow-stances-only.py — PreToolUse hook for ideation domain panelists.

Allow-list path guard: permits writes ONLY to stances/ directories.
Reads VS Code hook stdin JSON, checks paths for write tools, denies writes outside stances/.
Usage: invoked automatically by VS Code as a PreToolUse hook.

Allowed paths:
  */stances/*  — panelist stance output files (architect.md, data.md, etc.)

Denied:
  Everything else — panelists must not write outside their stances/ scope.
"""

from __future__ import annotations

import json
import re
import sys

_WRITE_TOOLS = {
    "create_file",
    "replace_string_in_file",
    "multi_replace_string_in_file",
    "apply_patch",
    "create_directory",
    "editFiles",
}

_STANCES_RE = re.compile(r"(/|^)stances/")


def _extract_paths(tool_input: object) -> list[str]:
    if not isinstance(tool_input, dict):
        return []
    paths: list[str] = []

    fp = tool_input.get("filePath")
    if isinstance(fp, str) and fp:
        paths.append(fp)

    dp = tool_input.get("dirPath")
    if isinstance(dp, str) and dp:
        paths.append(dp)

    for r in tool_input.get("replacements") or []:
        if isinstance(r, dict):
            rfp = r.get("filePath")
            if isinstance(rfp, str) and rfp:
                paths.append(rfp)

    for f in tool_input.get("files") or []:
        if isinstance(f, str) and f:
            paths.append(f)
        elif isinstance(f, dict):
            efp = f.get("filePath")
            if isinstance(efp, str) and efp:
                paths.append(efp)

    return paths


def _normalize(path: str) -> str:
    return path.replace("\\", "/").removeprefix("./")


def main() -> None:
    raw = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, ValueError):
        print("{}")
        return

    tool_name = payload.get("tool_name", "")
    if not tool_name or tool_name not in _WRITE_TOOLS:
        print("{}")
        return

    paths = _extract_paths(payload.get("tool_input"))
    if not paths:
        print("{}")
        return

    for p in paths:
        normalized = _normalize(p)
        if not _STANCES_RE.search(normalized):
            response = {
                "hookSpecificOutput": {
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"ideation panelist path guard: write target '{normalized}' "
                        "is outside the allowed stances/ directory. Domain panelists "
                        "may only write to stances/ within the brief working directory."
                    ),
                }
            }
            print(json.dumps(response))
            return

    print("{}")


if __name__ == "__main__":
    main()
