from __future__ import annotations

from typing import Any

from birre.application import diagnostics as dx


class DummyLogger:
    def __init__(self):
        self.bound = {}

    def bind(self, **kwargs):  # noqa: D401
        self.bound.update(kwargs)
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


def _ok_search_payload(domain: str | None) -> dict[str, Any]:
    resolved = domain or dx.HEALTHCHECK_COMPANY_DOMAIN
    entries = [
        {
            "guid": "g-1",
            "name": "GitHub",
            "domain": resolved,
            "primary_domain": resolved,
        }
    ]
    return {"companies": entries, "count": 1}


def test_company_search_diagnostics_success() -> None:
    def tool(ctx, **params):  # type: ignore[no-untyped-def]
        if params.get("name") == dx.HEALTHCHECK_COMPANY_NAME:
            return _ok_search_payload(dx.HEALTHCHECK_COMPANY_DOMAIN)
        if "domain" in params:
            return _ok_search_payload(params["domain"])
        return {"companies": [], "count": 0}

    assert (
        dx.run_company_search_diagnostics(
            context="standard",
            logger=DummyLogger(),  # type: ignore[arg-type]
            tool=tool,
            failures=[],
            summary={},
            run_sync=None,
        )
        is True
    )


def test_company_search_diagnostics_call_and_validation_fail() -> None:
    def tool_fail(ctx, **params):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    assert (
        dx.run_company_search_diagnostics(
            context="standard",
            logger=DummyLogger(),  # type: ignore[arg-type]
            tool=tool_fail,
            failures=[],
            summary={},
            run_sync=None,
        )
        is False
    )

    def tool_bad(ctx, **params):  # type: ignore[no-untyped-def]
        return {"results": []}  # invalid results list

    assert (
        dx.run_company_search_diagnostics(
            context="standard",
            logger=DummyLogger(),  # type: ignore[arg-type]
            tool=tool_bad,
            failures=[],
            summary={},
            run_sync=None,
        )
        is False
    )


def _rating_payload(domain: str) -> dict[str, Any]:
    return {
        "name": "GitHub",
        "domain": domain,
        "current_rating": {"value": "A"},
        "top_findings": {"count": 1, "findings": [{"id": 1}]},
        "legend": {"rating": {"A": "ok"}},
    }


def _interactive_payload() -> dict[str, Any]:
    return {
        "results": [
            {
                "guid": "g-1",
                "name": "GitHub",
                "primary_domain": dx.HEALTHCHECK_COMPANY_DOMAIN,
                "subscription": {"active": True},
            }
        ],
        "count": 1,
        "guidance": {"next": "step"},
    }


def _request_company_payload() -> dict[str, Any]:
    return {
        "status": "dry_run",
        "dry_run": True,
        "submitted": [dx.HEALTHCHECK_REQUEST_DOMAIN],
        "successfully_requested": [dx.HEALTHCHECK_REQUEST_DOMAIN],
        "already_existing": [{"domain": dx.HEALTHCHECK_REQUEST_DOMAIN}],
        "failed": [],
    }


def test_run_rating_diagnostics_success_and_domain_mismatch() -> None:
    def tool(ctx, **params):  # type: ignore[no-untyped-def]
        return _rating_payload(dx.HEALTHCHECK_COMPANY_DOMAIN)

    assert (
        dx.run_rating_diagnostics(
            context="standard",
            logger=DummyLogger(),  # type: ignore[arg-type]
            tool=tool,
            failures=[],
            summary={},
            run_sync=None,
        )
        is True
    )

    def tool_bad_domain(ctx, **params):  # type: ignore[no-untyped-def]
        return _rating_payload("example.com")

    assert (
        dx.run_rating_diagnostics(
            context="standard",
            logger=DummyLogger(),  # type: ignore[arg-type]
            tool=tool_bad_domain,
            failures=[],
            summary={},
            run_sync=None,
        )
        is False
    )


def test_manage_subscriptions_and_request_company_validators() -> None:
    logger = DummyLogger()

    # manage_subscriptions payloads
    ok = dx._validate_manage_subscriptions_payload(
        {
            "status": "dry_run",
            "guids": [dx.HEALTHCHECK_COMPANY_GUID],
            "payload": {"add": []},
        },
        logger=logger,  # type: ignore[arg-type]
        expected_guid=dx.HEALTHCHECK_COMPANY_GUID,
    )
    assert ok is True

    ok2 = dx._validate_manage_subscriptions_payload(
        {"status": "applied", "guids": [dx.HEALTHCHECK_COMPANY_GUID]},
        logger=logger,  # type: ignore[arg-type]
        expected_guid=dx.HEALTHCHECK_COMPANY_GUID,
    )
    assert ok2 is True

    # request_company payloads
    ok3 = dx._validate_request_company_payload(
        {
            "status": "dry_run",
            "dry_run": True,
            "submitted": [dx.HEALTHCHECK_REQUEST_DOMAIN],
            "already_existing": [],
            "successfully_requested": [dx.HEALTHCHECK_REQUEST_DOMAIN],
            "failed": [],
        },
        logger=logger,  # type: ignore[arg-type]
        expected_domain=dx.HEALTHCHECK_REQUEST_DOMAIN,
    )
    assert ok3 is True

    ok4 = dx._validate_request_company_payload(
        {
            "status": "submitted_v2_bulk",
            "submitted": [dx.HEALTHCHECK_REQUEST_DOMAIN],
            "already_existing": [],
            "successfully_requested": [dx.HEALTHCHECK_REQUEST_DOMAIN],
            "failed": [],
        },
        logger=logger,  # type: ignore[arg-type]
        expected_domain=dx.HEALTHCHECK_REQUEST_DOMAIN,
    )
    assert ok4 is True


