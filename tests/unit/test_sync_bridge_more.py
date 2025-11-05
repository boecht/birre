from __future__ import annotations

from birre.cli import sync_bridge


def test_invoke_with_optional_run_sync_passthrough() -> None:
    def fn(x: int) -> int:
        return x + 2

    out = sync_bridge.invoke_with_optional_run_sync(fn, 40)
    assert out == 42
