"""Async/sync bridge utilities for CLI commands.

Provides a simple utility to execute async code from synchronous CLI contexts.
"""

from __future__ import annotations

import asyncio
import atexit
import inspect
import logging
import threading
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

_loop_logger = logging.getLogger("birre.loop")
_SYNC_BRIDGE_LOOP: asyncio.AbstractEventLoop | None = None
_SYNC_BRIDGE_LOCK = threading.Lock()


def _close_sync_bridge_loop() -> None:
    """Best-effort shutdown for the shared synchronous event loop."""
    global _SYNC_BRIDGE_LOOP
    loop = _SYNC_BRIDGE_LOOP
    if loop is None or loop.is_closed():
        return
    # Note: Don't log here as logging may already be shutdown at atexit time
    pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
    for task in pending:
        task.cancel()
    with suppress(Exception):
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    loop.close()
    _SYNC_BRIDGE_LOOP = None


atexit.register(_close_sync_bridge_loop)


def await_sync[T](coro: Awaitable[T]) -> T:
    """Execute an awaitable from sync code using a reusable event loop.

    The loop lives for the process lifetime, is guarded by a lock to prevent
    concurrent access, and cleans up any pending tasks before returning.

    Raises:
        RuntimeError: If called from within an already-running event loop.
    """
    global _SYNC_BRIDGE_LOOP

    with _SYNC_BRIDGE_LOCK:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is not None:
            raise RuntimeError("await_sync cannot be used inside a running event loop")

        if _SYNC_BRIDGE_LOOP is None or _SYNC_BRIDGE_LOOP.is_closed():
            _SYNC_BRIDGE_LOOP = asyncio.new_event_loop()
            asyncio.set_event_loop(_SYNC_BRIDGE_LOOP)

        try:
            result = _SYNC_BRIDGE_LOOP.run_until_complete(coro)
        finally:
            # Clean up pending tasks but keep the loop alive for reuse
            pending = [
                task for task in asyncio.all_tasks(_SYNC_BRIDGE_LOOP) if not task.done()
            ]
            if pending:
                for task in pending:
                    task.cancel()
                with suppress(Exception):
                    _SYNC_BRIDGE_LOOP.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )

        return result


def invoke_with_optional_run_sync(
    func: Callable[..., Any], *args: Any, **kwargs: Any
) -> Any:
    """Invoke *func*, binding :func:`await_sync` when it declares ``run_sync``."""
    kwargs = dict(kwargs)
    kwargs.pop("run_sync", None)
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return func(*args, **kwargs)
    if "run_sync" in signature.parameters:
        return func(*args, run_sync=await_sync, **kwargs)
    return func(*args, **kwargs)


__all__ = [
    "await_sync",
    "invoke_with_optional_run_sync",
]
