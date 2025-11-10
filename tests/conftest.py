from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("birre")
    group.addoption(
        "--offline",
        action="store_true",
        dest="birre_offline",
        help="Run offline tests only (deselect tests marked 'online').",
    )
    group.addoption(
        "--online-only",
        action="store_true",
        dest="birre_online_only",
        help="Run only tests marked 'online' (deselect offline).",
    )


def _is_integration_path(s: str) -> bool:
    s = s.replace("\\", "/")
    return s.startswith("tests/integration/") or "/tests/integration/" in s


def _mark_by_path(items: list[pytest.Item]) -> None:
    for item in items:
        node_str = str(getattr(item, "fspath", item.nodeid))
        marker = (
            pytest.mark.online
            if _is_integration_path(node_str)
            else pytest.mark.offline
        )
        item.add_marker(marker)


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    _mark_by_path(items)

    offline_only = bool(config.getoption("birre_offline"))
    online_only = bool(config.getoption("birre_online_only"))

    if offline_only and online_only:
        raise pytest.UsageError("--offline and --online-only are mutually exclusive")

    deselect: list[pytest.Item] = []
    if online_only:
        deselect = [i for i in items if "online" not in i.keywords]
    elif offline_only:
        deselect = [i for i in items if "online" in i.keywords]

    if not deselect:
        return

    config.hook.pytest_deselected(items=deselect)
    items[:] = [i for i in items if i not in deselect]
