import asyncio
import warnings

import pytest

from birre.cli import helpers


async def _simple_coroutine(value: int) -> int:
    await asyncio.sleep(0)
    return value


async def _spawn_background_task() -> None:
    async def _background() -> None:
        await asyncio.sleep(0)

    _ = asyncio.create_task(_background())
    await asyncio.sleep(0)


def test_await_sync_reuse_no_resource_warning(recwarn: pytest.WarningsRecorder) -> None:
    warnings.simplefilter("always", ResourceWarning)

    assert helpers.await_sync(_simple_coroutine(1)) == 1
    assert helpers.await_sync(_simple_coroutine(2)) == 2

    resource_warnings = [w for w in recwarn if w.category is ResourceWarning]
    assert not resource_warnings


def test_await_sync_cancels_background_tasks() -> None:
    # If background tasks leaked between invocations, the second call would raise.
    helpers.await_sync(_spawn_background_task())
    helpers.await_sync(_simple_coroutine(3))
