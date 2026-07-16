"""PostToolUse lint and non-blocking minimum-change feedback for pipeline agents.

Reads VS Code hook JSON, runs Ruff on edited Python files, and warns about unusually broad edits.
"""

from __future__ import annotations

import json
import re
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
_PATCH_PATH_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+?)(?: -> .+)?$", re.MULTILINE)
_LARGE_CHURN_LINES = 200
_LARGE_DELETION_LINES = 80
_LARGE_DELETION_FRACTION = 0.4
_TEST_ADDITION_LINES = 100
_TEST_DOMINANCE_MULTIPLIER = 2
_WIDE_EDIT_FILES = 4
_MIN_NUMSTAT_FIELDS = 2


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

    if tool_name == "apply_patch":
        patch = tool_input.get("input")
        if isinstance(patch, str):
            for path in _PATCH_PATH_RE.findall(patch):
                _add(path)
    elif tool_name == "multi_replace_string_in_file":
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


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run a non-interactive git query without raising on repository state."""
    return subprocess.run(  # noqa: S603
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def _repository_root() -> Path | None:
    """Return the active Git root when the hook runs inside a repository."""
    result = _git(Path.cwd(), "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def _resolve_path(root: Path, raw_path: str) -> tuple[Path, str] | None:
    """Resolve a tool path inside the active repository."""
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve()
    try:
        relative = candidate.relative_to(root).as_posix()
    except ValueError:
        return None
    return candidate, relative


def _is_test_path(relative_path: str) -> bool:
    """Recognize common Python and JavaScript test locations and suffixes."""
    path = Path(relative_path)
    name = path.name.lower()
    return (
        any(part.lower() in {"test", "tests", "__tests__"} for part in path.parts)
        or name.startswith("test_")
        or name.endswith((".test.js", ".test.jsx", ".test.ts", ".test.tsx", ".spec.js", ".spec.ts"))
    )


def _change_stats(root: Path, path: Path, relative_path: str) -> tuple[int, int, int, bool]:
    """Return added, deleted, baseline lines, and whether the path exists in HEAD."""
    tracked = _git(root, "cat-file", "-e", f"HEAD:{relative_path}").returncode == 0
    if not tracked:
        try:
            return len(path.read_text(encoding="utf-8", errors="replace").splitlines()), 0, 0, False
        except OSError:
            return 0, 0, 0, False

    numstat = _git(root, "diff", "--numstat", "HEAD", "--", relative_path)
    added = deleted = 0
    if numstat.returncode == 0 and numstat.stdout.strip():
        fields = numstat.stdout.splitlines()[0].split("\t", 2)
        if len(fields) >= _MIN_NUMSTAT_FIELDS and fields[0].isdigit() and fields[1].isdigit():
            added, deleted = int(fields[0]), int(fields[1])

    baseline_result = _git(root, "show", f"HEAD:{relative_path}")
    baseline = len(baseline_result.stdout.splitlines()) if baseline_result.returncode == 0 else 0
    return added, deleted, baseline, True


def _minimum_change_warnings(candidate_paths: list[str], root: Path) -> list[str]:
    """Return non-blocking warnings for edits that deserve scope reassessment."""
    resolved = [item for raw in candidate_paths if (item := _resolve_path(root, raw)) and item[0].is_file()]
    if not resolved:
        return []

    warnings: list[str] = []
    test_added = product_added = 0
    if len(resolved) >= _WIDE_EDIT_FILES:
        warnings.append(f"wide edit touches {len(resolved)} files in one operation")

    for path, relative_path in resolved:
        added, deleted, baseline, tracked = _change_stats(root, path, relative_path)
        if _is_test_path(relative_path):
            test_added += added
            if not tracked:
                warnings.append(f"new test file: {relative_path}")
        else:
            product_added += added

        churn = added + deleted
        if (
            tracked
            and churn >= _LARGE_CHURN_LINES
            and deleted >= _LARGE_DELETION_LINES
            and baseline > 0
            and deleted / baseline >= _LARGE_DELETION_FRACTION
        ):
            warnings.append(f"large replacement in {relative_path} (+{added}/-{deleted})")

    if test_added >= _TEST_ADDITION_LINES and test_added > product_added * _TEST_DOMINANCE_MULTIPLIER:
        warnings.append(f"test-heavy edit adds {test_added} test lines versus {product_added} product lines")

    if warnings:
        warnings.append("recheck the change envelope and Rent Test; continue when the expansion is justified")
    return warnings


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

    root = _repository_root()
    warnings = _minimum_change_warnings(candidate_paths, root) if root else []

    # Filter: only existing .py files
    existing_py = [p for p in candidate_paths if p.endswith(".py") and Path(p).is_file()]
    messages = [f"Minimum-change warning: {warning}" for warning in warnings]
    if existing_py:
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
            result = None
        if result is not None and result.returncode == 1:
            messages.append((result.stdout + result.stderr).strip())

    if messages:
        output = "\n".join(messages)
        response = {
            "systemMessage": output,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": output,
            },
        }
        print(json.dumps(response))
    else:
        print("{}")


if __name__ == "__main__":
    main()
