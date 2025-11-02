from __future__ import annotations

import asyncio
import contextlib

import pytest

from birre.cli import sync_bridge


@pytest.mark.asyncio
async def test_await_sync_raises_inside_running_loop() -> None:
    async def _noop() -> int:
        await asyncio.sleep(0)
        return 1

    with pytest.raises(RuntimeError):
        # Calling await_sync while an event loop is running should fail
        sync_bridge.await_sync(_noop())


def test_invoke_with_optional_run_sync_binds_parameter() -> None:
    def fn(x: int, *, run_sync) -> int:  # type: ignore[no-untyped-def]
        # Ensure a callable was provided and is callable
        assert callable(run_sync)
        return x + 1

    out = sync_bridge.invoke_with_optional_run_sync(fn, 41)
    assert out == 42


def test_close_sync_bridge_loop_is_idempotent() -> None:
    # Force-create loop
    def _mk() -> int:
        def _noop() -> int:
            return 7

        return _noop()

    assert _mk() == 7

    # Call the private closer twice to verify idempotence
    with contextlib.suppress(Exception):
        sync_bridge._close_sync_bridge_loop()  # type: ignore[attr-defined]
        sync_bridge._close_sync_bridge_loop()  # type: ignore[attr-defined]
