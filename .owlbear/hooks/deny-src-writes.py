"""deny-src-writes.py — PreToolUse hook for test-only roles.

Allow-list path guard: only writes to `tests/`, `__tests__/`, `e2e/`, or
`.owlbear/scratch/` are permitted. Reads VS Code hook stdin JSON, checks paths
for write tools, denies writes outside those surfaces. Usage: invoked
automatically by VS Code as a PreToolUse hook.
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

_TESTS_RE = re.compile(r"(^|/)tests/")
_DUNDER_TESTS_RE = re.compile(r"(^|/)__tests__/")
_E2E_RE = re.compile(r"(^|/)e2e/")
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
            if line.startswith(("*** Update File: ", "*** Add File: ", "*** Delete File: ")):
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
        normalized = p.replace("\\", "/").removeprefix("./")
        if not (
            _TESTS_RE.search(normalized)
            or _DUNDER_TESTS_RE.search(normalized)
            or _E2E_RE.search(normalized)
            or _SCRATCH_RE.search(normalized)
        ):
            response = {
                "hookSpecificOutput": {
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"test-writer path guard: write target "
                        f"'{normalized}' is outside the allowed "
                        "directories. Only writes to tests/, __tests__/, e2e/, "
                        "or .owlbear/scratch/ are permitted."
                    ),
                }
            }
            print(json.dumps(response))
            return

    print("{}")


if __name__ == "__main__":
    main()
