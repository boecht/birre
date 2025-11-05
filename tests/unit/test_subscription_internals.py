from __future__ import annotations

import asyncio

import pytest

import birre.domain.subscription as sub

log_bulk_response = sub._log_bulk_response  # type: ignore[attr-defined]


def test_extract_guid_values_and_payload_builder() -> None:
    resp = {"added": ["a", {"guid": "b"}, 3, None], "modified": [{"guid": "c"}]}
    out = sub._extract_guid_values(resp, ("added", "modified"))  # type: ignore[attr-defined]
    assert set(out) == {"a", "b", "c"}

    assert sub._build_subscription_payload(None, "x") is None  # type: ignore[attr-defined]
    assert sub._build_subscription_payload("F", None) is None  # type: ignore[attr-defined]
    payload = sub._build_subscription_payload("F", "T")  # type: ignore[attr-defined]
    assert payload == {"folder": ["F"], "type": "T"}


@pytest.mark.asyncio
async def test_log_bulk_response_debug_toggle(monkeypatch) -> None:
    # Spy ctx.info
    calls = []

    class _Ctx:
        async def info(self, msg: str) -> None:
            await asyncio.sleep(0)
            calls.append(msg)

    ctx = _Ctx()
    # Off → no call
    await log_bulk_response(ctx, {"a": 1}, "add", debug_enabled=False)
    assert calls == []
    # On → call
    await log_bulk_response(ctx, {"a": 1}, "add", debug_enabled=True)
    assert calls and "raw response" in calls[0]

    # Non-serializable object → fallback to str
    class Obj:
        def __str__(self) -> str:
            return "OBJ"

    calls.clear()
    await log_bulk_response(ctx, Obj(), "add", debug_enabled=True)
    assert "OBJ" in calls[0]
