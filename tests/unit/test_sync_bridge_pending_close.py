from __future__ import annotations

import asyncio
import contextlib

from birre.cli import sync_bridge


def test_close_loop_cancels_pending_and_resets() -> None:
    async def _leak_task() -> None:
        # background task that would remain pending until cancelled
        asyncio.create_task(asyncio.sleep(60))
        await asyncio.sleep(0)

    # Create loop and leak a task
    sync_bridge.await_sync(_leak_task())
    # Now close the loop explicitly; should cancel pending and null out global
    with contextlib.suppress(Exception):
        sync_bridge._close_sync_bridge_loop()  # type: ignore[attr-defined]

    # A fresh await should recreate a loop and succeed
    assert sync_bridge.await_sync(asyncio.sleep(0)) is None
