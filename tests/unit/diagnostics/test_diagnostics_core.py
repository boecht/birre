from __future__ import annotations

import asyncio
import ssl
from types import SimpleNamespace

import httpx

from birre.application import diagnostics as dx


class DummyLogger:
    def bind(self, **kwargs):  # noqa: D401
        return self

    def info(self, *a, **k):
        return None

    def warning(self, *a, **k):
        return None

    def error(self, *a, **k):
        return None

    def exception(self, *a, **k):
        return None

    def critical(self, *a, **k):
        return None


def test_resolve_tool_callable_variants() -> None:
    assert dx._resolve_tool_callable(None) is None  # type: ignore[attr-defined]
    assert dx._resolve_tool_callable(lambda *a, **k: None) is not None  # type: ignore[attr-defined]
    tool = SimpleNamespace(fn=lambda *a, **k: None)
    assert dx._resolve_tool_callable(tool) is tool.fn  # type: ignore[attr-defined]
    assert dx._resolve_tool_callable(object()) is None  # type: ignore[attr-defined]


def test_invoke_tool_supports_kwargs_and_params_fallback() -> None:
    # kwargs path
    def tool_kwargs(ctx, *, x: int) -> int:  # type: ignore[no-untyped-def]
        return x + 1

    out = dx._invoke_tool(tool_kwargs, object(), run_sync=None, x=41)  # type: ignore[attr-defined]
    assert out == 42

    # params fallback path (TypeError when unexpected kwarg)
    def tool_params(ctx, params):  # type: ignore[no-untyped-def]
        return params["x"] + 1

    out2 = dx._invoke_tool(tool_params, object(), run_sync=None, x=41)  # type: ignore[attr-defined]
    assert out2 == 42

    # awaitable result path
    async def tool_async(ctx, *, x: int) -> int:  # type: ignore[no-untyped-def]
        await asyncio.sleep(0)
        return x + 1

    out3 = dx._invoke_tool(
        tool_async,
        object(),
        run_sync=lambda c: asyncio.get_event_loop().run_until_complete(c),
        x=41,
    )  # type: ignore[attr-defined]
    assert out3 == 42


def test_discover_and_collect_tools() -> None:
    server = SimpleNamespace(
        tools={"a": object()},
        get_tools=lambda: {"b": object()},
        company_search=object(),
    )
    names = dx.discover_context_tools(server)
    assert {"a", "b"}.issubset(names)
    tool_map = dx.collect_tool_map(server)
    # Should include explicit attribute fallback
    assert set(tool_map.keys()) >= {"a", "b", "company_search"}


def test_validate_positive() -> None:
    assert dx._validate_positive("x", None) is None  # type: ignore[attr-defined]
    assert dx._validate_positive("x", 1) == 1  # type: ignore[attr-defined]
    try:
        dx._validate_positive("x", 0)  # type: ignore[attr-defined]
    except ValueError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("expected ValueError")


def test_check_required_and_optional_tool_paths() -> None:
    logger = DummyLogger()
    # Required tool missing
    summary: dict[str, object] = {}
    ok = dx.check_required_tool(
        tool_name="x",
        tool=None,
        context="standard",
        logger=logger,  # type: ignore[arg-type]
        diagnostic_fn=lambda **k: True,  # type: ignore[no-untyped-call]
        failures=[],
        summary=summary,
        run_sync=None,
    )
    assert not ok and summary.get("status") == "fail"

    # Optional tool missing → pass with warning
    opt_summary: dict[str, object] = {}
    opt_ok = dx.check_optional_tool(
        tool=None,
        context="standard",
        logger=logger,  # type: ignore[arg-type]
        diagnostic_fn=lambda **k: True,  # type: ignore[no-untyped-call]
        failures=[],
        summary=opt_summary,
        run_sync=None,
    )
    assert opt_ok and opt_summary.get("status") == "warning"

    # Diagnostic returns False
    flag = dx.check_optional_tool(
        tool=object(),
        context="standard",
        logger=logger,  # type: ignore[arg-type]
        diagnostic_fn=lambda **k: False,  # type: ignore[no-untyped-call]
        failures=[],
        summary={},
        run_sync=None,
    )
    assert not flag


def test_aggregate_tool_outcomes_offline_and_merge() -> None:
    tools = frozenset({"a", "b"})
    agg = dx.aggregate_tool_outcomes(tools, [], offline_mode=True, offline_missing=["a"])  # type: ignore[list-item]
    assert agg["a"]["status"] == "fail" and agg["b"]["status"] == "warning"

    attempts = [
        {"label": "L1", "tools": {"a": {"status": "warning"}}},
        {"label": "L2", "tools": {"a": {"status": "pass"}, "b": {"status": "fail"}}},
    ]
    agg2 = dx.aggregate_tool_outcomes(tools, attempts)
    assert agg2["a"]["status"] == "pass" and agg2["b"]["status"] == "fail"


def test_classify_and_summarize_failure() -> None:
    f = dx.DiagnosticFailure(tool="t", stage="s", message="TLS handshake error")
    assert dx.classify_failure(f) in (None, "tls")
    f2 = dx.DiagnosticFailure(tool="t", stage="s", message="x", exception=ssl.SSLError("boom"))
    assert dx.classify_failure(f2) == "tls"
    f3 = dx.DiagnosticFailure(
        tool="t",
        stage="s",
        message="x",
        exception=FileNotFoundError("ca not found"),
    )
    assert dx.classify_failure(f3) == dx.MSG_CONFIG_CA_BUNDLE

    # httpx path with SSL-like message and cause
    cause = ssl.SSLError("SSL bad")
    exc = httpx.HTTPError("network")
    exc.__cause__ = cause  # type: ignore[attr-defined]
    f4 = dx.DiagnosticFailure(tool="t", stage="s", message="x", exception=exc)
    assert dx.classify_failure(f4) == "tls"

    s = dx.summarize_failure(f4)
    assert s["tool"] == "t" and "error" in s
