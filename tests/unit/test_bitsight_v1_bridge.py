from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from birre.infrastructure.logging import get_logger
from birre.integrations.bitsight import v1_bridge as bridge


class DummyContext:
    def __init__(self) -> None:
        self.infos: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []

    async def info(self, message: str) -> None:
        self.infos.append(message)

    async def warning(self, message: str) -> None:
        self.warnings.append(message)

    async def error(self, message: str) -> None:
        self.errors.append(message)


def test_filter_none_removes_nones() -> None:
    params = {"a": 1, "b": None}
    assert bridge.filter_none(params) == {"a": 1}


@pytest.mark.asyncio
async def test_parse_text_content_handles_bad_json() -> None:
    ctx = DummyContext()
    logger = get_logger("test.bitsight")
    result = await bridge._parse_text_content("not json", "tool", ctx, logger)
    assert result == "not json"
    assert ctx.warnings


@pytest.mark.asyncio
async def test_normalize_tool_result_prefers_structured() -> None:
    ctx = DummyContext()
    logger = get_logger("test.bitsight")

    class ToolResult:
        structured_content = {"result": {"value": 1}}

    normalized = await bridge._normalize_tool_result(ToolResult(), "tool", ctx, logger)
    assert normalized == {"value": 1}

    class TextResult:
        content = [SimpleNamespace(text=json.dumps({"foo": "bar"}))]

    normalized_text = await bridge._normalize_tool_result(
        TextResult(), "tool", ctx, logger
    )
    assert normalized_text == {"foo": "bar"}


class DummyResponse:
    def __init__(
        self, json_value: dict[str, Any] | None = None, text: str = "text"
    ) -> None:
        self._json_value = json_value
        self.text = text

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        if self._json_value is None:
            raise json.JSONDecodeError("err", "", 0)
        return self._json_value


class DummyClient:
    def __init__(self, response: DummyResponse) -> None:
        self.response = response
        self.captured: list[tuple[str, dict[str, Any]]] = []

    async def post(
        self, path: str, data: Any, files: Any, timeout: Any
    ) -> DummyResponse:
        self.captured.append((path, data))
        return self.response


def _make_api_stub(
    response: DummyResponse, timeout: float | None = None
) -> SimpleNamespace:
    client = DummyClient(response)
    return SimpleNamespace(_client=client, _timeout=timeout)


@pytest.mark.asyncio
async def test_call_company_request_bulk_returns_json() -> None:
    ctx = DummyContext()
    logger = get_logger("test.bitsight")
    response = DummyResponse(json_value={"ok": True})
    api_server = _make_api_stub(response, timeout=5)
    payload = {"file": "domain\nexample.com"}
    result = await bridge._call_company_request_bulk(api_server, ctx, payload, logger)
    assert result == {"ok": True}
    assert api_server._client.captured


@pytest.mark.asyncio
async def test_call_company_request_bulk_returns_text_on_json_error() -> None:
    ctx = DummyContext()
    logger = get_logger("test.bitsight")
    response = DummyResponse(json_value=None, text="raw")
    api_server = _make_api_stub(response)
    payload = {"file": "domain\nexample.com"}
    result = await bridge._call_company_request_bulk(api_server, ctx, payload, logger)
    assert result == "raw"


@pytest.mark.asyncio
async def test_call_company_request_bulk_requires_file() -> None:
    ctx = DummyContext()
    logger = get_logger("test.bitsight")
    api_server = _make_api_stub(DummyResponse())
    with pytest.raises(ValueError):
        await bridge._call_company_request_bulk(api_server, ctx, {}, logger)
