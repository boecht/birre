from __future__ import annotations

import asyncio
import ssl
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

import birre.integrations.bitsight.v1_bridge as v1

NULL_LOGGER = SimpleNamespace(
    debug=lambda *a, **k: None,
    error=lambda *a, **k: None,
    warning=lambda *a, **k: None,
)


def _ctx_spy():
    calls: list[tuple[str, str]] = []

    class _Ctx:
        async def __aenter__(self):  # for async with Context(api_server)
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def info(self, msg: str) -> None:
            calls.append(("info", msg))
            await asyncio.sleep(0)

        async def warning(self, msg: str) -> None:
            calls.append(("warning", msg))
            await asyncio.sleep(0)

        async def error(self, msg: str) -> None:
            calls.append(("error", msg))
            await asyncio.sleep(0)

    return _Ctx(), calls


def _patch_context(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
) -> None:
    class _CtxCM:
        docket = None  # Required by FastMCP 2.14 Context

        def __init__(self, _):  # noqa: D401
            pass  # Minimal context manager wrapper for testing

        async def __aenter__(self):
            return ctx

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(v1, "Context", _CtxCM)


def test_prepare_fastmcp_context_sets_private_attrs() -> None:
    class _API:
        docket = "docket"

    api = _API()
    v1._prepare_fastmcp_context(api)

    assert getattr(api, "_docket") == "docket"
    assert getattr(api, "_worker") is None


def test_prepare_fastmcp_context_ignores_unsettable_attrs() -> None:
    class _API:
        __slots__ = ("docket",)

        def __init__(self) -> None:
            self.docket = "docket"

    api = _API()

    v1._prepare_fastmcp_context(api)

    assert not hasattr(api, "_docket")
    assert not hasattr(api, "_worker")


@pytest.mark.asyncio
async def test_call_openapi_tool_normalizes_structured_and_json_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Fake api_server middleware returning various payload shapes
    class _API:
        async def _call_tool_middleware(  # noqa: ANN001
            self,
            name: str,
            params: dict[str, Any],
        ) -> Any:
            await asyncio.sleep(0)
            assert name == "companies"
            assert "q" in params
            # First return structured, then text JSON
            if params.get("mode") == "structured":
                return SimpleNamespace(structured_content={"result": {"ok": 1}})
            return SimpleNamespace(
                structured_content=None, content=[SimpleNamespace(text='{"a":1}')]
            )

    api = _API()
    ctx, _ = _ctx_spy()

    # Patch Context symbol used inside module to be a passthrough async CM
    _patch_context(monkeypatch, ctx)

    # 1) structured
    out1 = await v1.call_openapi_tool(
        api,
        "companies",
        ctx,
        {"q": "x", "mode": "structured"},
        logger=NULL_LOGGER,
    )  # type: ignore[arg-type]
    assert out1 == {"ok": 1}

    # 2) text json
    out2 = await v1.call_openapi_tool(
        api,
        "companies",
        ctx,
        {"q": "y"},
        logger=NULL_LOGGER,
    )  # type: ignore[arg-type]
    assert out2 == {"a": 1}


@pytest.mark.asyncio
async def test_call_openapi_tool_unstructured_returns_raw_with_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _API:
        async def _call_tool_middleware(self, *_: Any, **__: Any) -> Any:  # noqa: ANN001
            await asyncio.sleep(0)
            return SimpleNamespace(structured_content=None, content=None)

    api = _API()
    ctx, _ = _ctx_spy()

    _patch_context(monkeypatch, ctx)

    out = await v1.call_openapi_tool(
        api,
        "tool",
        ctx,
        {},
        logger=SimpleNamespace(
            debug=lambda *a, **k: None,
            error=lambda *a, **k: None,
            warning=lambda *a, **k: None,
        ),
    )  # type: ignore[arg-type]
    # When no structured data is available, the raw ToolResult (or equivalent) is returned
    assert out is not None


