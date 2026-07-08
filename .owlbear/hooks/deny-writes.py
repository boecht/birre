"""deny-writes.py — PreToolUse hook for read-only agents with scratch access.

Reads VS Code hook stdin JSON, allows writes only under `.owlbear/scratch/`,
and denies all other write targets. Usage: invoked automatically by VS Code as
a PreToolUse hook.
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

_SCRATCH_RE = re.compile(r"(^|/)\.owlbear/scratch(/|$)")


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

    patch_input = tool_input.get("input")
    if isinstance(patch_input, str):
        for line in patch_input.splitlines():
            if line.startswith(
                ("*** Update File: ", "*** Add File: ", "*** Delete File: ")
            ):
                path = line.split(": ", 1)[1].strip()
                if path:
                    paths.append(path)

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


def _is_scratch_path(normalized: str) -> bool:
    return _SCRATCH_RE.search(normalized) is not None


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

    for path in paths:
        normalized = _normalize(path)
        if not _is_scratch_path(normalized):
            response = {
                "hookSpecificOutput": {
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"read-only path guard: write to '{normalized}' is denied. "
                        "Only .owlbear/scratch/ is writable for this agent."
                    ),
                }
            }
            print(json.dumps(response))
            return

    print("{}")


if __name__ == "__main__":
    main()
