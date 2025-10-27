from __future__ import annotations

from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SRC_ROOT = _REPO_ROOT / "src"
if _SRC_ROOT.exists() and str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

import pytest

_TESTS_ROOT = Path(__file__).parent.resolve()
_UNIT_ROOT = _TESTS_ROOT / "unit"
_INTEGRATION_ROOT = _TESTS_ROOT / "integration"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-tag tests from the unit and integration trees with the right markers."""

    for item in items:
        path = Path(item.fspath).resolve()
        if _UNIT_ROOT in path.parents:
            item.add_marker("unit")
            item.add_marker("offline")
        elif _INTEGRATION_ROOT in path.parents:
            item.add_marker("integration")
            item.add_marker("online")
