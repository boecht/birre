from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

import birre.domain.company_rating.service as svc


def _ctx():
    class _C:
        async def info(self, *_: Any, **__: Any) -> None:  # noqa: ANN001
            await asyncio.sleep(0)

        async def warning(self, *_: Any, **__: Any) -> None:  # noqa: ANN001
            await asyncio.sleep(0)

        async def error(self, *_: Any, **__: Any) -> None:  # noqa: ANN001
            await asyncio.sleep(0)

    return _C()


def test_rating_color_buckets() -> None:
    assert svc._rating_color(None) is None
    assert svc._rating_color(900) == "green"
    assert svc._rating_color(740) == "green"
    assert svc._rating_color(639.9) == "yellow"
    assert svc._rating_color(250) == "red"


def test_compute_trend_on_series() -> None:
    a = datetime(2025, 10, 1, tzinfo=UTC)
    b = datetime(2025, 10, 15, tzinfo=UTC)
    series = [(a, 700.0), (b, 750.0)]
    trend = svc._compute_trend(series)
    assert {"direction", "change"}.issubset(trend.keys())


@pytest.mark.asyncio
async def test_build_top_findings_selection_strict_relaxed_and_webappsec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange: strict returns 1 item, relaxed returns 2, web_appsec returns more
    strict = [
        {
            "severity": "severe",
            "details": {},
            "risk_vector": "x",
            "last_seen": "2025-10-01",
        }
    ]
    relaxed = strict + [
        {
            "severity": "moderate",
            "details": {},
            "risk_vector": "y",
            "last_seen": "2025-10-02",
        }
    ]
    web = relaxed + [
        {
            "severity": "low",
            "details": {},
            "risk_vector": "web_appsec",
            "last_seen": "2025-10-03",
        }
    ]

    async def _req(tool, ctx, params, limit, label, *, debug_enabled):  # noqa: ANN001
        await asyncio.sleep(0)
        if label == "strict":
            return strict
        if label == "relaxed":
            return relaxed
        if label == "web_appsec":
            return web
        return []

    monkeypatch.setattr(svc, "_request_top_findings", _req)

    ctx = _ctx()

    sel = await svc._build_top_findings_selection(
        lambda *a, **k: None, ctx, {}, 5, debug_enabled=True
    )  # type: ignore[arg-type]
    assert sel is not None
    assert sel.profile in ("relaxed", "relaxed+web_appsec")
    assert 2 <= len(sel.findings) <= 5


@pytest.mark.asyncio
async def test_build_top_findings_selection_appends_webappsec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _req(tool, ctx, params, limit, label, *, debug_enabled):  # noqa: ANN001
        await asyncio.sleep(0)
        if label == "strict":
            return []
        if label == "relaxed":
            return [
                {
                    "severity": "material",
                    "details": {},
                    "risk_vector": "x",
                    "last_seen": "2025-10-02",
                }
            ]
        if label == "web_appsec":
            return [
                {
                    "severity": "low",
                    "details": {},
                    "risk_vector": "web_appsec",
                    "last_seen": "2025-10-03",
                }
                for _ in range(5)
            ]
        return []

    monkeypatch.setattr(svc, "_request_top_findings", _req)
    ctx = _ctx()
    sel = await svc._build_top_findings_selection(
        lambda *a, **k: None, ctx, {}, 5, debug_enabled=True
    )  # type: ignore[arg-type]
    assert sel is not None
    assert sel.profile.endswith("web_appsec") and "web_appsec" in sel.supplements


@pytest.mark.asyncio
async def test_assemble_top_findings_section_indexes_and_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    findings = [
        {
            "severity": "severe",
            "details": {},
            "risk_vector": "x",
            "last_seen": "2025-10-01",
        },
        {
            "severity": "material",
            "details": {},
            "risk_vector": "y",
            "last_seen": "2025-10-02",
        },
        {
            "severity": "moderate",
            "details": {},
            "risk_vector": "z",
            "last_seen": "2025-10-03",
        },
    ]

    async def _build(call, ctx, base_params, limit, *, debug_enabled):  # noqa: ANN001
        await asyncio.sleep(0)
        return svc._TopFindingsSelection(findings=list(findings), max_items=limit)

    monkeypatch.setattr(svc, "_build_top_findings_selection", _build)

    ctx = _ctx()
    payload = await svc._assemble_top_findings_section(
        lambda *a, **k: None, ctx, "guid", "botnet_infections", 5, debug_enabled=False
    )  # type: ignore[arg-type]
    assert payload["count"] == 3
    assert payload["policy"]["max_items"] == 5
    assert all(
        isinstance(x.get("top"), int) and 1 <= x["top"] <= 5
        for x in payload["findings"]
    )


def test_normalize_top_finding_limit_and_unavailable_payload() -> None:
    assert svc._normalize_top_finding_limit(0) > 0
    model = svc._top_findings_unavailable_payload()
    assert model.count == 0 and model.policy.profile == "unavailable"
