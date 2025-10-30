"""Async/sync bridge utilities for CLI commands.

Provides a simple utility to execute async code from synchronous CLI contexts.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")


def await_sync(coro: Awaitable[T]) -> T:
    """Execute an awaitable from synchronous code using asyncio.run().

    This is a simplified bridge that leverages Python 3.11+'s improved
    asyncio.run() implementation for proper cleanup and lifecycle management.

    Raises:
        RuntimeError: If called from within an already-running event loop.
    """
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if running_loop is not None:
        raise RuntimeError("await_sync cannot be used inside a running event loop")

    return asyncio.run(coro)  # type: ignore[arg-type]


def invoke_with_optional_run_sync(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Invoke *func*, binding :func:`await_sync` when it declares ``run_sync``."""
    kwargs = dict(kwargs)
    kwargs.pop("run_sync", None)
    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        params = {}  # type: ignore[assignment]
    if "run_sync" in params:
        return func(*args, run_sync=await_sync, **kwargs)
    return func(*args, **kwargs)


__all__ = [
    "await_sync",
    "invoke_with_optional_run_sync",
]
