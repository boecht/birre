import asyncio
from types import SimpleNamespace
from typing import Any, Dict

import pytest
from fastmcp import Context

from src.business.helpers.subscription import (
    SubscriptionAttempt,
    cleanup_ephemeral_subscription,
    create_ephemeral_subscription,
)


class StubContext(Context):
    def __init__(self) -> None:
        self.messages: Dict[str, list[str]] = {"info": [], "warning": [], "error": []}
        self.metadata = {}
        self.tool = "subscription"
        self._request_id = "sub-test"

    async def info(self, message: str) -> None:  # type: ignore[override]
        await asyncio.sleep(0)
        self.messages["info"].append(message)

    async def warning(self, message: str) -> None:  # type: ignore[override]
        await asyncio.sleep(0)
        self.messages["warning"].append(message)

    async def error(self, message: str) -> None:  # type: ignore[override]
        await asyncio.sleep(0)
        self.messages["error"].append(message)

    @property
    def request_id(self) -> str:  # type: ignore[override]
        return self._request_id

    @property
    def call_id(self) -> str:  # type: ignore[override]
        return self._request_id


@pytest.mark.asyncio
async def test_create_ephemeral_subscription_success(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = StubContext()
    monkeypatch.setenv("BIRRE_SUBSCRIPTION_FOLDER", "API")
    monkeypatch.setenv("BIRRE_SUBSCRIPTION_TYPE", "continuous_monitoring")

    async def call_v1(name: str, ctx: Context, payload: Dict[str, Any]):
        await asyncio.sleep(0)
        assert name == "manageSubscriptionsBulk"
        assert payload["add"][0]["guid"] == "guid-1"
        return {"added": ["guid-1"]}

    attempt = await create_ephemeral_subscription(call_v1, ctx, "guid-1", logger=_logdummy())
    assert attempt == SubscriptionAttempt(True, True, False, None)
    assert not ctx.messages["error"]


@pytest.mark.asyncio
async def test_create_ephemeral_subscription_already_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = StubContext()
    monkeypatch.setenv("BIRRE_SUBSCRIPTION_FOLDER", "API")
    monkeypatch.setenv("BIRRE_SUBSCRIPTION_TYPE", "continuous_monitoring")

    async def call_v1(name: str, ctx: Context, payload: Dict[str, Any]):
        await asyncio.sleep(0)
        return {"errors": [{"guid": "guid-1", "message": "Already exists"}]}

    attempt = await create_ephemeral_subscription(call_v1, ctx, "guid-1", logger=_logdummy())
    assert attempt == SubscriptionAttempt(True, False, True, "Already exists")


@pytest.mark.asyncio
async def test_create_ephemeral_subscription_missing_config(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = StubContext()
    monkeypatch.delenv("BIRRE_SUBSCRIPTION_FOLDER", raising=False)
    monkeypatch.delenv("BIRRE_SUBSCRIPTION_TYPE", raising=False)

    async def call_v1(name: str, ctx: Context, payload: Dict[str, Any]):
        await asyncio.sleep(0)
        raise AssertionError("call_v1 should not be invoked when config missing")

    attempt = await create_ephemeral_subscription(call_v1, ctx, "guid-1", logger=_logdummy())
    assert not attempt.success
    assert "Subscription settings missing" in (attempt.message or "")
    assert ctx.messages["error"]


@pytest.mark.asyncio
async def test_cleanup_ephemeral_subscription_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = StubContext()

    async def call_v1(name: str, ctx: Context, payload: Dict[str, Any]):
        await asyncio.sleep(0)
        return {"errors": ["boom"]}

    result = await cleanup_ephemeral_subscription(call_v1, ctx, "guid-1")
    assert result is False
    assert ctx.messages["error"]


@pytest.mark.asyncio
async def test_cleanup_ephemeral_subscription_success(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = StubContext()

    async def call_v1(name: str, ctx: Context, payload: Dict[str, Any]):
        await asyncio.sleep(0)
        return {"deleted": ["guid-1"]}

    result = await cleanup_ephemeral_subscription(call_v1, ctx, "guid-1")
    assert result is True


def _logdummy():
    class _Logger:
        def info(self, *args, **kwargs):
            """No-op info logging stub used for dependency-free tests."""

        def error(self, *args, **kwargs):
            """No-op error logging stub used for dependency-free tests."""

    return _Logger()
