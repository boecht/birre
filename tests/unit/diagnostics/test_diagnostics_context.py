from __future__ import annotations

from types import SimpleNamespace
from typing import Any

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


def _server_with_tools() -> SimpleNamespace:
    tools = {
        "company_search": object(),
        "get_company_rating": object(),
        "company_search_interactive": object(),
        "manage_subscriptions": object(),
        "request_company": object(),
    }
    server = SimpleNamespace(tools=tools)
    for name, tool in tools.items():
        setattr(server, name, tool)
    return server


def test_run_context_tool_diagnostics_handles_required_and_optional(
    monkeypatch,
) -> None:  # noqa: ANN001
    server = _server_with_tools()
    call_order: list[str] = []

    def _fake_diag(name: str, result: bool):
        def _runner(**kwargs: Any) -> bool:  # type: ignore[no-untyped-def]
            call_order.append(name)
            return result

        return _runner

    monkeypatch.setattr(
        dx,
        "run_company_search_diagnostics",
        _fake_diag("company_search", True),
    )
    monkeypatch.setattr(
        dx,
        "run_rating_diagnostics",
        _fake_diag("get_company_rating", False),
    )
    monkeypatch.setattr(
        dx,
        "run_company_search_interactive_diagnostics",
        _fake_diag("company_search_interactive", True),
    )
    monkeypatch.setattr(
        dx,
        "run_manage_subscriptions_diagnostics",
        _fake_diag("manage_subscriptions", False),
    )
    monkeypatch.setattr(
        dx,
        "run_request_company_diagnostics",
        _fake_diag("request_company", True),
    )

    summary: dict[str, dict[str, Any]] = {}
    failures: list[dx.DiagnosticFailure | None] = []
    ok = dx.run_context_tool_diagnostics(
        context="risk_manager",
        logger=DummyLogger(),  # type: ignore[arg-type]
        server_instance=server,
        expected_tools=dx.EXPECTED_TOOLS_BY_CONTEXT["risk_manager"],
        summary=summary,
        failures=failures,
        run_sync=None,
    )

    assert ok is False  # rating diagnostic returned False
    assert summary["company_search"]["status"] == "pass"
    assert summary["get_company_rating"]["status"] == "fail"
    assert summary["manage_subscriptions"]["status"] == "warning"
    assert summary["request_company"]["status"] in {"pass", "warning"}
    assert call_order == [
        "company_search",
        "get_company_rating",
        "company_search_interactive",
        "manage_subscriptions",
        "request_company",
    ]
    assert failures == []