def test_company_search_interactive_diagnostics_success_and_validation_warning() -> (
    None
):
    logger = DummyLogger()
    summary: dict[str, Any] = {}

    def tool_success(ctx, **params):  # type: ignore[no-untyped-def]
        assert params["name"] == dx.HEALTHCHECK_COMPANY_NAME
        return _interactive_payload()

    assert (
        dx.run_company_search_interactive_diagnostics(
            context="standard",
            logger=logger,  # type: ignore[arg-type]
            tool=tool_success,
            failures=[],
            summary=summary,
            run_sync=None,
        )
        is True
    )
    assert summary["status"] == "pass"

    failures: list[dx.DiagnosticFailure | None] = []
    summary_warning: dict[str, Any | None] = {}

    def tool_invalid(ctx, **params):  # type: ignore[no-untyped-def]
        return {"results": [], "count": 0, "guidance": {}}

    assert (
        dx.run_company_search_interactive_diagnostics(
            context="standard",
            logger=logger,  # type: ignore[arg-type]
            tool=tool_invalid,
            failures=failures,
            summary=summary_warning,
            run_sync=None,
        )
        is False
    )
    assert summary_warning["status"] == "warning"
    assert (
        summary_warning.get("details", {}).get("reason")
        == dx.MSG_UNEXPECTED_PAYLOAD_STRUCTURE
    )
    assert failures and failures[-1].stage == "validation"


def test_manage_subscriptions_diagnostics_success_and_invalid_payload() -> None:
    logger = DummyLogger()

    def tool_success(ctx, **params):  # type: ignore[no-untyped-def]
        assert params["action"] == "subscribe"
        assert params["guids"] == [dx.HEALTHCHECK_COMPANY_GUID]
        return {
            "status": "dry_run",
            "guids": [dx.HEALTHCHECK_COMPANY_GUID],
            "payload": {"add": []},
        }

    summary: dict[str, Any] = {}
    assert (
        dx.run_manage_subscriptions_diagnostics(
            context="standard",
            logger=logger,  # type: ignore[arg-type]
            tool=tool_success,
            failures=[],
            summary=summary,
            run_sync=None,
        )
        is True
    )
    assert summary["status"] == "pass"

    failures: list[dx.DiagnosticFailure | None] = []
    summary_warning: dict[str, Any | None] = {}

    def tool_invalid(ctx, **params):  # type: ignore[no-untyped-def]
        return {"status": "applied", "guids": []}

    assert (
        dx.run_manage_subscriptions_diagnostics(
            context="standard",
            logger=logger,  # type: ignore[arg-type]
            tool=tool_invalid,
            failures=failures,
            summary=summary_warning,
            run_sync=None,
        )
        is False
    )
    assert summary_warning["status"] == "warning"
    assert (
        summary_warning.get("details", {}).get("reason")
        == dx.MSG_UNEXPECTED_PAYLOAD_STRUCTURE
    )
    assert failures and failures[-1].stage == "validation"


def test_request_company_diagnostics_handles_400_and_payload(monkeypatch) -> None:  # noqa: ANN001
    logger = DummyLogger()

    summary: dict[str, Any] = {}

    def tool_success(ctx, **params):  # type: ignore[no-untyped-def]
        assert params["domains"] == dx.HEALTHCHECK_REQUEST_DOMAIN
        return _request_company_payload()

    assert (
        dx.run_request_company_diagnostics(
            context="standard",
            logger=logger,  # type: ignore[arg-type]
            tool=tool_success,
            failures=[],
            summary=summary,
            run_sync=None,
        )
        is True
    )
    assert summary["status"] == "pass"

    summary_400: dict[str, Any | None] = {}

    def tool_raises(ctx, **params):  # type: ignore[no-untyped-def]
        raise RuntimeError("HTTP 400 Bad Request: domain already exists")

    assert (
        dx.run_request_company_diagnostics(
            context="standard",
            logger=logger,  # type: ignore[arg-type]
            tool=tool_raises,
            failures=[],
            summary=summary_400,
            run_sync=None,
        )
        is True
    )
    assert summary_400["status"] == "pass"
    assert "API reachable" in summary_400.get("details", {}).get("reason", "")

    failures: list[dx.DiagnosticFailure | None] = []
    summary_warning: dict[str, Any | None] = {}

    def tool_invalid(ctx, **params):  # type: ignore[no-untyped-def]
        return {"status": "dry_run", "submitted": []}

    assert (
        dx.run_request_company_diagnostics(
            context="standard",
            logger=logger,  # type: ignore[arg-type]
            tool=tool_invalid,
            failures=failures,
            summary=summary_warning,
            run_sync=None,
        )
        is False
    )
    assert summary_warning["status"] == "warning"
    assert (
        summary_warning.get("details", {}).get("reason")
        == dx.MSG_UNEXPECTED_PAYLOAD_STRUCTURE
    )
    assert failures and failures[-1].stage == "validation"
