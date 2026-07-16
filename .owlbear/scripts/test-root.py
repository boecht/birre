"""Discover the test root (cwd + toolchain) for a given test file path.

Walks up from the test file toward the workspace root, looking for package
manifests that indicate which toolchain to use and where to run from.

Usage:
    uv run .owlbear/scripts/test-root.py <test_path> [<test_path> ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def find_test_root(test_path: str) -> dict[str, str]:
    """Resolve the test root for a given test file path.

    Returns a dict with keys: test_path, cwd, toolchain, cmd.
    """
    path = Path(test_path).resolve()
    start = path.parent if path.is_file() else path

    current = start
    workspace_root = Path.cwd()

    while current >= workspace_root:
        package_json = current / "package.json"
        if package_json.is_file():
            content = package_json.read_text(encoding="utf-8")
            try:
                pkg = json.loads(content)
            except json.JSONDecodeError:
                pass
            else:
                scripts = pkg.get("scripts", {})
                dev_deps = pkg.get("devDependencies", {})
                deps = pkg.get("dependencies", {})
                has_vitest = "vitest" in dev_deps or "vitest" in deps or any("vitest" in v for v in scripts.values())
                if has_vitest or "test" in scripts:
                    rel_cwd = current.relative_to(workspace_root)
                    return {
                        "test_path": test_path,
                        "cwd": str(rel_cwd) if rel_cwd != Path(".") else ".",
                        "toolchain": "vitest",
                        "cmd": "npm test",
                    }

        if current == workspace_root:
            break
        current = current.parent

    return {
        "test_path": test_path,
        "cwd": ".",
        "toolchain": "pytest",
        "cmd": "uv run pytest",
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: uv run .owlbear/scripts/test-root.py <path> [<path> ...]",
            file=sys.stderr,
        )
        sys.exit(1)

    results = [find_test_root(p) for p in sys.argv[1:]]
    if len(results) == 1:
        print(json.dumps(results[0], indent=2))
    else:
        print(json.dumps(results, indent=2))
