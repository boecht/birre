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


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    run_offline_only = bool(config.getoption("birre_offline"))
    run_online_only = bool(config.getoption("birre_online_only"))

    if run_offline_only and run_online_only:
        # Command line misuse; prefer explicit error
        raise pytest.UsageError("--offline and --online-only are mutually exclusive")

    if run_online_only:
        deselect = [item for item in items if "online" not in item.keywords]
    elif run_offline_only:
        deselect = [item for item in items if "online" in item.keywords]
    else:
        # Default: run all collected tests; online tests will self-skip if API key/dep missing
        deselect = []

    if deselect:
        config.hook.pytest_deselected(items=deselect)
        items[:] = [item for item in items if item not in deselect]
