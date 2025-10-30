"""Async/sync bridge utilities for CLI commands.

Provides utilities to execute async code from synchronous CLI contexts
using a reusable event loop.
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

_SYNC_BRIDGE_LOOP: asyncio.AbstractEventLoop | None = None
_SYNC_BRIDGE_LOCK = threading.Lock()
_loop_logger = logging.getLogger("birre.loop")


def close_sync_bridge_loop() -> None:
    """Dispose of the shared event loop used by :func:`await_sync`."""

    global _SYNC_BRIDGE_LOOP
    loop = _SYNC_BRIDGE_LOOP
    if loop is None:
        return
    if loop.is_closed():
        _SYNC_BRIDGE_LOOP = None
        return

    for handler in _loop_logger.handlers:
        stream = getattr(handler, "stream", None)
        if stream is not None and getattr(stream, "closed", False):
            continue
        _loop_logger.debug("sync_bridge.loop_close")
        break

    pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
    for task in pending:
        task.cancel()
    with suppress(Exception):
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    loop.close()
    _SYNC_BRIDGE_LOOP = None


atexit.register(close_sync_bridge_loop)


def await_sync(coro: Awaitable[Any]) -> Any:
    """Execute an awaitable from synchronous code on a reusable loop."""

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
            _loop_logger.debug("sync_bridge.loop_created")

        loop = _SYNC_BRIDGE_LOOP
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(coro)
        finally:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            if pending:
                for task in pending:
                    task.cancel()
                with suppress(Exception):
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            asyncio.set_event_loop(None)
        return result


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
    "close_sync_bridge_loop",
    "invoke_with_optional_run_sync",
]
