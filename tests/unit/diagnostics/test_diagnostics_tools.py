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
    entries = [
        {
            "guid": "g-1",
            "name": "GitHub",
            "domain": (domain or dx.HEALTHCHECK_COMPANY_DOMAIN),
        }
    ]
    return {"companies": entries, "count": 1}


def test_company_search_diagnostics_success() -> None:
    def tool(ctx, **params):  # type: ignore[no-untyped-def]
        if "name" in params:
            return _ok_search_payload(dx.HEALTHCHECK_COMPANY_DOMAIN)
        if "domain" in params:
            return _ok_search_payload(params["domain"])
        return {}

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
        {"status": "dry_run", "domain": dx.HEALTHCHECK_REQUEST_DOMAIN},
        logger=logger,  # type: ignore[arg-type]
        expected_domain=dx.HEALTHCHECK_REQUEST_DOMAIN,
    )
    assert ok3 is True

    ok4 = dx._validate_request_company_payload(
        {
            "status": "requested",
            "domains": [{"domain": dx.HEALTHCHECK_REQUEST_DOMAIN}],
        },
        logger=logger,  # type: ignore[arg-type]
        expected_domain=dx.HEALTHCHECK_REQUEST_DOMAIN,
    )
    assert ok4 is True