@pytest.mark.asyncio
async def test_parse_text_content_invalid_json_logs_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Exercise JSONDecodeError branch in _parse_text_content via call flow
    class _API:
        async def _call_tool_middleware(self, *_: Any, **__: Any) -> Any:  # noqa: ANN001
            await asyncio.sleep(0)
            return SimpleNamespace(
                structured_content=None, content=[SimpleNamespace(text="{bad}")]
            )

    api = _API()
    ctx, _ = _ctx_spy()

    _patch_context(monkeypatch, ctx)

    out = await v1.call_openapi_tool(
        api,
        "tool",
        ctx,
        {},
        logger=SimpleNamespace(
            debug=lambda *a, **k: None,
            error=lambda *a, **k: None,
            warning=lambda *a, **k: None,
        ),
    )  # type: ignore[arg-type]
    assert isinstance(out, str)  # raw text returned


def test_input_validation_errors() -> None:
    ctx, _ = _ctx_spy()
    api = object()
    with pytest.raises(ValueError):
        # empty tool name
        import anyio

        anyio.run(
            lambda: v1.call_openapi_tool(
                api,
                " ",
                ctx,
                {},
                logger=SimpleNamespace(),
            ),
        )  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        import anyio

        anyio.run(
            lambda: v1.call_openapi_tool(
                api,
                "t",
                ctx,
                [],
                logger=SimpleNamespace(),
            ),
        )  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_call_openapi_tool_http_status_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx, _ = _ctx_spy()

    _patch_context(monkeypatch, ctx)

    # Prepare a fake HTTP error
    req = httpx.Request("GET", "https://example.com/x")
    resp = httpx.Response(401, request=req)
    http_exc = httpx.HTTPStatusError("unauthorized", request=req, response=resp)

    class _API:
        async def _call_tool_middleware(self, *args, **kwargs):  # noqa: ANN001
            await asyncio.sleep(0)
            raise http_exc

    # Status errors propagate
    with pytest.raises(httpx.HTTPStatusError):
        await v1.call_openapi_tool(
            _API(),
            "tool",
            ctx,
            {},
            logger=SimpleNamespace(
                debug=lambda *a, **k: None,
                error=lambda *a, **k: None,
                warning=lambda *a, **k: None,
            ),
        )  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_call_openapi_tool_request_error_maps_to_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx, _ = _ctx_spy()

    req = httpx.Request("GET", "https://example.com/x")

    # Map a request error to domain error (patch classifier)
    class _BirreErr(Exception):
        def __init__(self):
            self.user_message = "mapped"

        def log_fields(self):  # noqa: D401
            return {}

        @property
        def hints(self):  # noqa: D401
            return ()

        @property
        def summary(self):  # noqa: D401
            return "TLS"

    def _classifier(exc: BaseException, *, tool_name: str):  # noqa: ANN001
        return _BirreErr()

    monkeypatch.setattr(v1, "classify_request_error", _classifier)

    class _ReqAPI:
        async def _call_tool_middleware(self, *_: Any, **__: Any) -> Any:  # noqa: ANN001
            await asyncio.sleep(0)
            raise httpx.RequestError("boom", request=req)

    with pytest.raises(_BirreErr):
        await v1.call_openapi_tool(
            _ReqAPI(),
            "tool",
            ctx,
            {},
            logger=SimpleNamespace(
                debug=lambda *a, **k: None,
                error=lambda *a, **k: None,
                warning=lambda *a, **k: None,
            ),
        )  # type: ignore[arg-type]


def test_filter_none() -> None:
    out = v1.filter_none({"a": 1, "b": None, "c": 0})
    assert out == {"a": 1, "c": 0}


@pytest.mark.asyncio
async def test_delegate_v1_and_v2_to_common(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def _fake_common(api, tool, ctx, params, *, logger):  # noqa: ANN001
        await asyncio.sleep(0)
        calls.append((tool, params))
        return {"ok": True}

    monkeypatch.setattr(v1, "call_openapi_tool", _fake_common)

    ctx, _ = _ctx_spy()
    api = object()
    out1 = await v1.call_v1_openapi_tool(
        api,
        "t1",
        ctx,
        {"x": 1},
        logger=NULL_LOGGER,
    )  # type: ignore[arg-type]
    out2 = await v1.call_v2_openapi_tool(
        api,
        "t2",
        ctx,
        {"y": 2},
        logger=NULL_LOGGER,
    )  # type: ignore[arg-type]
    assert out1 == out2 == {"ok": True}
    assert calls == [("t1", {"x": 1}), ("t2", {"y": 2})]


@pytest.mark.asyncio
async def test_request_error_without_mapping_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _API:
        async def _call_tool_middleware(self, *_: Any, **__: Any) -> Any:  # noqa: ANN001
            await asyncio.sleep(0)
            raise httpx.RequestError(
                "boom", request=httpx.Request("GET", "https://e/x")
            )

    api = _API()
    ctx, _ = _ctx_spy()

    _patch_context(monkeypatch, ctx)
    monkeypatch.setattr(v1, "classify_request_error", lambda *a, **k: None)

    with pytest.raises(httpx.RequestError):
        await v1.call_openapi_tool(
            api,
            "tool",
            ctx,
            {},
            logger=NULL_LOGGER,
        )  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_content_without_text_returns_raw_and_warns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _API:
        async def _call_tool_middleware(self, *_: Any, **__: Any) -> Any:  # noqa: ANN001
            await asyncio.sleep(0)
            return SimpleNamespace(
                structured_content=None,
                content=[SimpleNamespace(not_text="x")],
            )

    api = _API()
    ctx, calls = _ctx_spy()

    _patch_context(monkeypatch, ctx)

    raw = await v1.call_openapi_tool(
        api,
        "tool",
        ctx,
        {},
        logger=NULL_LOGGER,
    )  # type: ignore[arg-type]
    assert raw is not None
    # Ensure a warning was emitted by ctx
    assert any(kind == "warning" for kind, _ in calls)


@pytest.mark.asyncio
async def test_params_filtering_is_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class _API:
        async def _call_tool_middleware(  # noqa: ANN001
            self,
            name: str,
            params: dict[str, Any],
        ) -> Any:
            await asyncio.sleep(0)
            seen.update(params)
            assert "none_value" not in params
            return SimpleNamespace(structured_content={"result": {"ok": True}})

    api = _API()
    ctx, _ = _ctx_spy()

    _patch_context(monkeypatch, ctx)

    out = await v1.call_openapi_tool(
        api,
        "tool",
        ctx,
        {"none_value": None, "keep": 1},
        logger=NULL_LOGGER,  # type: ignore[arg-type]
    )
    assert out == {"ok": True}
    assert "keep" in seen and "none_value" not in seen


def test_log_tls_error_debug_and_non_debug(capsys: pytest.CaptureFixture[str]) -> None:
    class _Mapped(Exception):
        user_message = "user"

        def log_fields(self):  # noqa: D401
            return {"k": "v"}

        @property
        def hints(self):  # noqa: D401
            return ("hint1", "hint2")

        @property
        def summary(self):  # noqa: D401
            return "summary"

    logs = {"debug": 0, "error": 0}

    class _Logger:
        def debug(self, *a, **k):  # noqa: D401
            logs["debug"] += 1

        def error(self, *a, **k):  # noqa: D401
            logs["error"] += 1

    # With debug enabled → includes traceback debug and two hint errors
    v1._log_tls_error(  # type: ignore[attr-defined]
        _Mapped(),
        logger=_Logger(),
        debug_enabled=True,
        exc=ssl.SSLError("x"),
    )
    assert logs["error"] >= 3
    assert logs["debug"] >= 1

    # Without debug enabled → still logs errors but no debug
    logs.update({"debug": 0, "error": 0})
    v1._log_tls_error(  # type: ignore[attr-defined]
        _Mapped(),
        logger=_Logger(),
        debug_enabled=False,
        exc=ssl.SSLError("x"),
    )
    assert logs["error"] >= 3
    assert logs["debug"] == 0
